"""Exercise real Git revisions and retained index identities, including FK ordering."""
import json
import subprocess
import time
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from app import parsing
from app.models import CallSite, FileIndexState, IndexChanges, SourceFile, Symbol
from test_ingestion import git_repository, local_clone, register


def commit(root, message):
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null",
                    "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-m", message], check=True, capture_output=True)


def index(client, prefix):
    assert client.post(prefix + "/ingest").status_code == 200
    response = client.post(prefix + "/parse")
    assert response.status_code == 200, response.text
    return response.json()


def saved(client):
    with client.app.state.sessions() as session:
        return {file.path: (file.id,
            [(s.id, s.name) for s in session.scalars(select(Symbol).where(Symbol.file_id == file.id))],
            [c.id for c in session.scalars(select(CallSite).where(CallSite.file_id == file.id))])
            for file in session.scalars(select(SourceFile))}


def changes(client, repo):
    with client.app.state.sessions() as session:
        row = session.get(IndexChanges, repo)
        return {key: getattr(row, key) for key in
                ("added", "changed", "removed", "unchanged", "parsed_files", "reused_files")}


def verify_diff(client, git_repository):
    # Enable actual SQLite FK checks on every connection before touching the index.
    engine = client.app.state.sessions.kw["bind"]
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    (git_repository / "src/app.py").write_text("def work(): return True\ndef run(): return work()\n")
    (git_repository / "src/bom.py").write_text("def old(): return 1\n")
    commit(git_repository, "definitions")
    repo = register(client)
    prefix = f"/repositories/{repo}"
    index(client, prefix)
    before = saved(client)
    (git_repository / "src/bom.py").write_text("def updated(): return 2\n")
    (git_repository / "src/empty.py").unlink()
    (git_repository / "new.py").write_text("def added(): return 3\n")
    commit(git_repository, "change inventory")
    with patch("app.parsing.parse_python", wraps=parsing.parse_python) as parse:
        result = index(client, prefix)
        assert sorted(call.args[1] for call in parse.call_args_list) == ["new.py", "src/bom.py"]
    after = saved(client)
    assert before["src/app.py"] == after["src/app.py"]
    assert before["src/app.py"][2]  # Contains a retained call site.
    assert before["src/bom.py"][0] == after["src/bom.py"][0]
    assert "src/empty.py" not in after
    assert result["symbol_count"] == 4
    assert changes(client, repo) == dict(added=1, changed=1, removed=1, unchanged=1, parsed_files=2, reused_files=1)


def test_git_diff_parses_only_changed_and_added_and_preserves_calls(client, local_clone, git_repository):
    verify_diff(client, git_repository)


def test_non_python_commit_reuses_all_and_publishes_new_sha(client, local_clone, git_repository):
    repo = register(client)
    prefix = f"/repositories/{repo}"
    first = index(client, prefix)
    before = saved(client)
    (git_repository / "README.md").write_text("Updated documentation")
    commit(git_repository, "docs only")
    with patch("app.parsing.parse_python", side_effect=AssertionError("Unchanged source parsed")):
        latest = index(client, prefix)
    assert latest["commit_sha"] != first["commit_sha"]
    assert saved(client) == before
    assert changes(client, repo) == dict(added=0, changed=0, removed=0, unchanged=3, parsed_files=0, reused_files=3)


def test_unchanged_importer_relinks_when_module_added_and_removed(client, local_clone, git_repository):
    (git_repository / "src/app.py").write_text("import helper\n")
    commit(git_repository, "import missing module")
    repo = register(client)
    prefix = f"/repositories/{repo}"
    index(client, prefix)
    before = saved(client)["src/app.py"]
    url = prefix + f"/files/{before[0]}/relationships?kind=imports"
    assert client.get(url).json()["items"][0]["resolution"] == "unresolved"
    (git_repository / "src/helper.py").write_text("def help(): return 1\n")
    commit(git_repository, "add target")
    with patch("app.parsing.parse_python", wraps=parsing.parse_python) as parse:
        index(client, prefix)
        assert [call.args[1] for call in parse.call_args_list] == ["src/helper.py"]
    assert client.get(url).json()["items"][0]["resolution"] == "local"
    (git_repository / "src/helper.py").unlink()
    commit(git_repository, "remove target")
    with patch("app.parsing.parse_python", side_effect=AssertionError("Unchanged source parsed")):
        index(client, prefix)
    assert client.get(url).json()["items"][0]["resolution"] == "unresolved"
    assert saved(client)["src/app.py"] == before


def test_exact_scopes_survive_cache_and_version_change_forces_parse(client, ingested_repository, monkeypatch):
    prefix = f"/repositories/{ingested_repository}"
    with client.app.state.sessions() as session:
        file = session.scalar(select(SourceFile).where(SourceFile.path == "app.py"))
        file.source = "def duplicate():\n    def inner(): pass\ndef duplicate():\n    def inner(): pass\n"
        session.commit()
    assert client.post(prefix + "/parse").status_code == 200
    before = saved(client)
    url = prefix + f"/files/{before['app.py'][0]}/relationships?kind=contains"
    edges = client.get(url).json()["items"]
    with patch("app.parsing.parse_python", side_effect=AssertionError("Cached source parsed")):
        assert client.post(prefix + "/parse").status_code == 200
    after_edges = client.get(url).json()["items"]
    assert [(edge["source_symbol_id"], edge["target_symbol_id"]) for edge in after_edges] == [
        (edge["source_symbol_id"], edge["target_symbol_id"]) for edge in edges]
    assert saved(client) == before
    monkeypatch.setattr(parsing, "INDEX_FORMAT_VERSION", "next-version")
    with patch("app.parsing.parse_python", wraps=parsing.parse_python) as parse:
        assert client.post(prefix + "/parse").status_code == 200
        assert parse.call_count == 2


def test_missing_or_corrupt_cache_is_rebuilt(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    assert client.post(prefix + "/parse").status_code == 200
    with client.app.state.sessions() as session:
        states = session.scalars(select(FileIndexState)).all()
        session.delete(states[0])  # Upgrade from an older installation.
        states[1].structure = json.dumps(dict(symbols=[], parents=[999]))
        session.commit()
    with patch("app.parsing.parse_python", wraps=parsing.parse_python) as parse:
        assert client.post(prefix + "/parse").status_code == 200
        assert parse.call_count == 2


def finish(client, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            assert job["status"] == "succeeded", job
            return job
        time.sleep(.01)
    pytest.fail("Indexing did not finish")


def test_job_summaries_are_durable_per_run(client, local_clone):
    repo = register(client)
    first = finish(client, client.post(f"/repositories/{repo}/jobs").json()["id"])
    second = finish(client, client.post(f"/repositories/{repo}/jobs").json()["id"])
    assert first["changes"] == dict(added=3, changed=0, removed=0, unchanged=0, parsed_files=3, reused_files=0)
    assert second["changes"] == dict(added=0, changed=0, removed=0, unchanged=3, parsed_files=0, reused_files=3)
    assert client.get(f"/jobs/{first['id']}").json()["changes"] == first["changes"]
    history = client.get("/jobs").json()
    assert [row["changes"] for row in history] == [second["changes"], first["changes"]]
