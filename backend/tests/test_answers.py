from unittest.mock import patch

from test_semantic import encode
from app import answers, semantic


def prepare(client, repository, monkeypatch):
    prefix = f"/repositories/{repository}"
    client.post(prefix + "/parse")
    monkeypatch.setattr(semantic, "encode", encode)
    assert client.post(prefix + "/semantic").status_code == 200
    return prefix


def test_answers_have_current_source_citations(client, ingested_repository, monkeypatch):
    prefix = prepare(client, ingested_repository, monkeypatch)
    response = client.post(prefix + "/questions", json={"question": "Where is Service defined?"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "source_findings"
    assert result["citations"]
    assert result["commit_sha"] == "a" * 40
    assert all("/blob/" + "a" * 40 + "/" in citation["github_url"] for citation in result["citations"])
    assert all(citation["quote"] for citation in result["citations"])


def test_generation_is_opt_in_and_failure_falls_back(client, ingested_repository, monkeypatch):
    prefix = prepare(client, ingested_repository, monkeypatch)
    with patch("app.answers.generate", side_effect=AssertionError("Unexpected model request")):
        assert client.post(prefix + "/questions", json={"question": "Service"}).json()["mode"] == "source_findings"
    with patch("app.answers.generate", side_effect=ValueError("invalid citations")):
        result = client.post(prefix + "/questions", json={"question": "Service", "generate": True}).json()
    assert result["mode"] == "source_findings" and result["notice"]


def test_generated_citations_are_validated(monkeypatch):
    monkeypatch.setenv("CODEATLAS_GENERATION_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("CODEATLAS_GENERATION_MODEL", "test-model")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _): return b'{"choices":[{"message":{"content":"Made up [99]"}}]}'
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr(answers, "build_opener", lambda *_: Opener())
    import pytest
    with pytest.raises(ValueError, match="invalid citations"):
        answers.generate("question", [{"id": 1}])
    monkeypatch.setenv("CODEATLAS_GENERATION_URL", "http://external.example/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        answers.generate("question", [{"id": 1}])


def test_question_validation_and_missing_semantic_index(client, ingested_repository):
    prefix = f"/repositories/{ingested_repository}"
    assert client.post(prefix + "/questions", json={"question": "x"}).status_code == 422
    assert client.post(prefix + "/questions", json={"question": "Where?"}).status_code == 409
