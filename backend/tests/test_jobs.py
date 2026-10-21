from datetime import datetime, timezone
import threading
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from app.ingestion import IngestionError
from app.main import create_app
from app.models import IndexJob, RepositorySnapshot
from app.parsing import ParsingError, parse_repository


def finished(client, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.01)
    pytest.fail("Background job did not finish")


def test_job_returns_while_worker_runs_shared_lock_and_live_stages(client, ingested_repository, monkeypatch):
    ingest_started, release_ingest = threading.Event(), threading.Event()
    parse_started, release_parse = threading.Event(), threading.Event()
    def ingest(session, repository):
        ingest_started.set()
        assert release_ingest.wait(5)
        return session.get(RepositorySnapshot, repository.id)
    def parse(session, repository):
        parse_started.set()
        assert release_parse.wait(5)
        return parse_repository(session, repository)
    monkeypatch.setattr("app.jobs.ingest_repository", ingest)
    monkeypatch.setattr("app.jobs.parse_repository", parse)
    try:
        response = client.post(f"/repositories/{ingested_repository}/jobs")
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert ingest_started.wait(2)
        assert client.get(f"/jobs/{job_id}").json()["stage"] == "ingesting"
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        duplicate = client.post(f"/repositories/{ingested_repository}/jobs")
        assert duplicate.status_code == 202 and duplicate.json()["id"] == job_id
        other = client.post("/repositories", json={"github_url": "https://github.com/example/other-job"}).json()["id"]
        assert client.post(f"/repositories/{other}/jobs").status_code == 409
        assert client.post(f"/repositories/{ingested_repository}/ingest").status_code == 409
        assert client.post(f"/repositories/{ingested_repository}/parse").status_code == 409
        release_ingest.set()
        assert parse_started.wait(2)
        parsing = client.get(f"/jobs/{job_id}").json()
        assert parsing["stage"] == "parsing" and parsing["commit_sha"] == "a" * 40
        release_parse.set()
        job = finished(client, job_id)
        assert job["status"] == "succeeded" and job["stage"] == "complete"
        assert job["error"] is None and job["started_at"] and job["finished_at"]
        assert job["created_at"].endswith("Z")
        assert client.get(f"/repositories/{ingested_repository}/symbols").json()
        assert client.get("/jobs").json()[0] == job
    finally:
        release_ingest.set(); release_parse.set()


@pytest.mark.parametrize("failure,expected", [
    (IngestionError("Cannot clone this public repository."), "Cannot clone this public repository."),
    (RuntimeError("private server detail"), "Indexing failed unexpectedly. Check API logs and try again."),
])
def test_failed_jobs_persist_safe_errors_and_allow_retry(client, ingested_repository, monkeypatch, failure, expected):
    def fail(*args):
        raise failure
    monkeypatch.setattr("app.jobs.ingest_repository", fail)
    job_id = client.post(f"/repositories/{ingested_repository}/jobs").json()["id"]
    job = finished(client, job_id)
    assert job["status"] == "failed" and job["stage"] == "ingesting" and job["error"] == expected
    assert client.get(f"/repositories/{ingested_repository}/snapshot").json()["commit_sha"] == "a" * 40
    monkeypatch.setattr("app.jobs.ingest_repository", lambda session, repo: session.get(RepositorySnapshot, repo.id))
    retry = client.post(f"/repositories/{ingested_repository}/jobs")
    assert retry.status_code == 202
    assert finished(client, retry.json()["id"])["status"] == "succeeded"


def test_parse_failure_retains_committed_ingestion_stage(client, ingested_repository, monkeypatch):
    monkeypatch.setattr("app.jobs.ingest_repository", lambda session, repo: session.get(RepositorySnapshot, repo.id))
    def fail(*args):
        raise ParsingError("Repository exceeds the call limit.")
    monkeypatch.setattr("app.jobs.parse_repository", fail)
    response = client.post(f"/repositories/{ingested_repository}/jobs")
    job = finished(client, response.json()["id"])
    assert job["status"] == "failed" and job["stage"] == "parsing"
    assert job["commit_sha"] == "a" * 40


def test_recovery_marks_stale_jobs_interrupted_and_retains_history(client, ingested_repository, database_url):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    with client.app.state.sessions() as session:
        session.add_all(IndexJob(id=identifier, repository_id=ingested_repository, status=status,
            stage="ingesting", created_at=datetime.now(timezone.utc))
            for identifier, status in zip(ids, ("queued", "running", "failed")))
        session.commit()
    with TestClient(create_app(database_url)) as restarted:
        for identifier in ids[:2]:
            job = restarted.get(f"/jobs/{identifier}").json()
            assert job["status"] == "interrupted" and job["finished_at"]
            assert "restarted" in job["error"]
        assert restarted.get(f"/jobs/{ids[2]}").json()["status"] == "failed"
        assert len(restarted.get("/jobs").json()) == 3


def test_submission_failure_releases_lock_and_records_failure(client, ingested_repository, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("executor unavailable")
    monkeypatch.setattr(client.app.state.index_worker.executor, "submit", unavailable)
    assert client.post(f"/repositories/{ingested_repository}/jobs").status_code == 503
    assert not client.app.state.ingestion_lock.locked()
    assert client.get("/jobs").json()[0]["status"] == "failed"


def test_job_missing_ids_and_paging_validation(client):
    assert client.post("/repositories/999/jobs").status_code == 404
    assert client.get("/jobs/missing").status_code == 404
    assert client.get("/jobs").json() == []
    assert client.get("/jobs?limit=51").status_code == 422
