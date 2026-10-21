import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'metadata.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as client:
        yield client
