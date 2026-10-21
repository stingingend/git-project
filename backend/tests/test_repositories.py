import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_register_list_and_retrieve_repository(client):
    assert client.get("/repositories").json() == []
    response = client.post("/repositories", json={"github_url": " https://github.com/Pallets/Flask.git/ "})
    assert response.status_code == 201
    repository = response.json()
    assert repository["github_url"] == "https://github.com/pallets/flask"
    assert repository["owner"] == "pallets"
    assert repository["name"] == "flask"
    assert repository["status"] == "registered"
    assert repository["created_at"].endswith("Z")
    assert client.get("/repositories").json() == [repository]
    assert client.get(f"/repositories/{repository['id']}").json() == repository


def test_record_survives_application_restart(database_url):
    with TestClient(create_app(database_url)) as first_client:
        response = first_client.post("/repositories", json={"github_url": "https://github.com/pallets/flask"})
        assert response.status_code == 201
        repository = response.json()
    with TestClient(create_app(database_url)) as restarted_client:
        assert restarted_client.get("/repositories").json() == [repository]


def test_duplicate_url_rolls_back_and_session_remains_usable(client):
    assert client.post("/repositories", json={"github_url": "https://github.com/pallets/flask"}).status_code == 201
    duplicate = client.post("/repositories", json={"github_url": "https://github.com/Pallets/Flask.git"})
    assert duplicate.status_code == 409
    assert client.post("/repositories", json={"github_url": "https://github.com/pallets/click"}).status_code == 201
    assert len(client.get("/repositories").json()) == 2


@pytest.mark.parametrize("value", [
    "http://github.com/owner/repo", "https://github.com.evil.com/owner/repo",
    "https://user@github.com/owner/repo", "https://github.com/owner/repo/tree/main",
    "https://github.com/owner/repo?ref=main", "https://github.com/owner/repo#readme",
    "file:///tmp/repo", "https://github.com/owner/..", "https://github.com/owner/.git",
])
def test_invalid_urls_are_rejected_without_writing(client, value):
    assert client.post("/repositories", json={"github_url": value}).status_code == 422
    assert client.get("/repositories").json() == []


def test_missing_repository_and_invalid_payload(client):
    assert client.get("/repositories/999").status_code == 404
    assert client.post("/repositories", json={}).status_code == 422
    assert client.post("/repositories", json={"github_url": "https://github.com/a/b", "status": "indexed"}).status_code == 422
    assert client.get("/repositories").json() == []
