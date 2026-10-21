from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text

from app.database import create_database
from app.migrations import upgrade_database
from app.migrations.baseline import Base


def test_fresh_and_repeat_upgrade(database_url):
    engine, _ = create_database(database_url)
    try:
        upgrade_database(engine)
        upgrade_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "002_job_history"
        assert "ix_index_jobs_repository_created" in {index["name"] for index in inspect(engine).get_indexes("index_jobs")}
    finally:
        engine.dispose()


def test_adopts_previous_database_without_changing_records(database_url):
    engine, _ = create_database(database_url)
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(Base.metadata.tables["repositories"].insert(), dict(id=71,
                github_url="https://github.com/example/legacy", owner="example", name="legacy",
                status="registered", created_at=datetime.now(timezone.utc)))
        upgrade_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT name FROM repositories WHERE id=71")) == "legacy"
    finally:
        engine.dispose()


def test_incompatible_database_is_not_stamped(database_url):
    engine, _ = create_database(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE repositories (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="incompatible table repositories"):
            upgrade_database(engine)
        assert "repository_snapshots" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
