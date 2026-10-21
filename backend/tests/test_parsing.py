from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import IntegrityError

from app.main import create_app


def test_parse_saved_source_and_inspect_symbols(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    response = client.post(prefix + "/parse")
    assert response.status_code == 200, response.text
    parsed = response.json()
    assert parsed["commit_sha"] == "a" * 40
    assert parsed["file_count"] == 2
    assert parsed["classes"] == 1
    assert parsed["methods"] == 1
    assert parsed["imports"] == 1
    assert parsed["parse_error_files"] == 1
    assert parsed["parsed_at"].endswith("Z")
    assert client.get(prefix).json()["status"] == "parsed"
    assert client.get(prefix + "/parse").json() == parsed
    symbols = client.get(prefix + "/symbols").json()
    assert len(symbols) == parsed["symbol_count"]
    assert len(client.get(prefix + "/symbols", params={"kind": "method"}).json()) == 1
    files = client.get(prefix + "/files").json()
    app_file = next(file for file in files if file["path"] == "app.py")
    assert len(client.get(prefix + "/symbols", params={"file_id": app_file["id"]}).json()) == 3
    page = client.get(prefix + "/symbols", params={"limit": 1, "offset": 1}).json()
    assert page == symbols[1:2]
    assert client.get(prefix + "/symbols", params={"limit": 501}).status_code == 422
    assert client.get(prefix + "/symbols", params={"kind": "unknown"}).status_code == 422
    file_results = client.get(prefix + "/parse/files").json()
    assert [file["has_parse_errors"] for file in file_results] == [False, True]
    assert client.post(prefix + "/parse").status_code == 200
    assert len(client.get(prefix + "/symbols").json()) == len(symbols)


def test_parsed_results_survive_restart(client, ingested_repository, database_url):
    prefix = f"/repositories/{ingested_repository}"
    parsed = client.post(prefix + "/parse").json()
    symbols = client.get(prefix + "/symbols").json()
    with TestClient(create_app(database_url)) as restarted:
        assert restarted.get(prefix + "/parse").json() == parsed
        assert restarted.get(prefix + "/symbols").json() == symbols


def test_scope_missing_snapshot_and_shared_processing_lock(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    second = client.post("/repositories", json={"github_url": "https://github.com/example/other"}).json()["id"]
    assert client.get(f"/repositories/{second}/symbols").json() == []
    assert client.post(f"/repositories/{second}/parse").status_code == 409
    with client.app.state.ingestion_lock:
        assert client.post(prefix + "/parse").status_code == 409
    for path in ["parse", "parse/files", "symbols"]:
        assert client.get(f"/repositories/999/{path}").status_code == 404
    assert client.post("/repositories/999/parse").status_code == 404


def test_symbol_limit_preserves_previous_results(client, ingested_repository, monkeypatch):
    prefix = f"/repositories/{ingested_repository}"
    parsed = client.post(prefix + "/parse").json()
    symbols = client.get(prefix + "/symbols").json()
    monkeypatch.setattr("app.parsing.MAX_SYMBOLS", 1)
    assert client.post(prefix + "/parse").status_code == 422
    assert client.get(prefix + "/parse").json() == parsed
    assert client.get(prefix + "/symbols").json() == symbols
    assert not client.app.state.ingestion_lock.locked()


def test_database_failure_rolls_back_parse_replacement(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    parsed = client.post(prefix + "/parse").json()
    symbols = client.get(prefix + "/symbols").json()
    engine = client.app.state.sessions.kw["bind"]
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TRIGGER reject_symbols BEFORE INSERT ON symbols "
                                  "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END")
    try:
        with pytest.raises(IntegrityError):
            client.post(prefix + "/parse")
        assert client.get(prefix + "/parse").json() == parsed
        assert client.get(prefix + "/symbols").json() == symbols
        assert not client.app.state.ingestion_lock.locked()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER reject_symbols")
