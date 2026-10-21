import pytest
from sqlalchemy import select

from app.models import Relationship, SourceFile
from app.relationships import import_modules
from app.relationships import module_name


def test_source_layout_and_module_names():
    assert module_name("src.py") == ["src"]
    assert module_name("src/pkg/__init__.py") == ["pkg"]
    assert module_name("namespace/child.py") == ["namespace", "child"]


@pytest.fixture
def graph(client, ingested_repository):
    with client.app.state.sessions() as session:
        session.add_all([
            SourceFile(repository_id=ingested_repository, path="src/pkg/__init__.py",
                source="from . import util\n", content_hash="d" * 64, line_count=1),
            SourceFile(repository_id=ingested_repository, path="src/pkg/util.py",
                source="class Same:\n    def one(self): pass\nclass Same:\n    def two(self): pass\n",
                content_hash="e" * 64, line_count=4),
            SourceFile(repository_id=ingested_repository, path="src/pkg/main.py",
                source="from . import util as u\nfrom .util import Same\nimport os, pkg.util as helper\nfrom ... import missing\n",
                content_hash="f" * 64, line_count=4),
        ])
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    assert client.post(prefix + "/parse").status_code == 200
    files = {f["path"]: f["id"] for f in client.get(prefix + "/files").json()}
    return prefix, files


def test_local_imports_aliases_unresolved_and_incoming(client, graph):
    prefix, files = graph
    url = prefix + f"/files/{files['src/pkg/main.py']}/relationships"
    page = client.get(url, params={"kind": "imports"}).json()
    assert page["ready"] and page["commit_sha"] == "a" * 40
    assert page["total"] == 5
    local = [e for e in page["items"] if e["resolution"] == "local"]
    assert len(local) == 3
    assert all(e["target_file_id"] == files["src/pkg/util.py"] for e in local)
    assert sum(e["resolution"] == "unresolved" for e in page["items"]) == 2
    incoming = client.get(prefix + f"/files/{files['src/pkg/util.py']}/relationships",
                          params={"direction": "incoming"}).json()
    assert incoming["total"] == 4
    assert {e["path"] for e in incoming["items"]} == {"src/pkg/main.py", "src/pkg/__init__.py"}


def test_containment_uses_exact_definition_not_repeated_name(client, graph):
    prefix, files = graph
    symbols = client.get(prefix + "/symbols", params={"file_id": files["src/pkg/util.py"]}).json()
    page = client.get(prefix + f"/files/{files['src/pkg/util.py']}/relationships",
                      params={"kind": "contains"}).json()
    assert page["total"] == 4
    one = next(e for e in page["items"] if e["target_name"] == "one")
    two = next(e for e in page["items"] if e["target_name"] == "two")
    assert one["source_symbol_id"] == symbols[0]["id"]
    assert two["source_symbol_id"] == symbols[2]["id"]
    assert one["source_symbol_id"] != two["source_symbol_id"]
    assert one["start_line"] == 2 and two["start_line"] == 4


def test_paging_scope_and_reparse_cleanup(client, graph):
    prefix, files = graph
    url = prefix + f"/files/{files['src/pkg/main.py']}/relationships"
    first = client.get(url).json()
    assert client.get(url, params={"limit": 2, "offset": 2}).json()["items"] == first["items"][2:4]
    assert client.post(prefix + "/parse").status_code == 200
    second = client.get(url).json()
    assert second["total"] == first["total"]
    assert client.get(f"/repositories/999/files/{files['src/pkg/main.py']}/relationships").status_code == 404
    for params in [{"kind": "calls"}, {"direction": "both"}, {"limit": 101}, {"offset": -1}]:
        assert client.get(url, params=params).status_code == 422


def test_legacy_index_needs_reparse_and_invalidation(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    file_id = client.get(prefix + "/files").json()[0]["id"]
    url = prefix + f"/files/{file_id}/relationships"
    assert client.get(url).json()["ready"] is False
    client.post(prefix + "/parse")
    from app.parsing import clear_parse_results
    with client.app.state.sessions() as session:
        clear_parse_results(session, ingested_repository)
        session.commit()
        assert session.scalars(select(Relationship)).all() == []
    assert client.get(url).json()["ready"] is False


def test_ambiguous_module_is_not_guessed(client, graph):
    prefix, files = graph
    with client.app.state.sessions() as session:
        session.add(SourceFile(repository_id=int(prefix.split("/")[-1]), path="pkg/util.py",
            source="", content_hash="1" * 64, line_count=0))
        session.commit()
    client.post(prefix + "/parse")
    edges = client.get(prefix + f"/files/{files['src/pkg/main.py']}/relationships",
                       params={"kind": "imports"}).json()["items"]
    assert sum(e["resolution"] == "ambiguous" for e in edges) == 3
    assert all(e["target_file_id"] is None for e in edges)


def test_graph_write_failure_rolls_back_symbols_and_edges(client, graph):
    from sqlalchemy.exc import IntegrityError
    prefix, files = graph
    url = prefix + f"/files/{files['src/pkg/main.py']}/relationships"
    before = client.get(url).json()
    symbols = client.get(prefix + "/symbols").json()
    engine = client.app.state.sessions.kw["bind"]
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TRIGGER reject_edges BEFORE INSERT ON relationships "
                                  "BEGIN SELECT RAISE(ABORT, 'simulated graph failure'); END")
    try:
        with pytest.raises(IntegrityError):
            client.post(prefix + "/parse")
        assert client.get(url).json() == before
        assert client.get(prefix + "/symbols").json() == symbols
        assert not client.app.state.ingestion_lock.locked()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER reject_edges")


def test_graph_persists_after_restart(client, graph, database_url):
    from fastapi.testclient import TestClient
    from app.main import create_app
    prefix, files = graph
    url = prefix + f"/files/{files['src/pkg/main.py']}/relationships"
    before = client.get(url).json()
    with TestClient(create_app(database_url)) as restarted:
        assert restarted.get(url).json() == before


@pytest.mark.parametrize("statement,path,expected", [
    ("import a.b as c", "main.py", [("a.b", ["a.b"])]),
    ("from ..utils import helper", "src/pkg/sub/main.py", [("..utils import helper", ["pkg.utils.helper", "pkg.utils"])]),
    ("from pkg import *", "main.py", [("pkg import *", ["pkg"])]),
    ("from __future__ import annotations", "main.py", [("__future__ import annotations", [])]),
    ("from . import other", "main.py", [("from . import other", [])]),
    ("import (", "main.py", []),
])
def test_import_syntax_resolution(statement, path, expected):
    assert import_modules(statement, path) == expected
