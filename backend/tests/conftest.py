import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import create_app
from app.models import Repository, RepositorySnapshot, SourceFile, IndexChanges


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'metadata.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client


@pytest.fixture
def ingested_repository(client):
    response = client.post("/repositories", json={"github_url": "https://github.com/example/demo"})
    repository_id = response.json()["id"]
    with client.app.state.sessions() as session:
        session.get(Repository, repository_id).status = "ingested"
        session.add(RepositorySnapshot(repository_id=repository_id, commit_sha="a" * 40,
            default_branch="main", ingested_at=datetime.now(timezone.utc), file_count=2,
            skipped_files=0, line_count=5))
        session.add_all([
            SourceFile(repository_id=repository_id, path="app.py", content_hash="b" * 64,
                line_count=4, source="import os\nclass Service:\n    def run(self):\n        return True\n"),
            SourceFile(repository_id=repository_id, path="broken.py", content_hash="c" * 64,
                line_count=1, source="def broken(:\n"),
        ])
        session.add(IndexChanges(repository_id=repository_id, added=2, changed=0, removed=0, unchanged=0))
        session.commit()
    return repository_id
