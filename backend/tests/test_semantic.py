from unittest.mock import patch

import pytest
from sqlalchemy import select

from app import semantic
from app.models import SearchDocument, SourceFile


def encode(texts):
    # Deterministic test provider; production always uses the pinned local model.
    return [[float("token" in text.lower()), float("database" in text.lower()), 0.1] + [0.0] * 253 for text in texts]


def verify_semantic(client, repository_id, monkeypatch):
    prefix = f"/repositories/{repository_id}"
    with client.app.state.sessions() as session:
        files = session.scalars(select(SourceFile).where(SourceFile.repository_id == repository_id).order_by(SourceFile.id)).all()
        files[0].source = "def validate_token(token):\n    return token == 'valid'\n"
        files[0].content_hash = "1" * 64
        files[1].source = "def query_database(): return []\n"
        files[1].content_hash = "2" * 64
        session.commit()
    assert client.post(prefix + "/parse").status_code == 200
    monkeypatch.setattr(semantic, "encode", encode)
    assert client.get(prefix + "/semantic").json()["ready"] is False
    assert client.get(prefix + "/semantic/search", params={"q": "token validation"}).status_code == 409
    first = client.post(prefix + "/semantic")
    assert first.status_code == 200, first.text
    assert first.json()["embedded"] == 4
    assert client.get(prefix + "/semantic").json()["ready"] is True
    with patch("app.semantic.encode", side_effect=AssertionError("Recomputed unchanged embeddings")):
        second = client.post(prefix + "/semantic").json()
        assert second["embedded"] == 0 and second["reused"] == 4
    found = client.get(prefix + "/semantic/search", params={"q": "token validation"}).json()
    assert found["commit_sha"] == "a" * 40
    assert found["items"][0]["path"] == files[0].path
    assert found["items"][0]["github_url"].startswith("https://github.com/")
    assert "/blob/" + "a" * 40 + "/" in found["items"][0]["github_url"]
    assert found["items"][0]["score"] > .9
    assert client.post(prefix + "/parse").status_code == 200
    assert client.get(prefix + "/semantic").json()["ready"] is False
    assert client.post(prefix + "/semantic").json()["reused"] == 4


def test_semantic_build_reuse_retrieval_and_invalidation(client, ingested_repository, monkeypatch):
    verify_semantic(client, ingested_repository, monkeypatch)


def test_embedding_failure_rolls_back_and_releases_lock(client, ingested_repository, monkeypatch):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    monkeypatch.setattr(semantic, "encode", lambda _: (_ for _ in ()).throw(RuntimeError("download failure")))
    assert client.post(prefix + "/semantic").status_code == 503
    assert not client.app.state.ingestion_lock.locked()
    with client.app.state.sessions() as session:
        assert session.scalars(select(SearchDocument)).all() == []
    assert client.get(prefix + "/semantic").json()["ready"] is False


def test_semantic_limits_and_repository_scope(client, ingested_repository, monkeypatch):
    prefix = f"/repositories/{ingested_repository}"
    client.post(prefix + "/parse")
    monkeypatch.setattr(semantic, "MAX_DOCUMENTS", 1)
    assert client.post(prefix + "/semantic").status_code == 422
    assert client.get("/repositories/999/semantic").status_code == 404
    assert client.get(prefix + "/semantic/search", params={"q": "x"}).status_code == 422
    with client.app.state.ingestion_lock:
        assert client.post(prefix + "/semantic").status_code == 409
