from datetime import datetime, timezone
import hashlib
import hmac
import json
import threading
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import JobTarget, PullRequestReport, RepositorySnapshot
from app.pull_requests import changed_base_lines, fetch_pull_request, PullRequestError
from test_analysis import seed


def payload(number=42, base="a" * 40):
    return dict(number=number, title="Change leaf", base_sha=base, head_sha="b" * 40,
        github_url=f"https://github.com/example/demo/pull/{number}", files=[dict(filename="c.py",
            status="modified", additions=1, deletions=1, patch="@@ -1,3 +1,3 @@\n import a\n def leaf():\n-    if True: return 1\n+    if True: return 2")])


def finished(client, prefix, report_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        report = client.get(prefix + f"/pull-requests/{report_id}").json()
        if report["status"] not in ("queued", "running"):
            return report
        time.sleep(.01)
    raise AssertionError("PR report did not finish")


def test_diff_anchors_and_public_fetch_validation(monkeypatch):
    assert changed_base_lines("@@ -5,2 +5,3 @@\n context\n+addition\n-deleted") == {5, 6}
    metadata = dict(base={"sha": "a" * 40, "repo": {"private": False}}, head={"sha": "b" * 40},
                    changed_files=1, title="test")
    responses = iter([metadata, [dict(filename="a.py")], metadata])
    monkeypatch.setattr("app.pull_requests.github_json", lambda _: next(responses))
    assert len(fetch_pull_request("example", "demo", 1)["files"]) == 1
    import pytest
    monkeypatch.setattr("app.pull_requests.github_json", lambda _: {**metadata, "changed_files": 501})
    with pytest.raises(PullRequestError, match="limited"):
        fetch_pull_request("example", "demo", 1)


def test_pr_reports_map_base_lines_and_survive_reload(client, ingested_repository, monkeypatch):
    prefix = seed(client, ingested_repository)
    monkeypatch.setattr("app.pull_requests.fetch_pull_request", lambda *args: payload())
    response = client.post(prefix + "/pull-requests", json={"number": 42})
    assert response.status_code == 202
    report = finished(client, prefix, response.json()["id"])
    assert report["status"] == "succeeded", report
    result = report["result"]
    assert result["comparable"] and result["changed_symbol_count"] == 1
    assert result["impact"]["affected_symbol_count"] == 3
    assert any(file["is_test"] for file in result["impact"]["files"])
    assert client.get(prefix + "/pull-requests").json()[0]["id"] == report["id"]
    assert client.get("/repositories/999/pull-requests/" + report["id"]).status_code == 404
    monkeypatch.setattr("app.pull_requests.fetch_pull_request", lambda *args: payload(base="c" * 40))
    other = finished(client, prefix, client.post(prefix + "/pull-requests", json={"number": 42}).json()["id"])
    assert other["result"]["requires_base_index"] and other["result"]["impact"] is None


def test_signed_webhooks_are_idempotent_and_invalid_payloads_rejected(client, ingested_repository, monkeypatch):
    seed(client, ingested_repository)
    monkeypatch.setenv("CODEATLAS_WEBHOOK_SECRET", "test-secret-at-least-16-characters")
    monkeypatch.setattr("app.pull_requests.fetch_pull_request", lambda *args: payload())
    body = json.dumps(dict(action="opened", number=42, repository={"full_name": "example/demo", "private": False})).encode()
    signature = "sha256=" + hmac.new(b"test-secret-at-least-16-characters", body, hashlib.sha256).hexdigest()
    headers = {"X-Hub-Signature-256": signature, "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": str(uuid.uuid4())}
    assert client.post("/webhooks/github", content=body).status_code == 401
    first = client.post("/webhooks/github", content=body, headers=headers)
    assert first.status_code == 202, first.text
    second = client.post("/webhooks/github", content=body, headers=headers)
    assert second.status_code == 202 and second.json()["id"] == first.json()["id"]
    assert client.post(f"/repositories/{ingested_repository}/pull-requests", json={"number": 0}).status_code == 422


def test_requested_commit_is_saved_and_delivered_to_ingestion(client, ingested_repository, monkeypatch):
    requested = []
    def ingest(session, repo, commit_sha=None):
        requested.append(commit_sha)
        snapshot = session.get(RepositorySnapshot, repo.id)
        snapshot.commit_sha = commit_sha
        return snapshot
    monkeypatch.setattr("app.jobs.ingest_repository", ingest)
    job = client.post(f"/repositories/{ingested_repository}/jobs", json={"commit_sha": "c" * 40})
    assert job.status_code == 202
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = client.get("/jobs/" + job.json()["id"]).json()
        if result["status"] not in ("queued", "running"):
            break
        time.sleep(.01)
    assert result["status"] == "succeeded", result
    assert requested == ["c" * 40]
    with client.app.state.sessions() as session:
        assert session.get(JobTarget, result["id"]).commit_sha == "c" * 40
    assert client.post(f"/repositories/{ingested_repository}/jobs", json={"commit_sha": "main; bad"}).status_code == 422


def test_pr_worker_recovery(database_url):
    with TestClient(create_app(database_url)) as client:
        repo = client.post("/repositories", json={"github_url": "https://github.com/example/demo"}).json()["id"]
        with client.app.state.sessions() as session:
            session.add(PullRequestReport(id="interrupted", repository_id=repo, number=1,
                status="running", created_at=datetime.now(timezone.utc)))
            session.commit()
    with TestClient(create_app(database_url)) as client:
        report = client.get(f"/repositories/{repo}/pull-requests/interrupted").json()
        assert report["status"] == "interrupted" and report["error"]
