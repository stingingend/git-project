import hashlib
import hmac
import json
import os
import re

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .jobs import IndexingBusy
from .models import PullRequestReport, Repository
from .pull_requests import report_read


class PullRequestInput(BaseModel):
    number: int = Field(ge=1, le=10_000_000)


def valid_signature(secret, body, signature):
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def install(application, get_session):
    def submit(repository_id, number, delivery_id=None):
        try:
            return application.state.pull_request_worker.submit(repository_id, number, delivery_id)
        except IndexingBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except (RuntimeError, SQLAlchemyError) as exc:
            raise HTTPException(503, "Could not start PR analysis. Try again.") from exc

    @application.post("/repositories/{repository_id}/pull-requests", status_code=202)
    def start(repository_id: int, body: PullRequestInput, session=Depends(get_session)):
        if session.get(Repository, repository_id) is None:
            raise HTTPException(404, "Repository not found.")
        return submit(repository_id, body.number)

    @application.get("/repositories/{repository_id}/pull-requests")
    def history(repository_id: int, limit: int = Query(10, ge=1, le=50), session=Depends(get_session)):
        if session.get(Repository, repository_id) is None:
            raise HTTPException(404, "Repository not found.")
        reports = session.scalars(select(PullRequestReport).where(PullRequestReport.repository_id == repository_id)
                                 .order_by(PullRequestReport.created_at.desc()).limit(limit)).all()
        return [report_read(report) for report in reports]

    @application.get("/repositories/{repository_id}/pull-requests/{report_id}")
    def get_report(repository_id: int, report_id: str, session=Depends(get_session)):
        report = session.get(PullRequestReport, report_id)
        if report is None or report.repository_id != repository_id:
            raise HTTPException(404, "PR report not found in this repository.")
        return report_read(report)

    @application.post("/webhooks/github", status_code=202)
    async def webhook(request: Request, session=Depends(get_session)):
        secret = os.getenv("CODEATLAS_WEBHOOK_SECRET", "")
        if len(secret) < 16:
            raise HTTPException(503, "GitHub webhook secret is not configured (minimum 16 characters).")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413, "Webhook payload exceeds the size limit.")
        if not valid_signature(secret, bytes(body), request.headers.get("X-Hub-Signature-256", "")):
            raise HTTPException(401, "Invalid webhook signature.")
        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return {"status": "pong"}
        if event != "pull_request":
            return {"status": "ignored"}
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
            if payload.get("action") not in {"opened", "reopened", "synchronize"}:
                return {"status": "ignored"}
            full_name = payload["repository"]["full_name"]
            private = payload["repository"]["private"]
            number = payload["number"]
            if type(number) is not int or not 1 <= number <= 10_000_000 or not isinstance(full_name, str):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "Invalid pull request webhook payload.")
        if private:
            raise HTTPException(403, "Only public repositories are supported.")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", delivery_id):
            raise HTTPException(422, "A valid GitHub delivery ID is required.")
        repository = session.scalar(select(Repository).where(Repository.github_url == "https://github.com/" + full_name.lower()))
        if repository is None:
            raise HTTPException(404, "Register this public repository before using its webhook.")
        return submit(repository.id, number, delivery_id)
