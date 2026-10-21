from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.database import create_database


def test_readiness_checks_database_and_does_not_leak_failure(client):
    assert client.get("/ready").json() == {"status": "ready"}
    engine = client.app.state.sessions.kw["bind"]
    def unavailable(*args):
        raise OperationalError("private connection details", {}, Exception("secret"))
    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable."}
        assert client.get("/health").json() == {"status": "ok"}
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)


def test_postgres_urls_select_psycopg_without_connecting():
    import pytest
    pytest.importorskip("psycopg")
    for scheme in ("postgres", "postgresql", "postgresql+psycopg"):
        engine, _ = create_database(f"{scheme}://user:password@localhost/db")
        try:
            assert engine.url.drivername == "postgresql+psycopg"
        finally:
            engine.dispose()
