from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import event
from sqlalchemy.engine import make_url
import sqlite3

from app.main import create_app
from app.models import SourceFile


def app_file(client, repository_id):
    return next(file for file in client.get(f"/repositories/{repository_id}/files").json()
                if file["path"] == "app.py")


def test_registered_overview_marks_unavailable_stages(client):
    repository = client.post("/repositories", json={"github_url": "https://github.com/example/empty"}).json()
    response = client.get(f"/repositories/{repository['id']}/overview")
    assert response.status_code == 200
    assert response.json() == {"repository": repository, "snapshot": None, "parsing": None, "languages": {}}
    assert client.get("/repositories/999/overview").status_code == 404


def test_overview_combines_ingestion_and_parse_statistics(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    before = client.get(prefix + "/overview").json()
    assert before["repository"]["status"] == "ingested"
    assert before["snapshot"]["file_count"] == 2
    assert before["snapshot"]["line_count"] == 5
    assert before["parsing"] is None
    parsed = client.post(prefix + "/parse").json()
    after = client.get(prefix + "/overview").json()
    assert after["parsing"] == parsed
    assert after["repository"]["status"] == "parsed"
    assert after["parsing"]["classes"] == 1
    assert after["parsing"]["methods"] == 1
    assert after["parsing"]["parse_error_files"] == 1
    assert after["snapshot"]["commit_sha"] == after["parsing"]["commit_sha"]


def test_file_inspection_before_and_after_parsing(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    file = app_file(client, ingested_repository)
    url = prefix + f"/files/{file['id']}"
    response = client.get(url)
    assert response.status_code == 200
    detail = response.json()
    assert detail["file"] == file
    assert detail["source"] == "import os\nclass Service:\n    def run(self):\n        return True\n"
    assert detail["commit_sha"] == "a" * 40
    assert detail["github_url"] == f"https://github.com/example/demo/blob/{'a' * 40}/app.py"
    assert detail["parsing"] is None
    assert detail["symbols"] == {"items": [], "total": None, "limit": 100, "offset": 0}
    client.post(prefix + "/parse")
    parsed = client.get(url).json()
    assert parsed["parsing"] == {"file_id": file["id"], "has_parse_errors": False, "symbol_count": 3}
    assert parsed["symbols"]["total"] == 3
    assert [s["name"] for s in parsed["symbols"]["items"]] == ["import os", "Service", "run"]


def test_file_symbol_pagination_and_validation(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    file = app_file(client, ingested_repository)
    url = prefix + f"/files/{file['id']}"
    full = client.get(url).json()["symbols"]["items"]
    page = client.get(url, params={"limit": 1, "offset": 1}).json()["symbols"]
    assert page == {"items": full[1:2], "total": 3, "limit": 1, "offset": 1}
    assert client.get(url, params={"offset": 99}).json()["symbols"]["items"] == []
    for params in [{"limit": 0}, {"limit": 501}, {"offset": -1}]:
        assert client.get(url, params=params).status_code == 422


def test_symbol_snippet_and_commit_pinned_line_link(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    method = client.get(prefix + "/symbols", params={"kind": "method"}).json()[0]
    response = client.get(prefix + f"/symbols/{method['id']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["symbol"] == method
    assert detail["file"] == app_file(client, ingested_repository)
    assert detail["source"] == "    def run(self):\n        return True"
    assert detail["github_url"] == f"https://github.com/example/demo/blob/{'a' * 40}/app.py#L3-L4"
    assert detail["has_parse_errors"] is False


def test_detail_endpoints_enforce_repository_scope(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    file_id = app_file(client, ingested_repository)["id"]
    symbol_id = client.get(prefix + "/symbols").json()[0]["id"]
    other = client.post("/repositories", json={"github_url": "https://github.com/example/other"}).json()["id"]
    for repository_id in [other, 999]:
        assert client.get(f"/repositories/{repository_id}/files/{file_id}").status_code == 404
        assert client.get(f"/repositories/{repository_id}/symbols/{symbol_id}").status_code == 404
    assert client.get(prefix + "/files/999").status_code == 404
    assert client.get(prefix + "/symbols/999").status_code == 404


def test_empty_file_is_distinct_from_unparsed_file(client, ingested_repository):
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.path == "app.py"))
        file.source = ""
        file.line_count = 0
        file_id = file.id
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    detail = client.get(prefix + f"/files/{file_id}").json()
    assert detail["source"] == ""
    assert detail["parsing"]["has_parse_errors"] is False
    assert detail["symbols"]["total"] == 0
    assert detail["symbols"]["items"] == []


def test_recovered_symbols_carry_syntax_error_flag(client, ingested_repository):
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.path == "broken.py"))
        file.source = "def valid():\n    return 1\n\ndef broken(:\n"
        file_id = file.id
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    detail = client.get(prefix + f"/files/{file_id}").json()
    assert detail["parsing"]["has_parse_errors"] is True
    symbol = next(s for s in detail["symbols"]["items"] if s["name"] == "valid")
    assert client.get(prefix + f"/symbols/{symbol['id']}").json()["has_parse_errors"] is True


def test_source_links_encode_paths_and_snippets_use_parser_line_boundaries(client, ingested_repository):
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.path == "app.py"))
        file.path = "src/odd #name.py"
        file.source = 'text = "first\u2028second"\ndef actual():\n    return text\n'
        file_id = file.id
        session.commit()
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    detail = client.get(prefix + f"/files/{file_id}").json()
    assert detail["github_url"].endswith("/src/odd%20%23name.py")
    symbol = detail["symbols"]["items"][0]
    snippet = client.get(prefix + f"/symbols/{symbol['id']}").json()
    assert snippet["source"] == "def actual():\n    return text"
    assert snippet["github_url"].endswith("/src/odd%20%23name.py#L2-L3")


def test_overview_and_inspection_survive_restart(client, ingested_repository, database_url):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    file_id = app_file(client, ingested_repository)["id"]
    overview = client.get(prefix + "/overview").json()
    detail = client.get(prefix + f"/files/{file_id}").json()
    with TestClient(create_app(database_url)) as restarted:
        assert restarted.get(prefix + "/overview").json() == overview
        assert restarted.get(prefix + f"/files/{file_id}").json() == detail


def test_file_and_symbols_use_same_read_snapshot_during_a_write(client, ingested_repository, database_url):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    file_id = app_file(client, ingested_repository)["id"]
    engine = client.app.state.sessions.kw["bind"]
    database_path = make_url(database_url).database
    # WAL lets another connection commit while the API holds its read snapshot.
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    changed = False
    def replace_between_queries(connection, cursor, statement, parameters, context, many):
        nonlocal changed
        if not changed and "FROM source_files JOIN repositories" in statement:
            changed = True
            with sqlite3.connect(database_path) as writer:
                writer.execute("UPDATE source_files SET source = 'changed source' WHERE id = ?", (file_id,))
                writer.execute("UPDATE symbols SET name = 'changed symbol' WHERE file_id = ?", (file_id,))
    event.listen(engine, "after_cursor_execute", replace_between_queries)
    try:
        detail = client.get(prefix + f"/files/{file_id}").json()
        assert changed
        assert detail["source"].startswith("import os")
        assert [s["name"] for s in detail["symbols"]["items"]] == ["import os", "Service", "run"]
    finally:
        event.remove(engine, "after_cursor_execute", replace_between_queries)
