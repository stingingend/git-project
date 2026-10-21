"""One local background worker; durable records, no distributed queue yet."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import select, update

from .ingestion import IngestionError, ingest_repository
from .models import IndexJob, Repository
from .parsing import ParsingError, parse_repository

ACTIVE_STATUSES = ("queued", "running")
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


class IndexingBusy(ValueError):
    pass


class IndexWorker:
    def __init__(self, sessions, lock):
        self.sessions = sessions
        self.lock = lock
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="codeatlas-index")

    def recover(self):
        # Only one API instance may own this database. A restart never silently
        # resumes a partially ingested snapshot or launches a fresh network clone.
        with self.sessions() as session:
            session.execute(update(IndexJob).where(IndexJob.status.in_(ACTIVE_STATUSES)).values(
                status="interrupted", finished_at=now(),
                error="The API restarted before indexing finished. Start indexing again."))
            session.commit()

    def submit(self, repository_id):
        if not self.lock.acquire(blocking=False):
            with self.sessions() as session:
                existing = session.scalar(select(IndexJob).where(
                    IndexJob.repository_id == repository_id, IndexJob.status.in_(ACTIVE_STATUSES))
                    .order_by(IndexJob.created_at.desc()).limit(1))
                if existing:
                    return existing
            raise IndexingBusy("Another ingestion or indexing job is running. Try again when it finishes.")
        job = None
        try:
            with self.sessions() as session:
                job = IndexJob(id=str(uuid.uuid4()), repository_id=repository_id,
                    status="queued", stage="queued", created_at=now())
                session.add(job)
                session.commit()
            self.executor.submit(self.run, job.id)
            return job
        except Exception:
            try:
                if job is not None:
                    self.fail(job.id, "The indexing worker could not start. Try again.")
            except Exception:
                logger.exception("Could not persist a worker startup failure")
            finally:
                self.lock.release()
            raise

    def fail(self, job_id, message):
        with self.sessions() as session:
            job = session.get(IndexJob, job_id)
            if job is not None:
                job.status, job.error, job.finished_at = "failed", message, now()
                session.commit()

    def run(self, job_id):
        try:
            with self.sessions() as session:
                job = session.get(IndexJob, job_id)
                job.status, job.stage, job.started_at = "running", "ingesting", now()
                session.commit()
            with self.sessions() as session:
                job = session.get(IndexJob, job_id)
                repository = session.get(Repository, job.repository_id)
                snapshot = ingest_repository(session, repository)
                job.stage, job.commit_sha = "parsing", snapshot.commit_sha
                session.commit()
            with self.sessions() as session:
                job = session.get(IndexJob, job_id)
                repository = session.get(Repository, job.repository_id)
                parsed = parse_repository(session, repository)
                job.status, job.stage, job.finished_at = "succeeded", "complete", now()
                job.commit_sha = parsed.commit_sha
                session.commit()
        except Exception as exc:
            expected = isinstance(exc, (IngestionError, ParsingError))
            if not expected:
                logger.exception("Indexing job %s failed", job_id)
            try:
                self.fail(job_id, str(exc) if expected else "Indexing failed unexpectedly. Check API logs and try again.")
            except Exception:
                logger.exception("Could not persist failure for indexing job %s", job_id)
        finally:
            self.lock.release()

    def close(self):
        # Finish the bounded in-flight operation during a graceful shutdown.
        self.executor.shutdown(wait=True)
