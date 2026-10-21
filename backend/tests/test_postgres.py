"""Opt-in integration checks; each test owns only its random, isolated schema."""
from datetime import datetime, timezone
import os
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select, text

from app.database import create_database
from app.main import create_app
from app.models import RepositorySnapshot, SourceFile, IndexChanges
from app.parsing import clear_parse_results
from test_ingestion import git_repository, local_clone


@pytest.fixture
def postgres_client():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to run PostgreSQL integration tests.")
    admin, _ = create_database(url)
    assert admin.dialect.name == "postgresql", "TEST_POSTGRES_URL must point to PostgreSQL"
    schema = "codeatlas_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = admin.url.update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        with TestClient(create_app(scoped_url.render_as_string(hide_password=False))) as client:
            yield client
    finally:
        # schema is generated above, never read from an environment variable.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def seed(client):
    repo = client.post("/repositories", json={"github_url": "https://github.com/example/postgres"}).json()
    prefix = f"/repositories/{repo['id']}"
    with client.app.state.sessions() as session:
        session.add(RepositorySnapshot(repository_id=repo["id"], commit_sha="a" * 40,
            default_branch="main", ingested_at=datetime.now(timezone.utc), file_count=2,
            skipped_files=0, line_count=5))
        session.add_all([
            SourceFile(repository_id=repo["id"], path="pkg/main.py", content_hash="b" * 64,
                line_count=4, source="from .helper import work\nclass Service:\n    def run(self):\n        return work()\n"),
            SourceFile(repository_id=repo["id"], path="pkg/helper.py", content_hash="c" * 64,
                line_count=1, source="def work(): return True\n"),
        ])
        session.add(IndexChanges(repository_id=repo["id"], added=2, changed=0, removed=0, unchanged=0))
        session.commit()
    return prefix


def test_postgres_index_search_graph_replacement_and_rollback(postgres_client):
    client = postgres_client
    assert client.get("/ready").status_code == 200
    prefix = seed(client)
    assert client.post(prefix + "/parse").status_code == 200
    found = client.get(prefix + "/search", params={"q": "Service.run"}).json()
    assert found["total"] == 1
    assert found["items"][0]["symbol"]["name"] == "run"
    file_id = found["items"][0]["symbol"]["file_id"]
    url = prefix + f"/files/{file_id}/relationships"
    edges = client.get(url, params={"kind": "imports"}).json()
    assert edges["items"][0]["target_path"] == "pkg/helper.py"
    assert edges["items"][0]["resolution"] == "local"
    graph = client.get(prefix + f"/files/{file_id}/graph").json()
    assert graph["total_neighbors"] == 1
    assert graph["edges"][0]["count"] == 1
    calls = client.get(prefix + f"/files/{file_id}/calls").json()
    assert calls["ready"] and calls["total"] == 1
    assert calls["items"][0]["expression"] == "work"
    # Imported work is outside this phase's same-file definition matcher.
    assert calls["items"][0]["resolution"] == "unresolved"
    # Real PostgreSQL foreign keys require edges to be deleted before symbols.
    assert client.post(prefix + "/parse").status_code == 200
    symbols = client.get(prefix + "/symbols").json()
    engine = client.app.state.sessions.kw["bind"]
    def fail_graph(connection, cursor, statement, *args):
        if statement.startswith("INSERT INTO relationships"):
            raise RuntimeError("simulated graph write failure")
    event.listen(engine, "before_cursor_execute", fail_graph)
    try:
        with pytest.raises(RuntimeError, match="graph write failure"):
            client.post(prefix + "/parse")
    finally:
        event.remove(engine, "before_cursor_execute", fail_graph)
    assert client.get(prefix + "/symbols").json() == symbols
    assert client.get(url, params={"kind": "imports"}).json()["total"] == edges["total"]
    # A second app instance sees the committed index without rebuilding it.
    with TestClient(create_app(engine.url.render_as_string(hide_password=False))) as restarted:
        assert restarted.get(prefix + "/symbols").json() == symbols
    with client.app.state.sessions() as session:
        clear_parse_results(session, int(prefix.split("/")[-1]))
        session.commit()
    assert client.get(url).json()["ready"] is False
    assert client.get(prefix + f"/files/{file_id}/calls").json()["ready"] is False
    assert client.get(prefix + "/search", params={"q": "Service"}).json()["items"] == []


def test_postgres_index_reads_keep_one_snapshot(postgres_client):
    client = postgres_client
    prefix = seed(client)
    client.post(prefix + "/parse")
    file_id = client.get(prefix + "/search", params={"q": "Service.run"}).json()["items"][0]["symbol"]["file_id"]
    engine = client.app.state.sessions.kw["bind"]
    changed = False
    def replace_between_queries(connection, cursor, statement, *args):
        nonlocal changed
        if not changed and "FROM source_files JOIN repositories" in statement:
            changed = True
            with engine.begin() as writer:
                writer.execute(text("UPDATE source_files SET source = 'changed source' WHERE id = :id"), {"id": file_id})
                writer.execute(text("UPDATE symbols SET name = 'changed symbol' WHERE file_id = :id"), {"id": file_id})
    event.listen(engine, "after_cursor_execute", replace_between_queries)
    try:
        detail = client.get(prefix + f"/files/{file_id}").json()
        assert changed
        assert detail["source"].startswith("from .helper")
        assert [s["name"] for s in detail["symbols"]["items"]] == ["from .helper import work", "Service", "run"]
    finally:
        event.remove(engine, "after_cursor_execute", replace_between_queries)


def test_postgres_background_job_uses_its_own_sessions(postgres_client, monkeypatch):
    import time
    client = postgres_client
    prefix = seed(client)
    monkeypatch.setattr("app.jobs.ingest_repository",
        lambda session, repo: session.get(RepositorySnapshot, repo.id))
    response = client.post(prefix + "/jobs")
    assert response.status_code == 202
    job_id = response.json()["id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            break
        time.sleep(0.01)
    assert job["status"] == "succeeded", job
    assert job["commit_sha"] == "a" * 40
    assert client.get(prefix + "/search", params={"q": "Service.run"}).json()["total"] == 1
    assert client.get("/jobs").json()[0]["id"] == job_id


def test_postgres_incremental_diff_and_foreign_keys(postgres_client, local_clone, git_repository):
    from test_incremental import verify_diff
    verify_diff(postgres_client, git_repository)
