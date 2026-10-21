from contextlib import asynccontextmanager
import os
import threading

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, create_database
from .ingestion import IngestionError, ingest_repository
from .models import Repository, RepositorySnapshot, SourceFile
from .schemas import FileRead, RepositoryCreate, RepositoryRead, SnapshotRead


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


def create_app(database_url: str | None = None) -> FastAPI:
    engine, sessions = create_database(
        database_url or os.getenv("DATABASE_URL", "sqlite:///./codeatlas-metadata.db")
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="CodeAtlas", version="0.3.0", lifespan=lifespan)
    application.state.sessions = sessions
    application.state.ingestion_lock = threading.Lock()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/repositories", response_model=RepositoryRead, status_code=201)
    def register_repository(body: RepositoryCreate, session: Session = Depends(get_session)):
        owner, name = body.github_url.removeprefix("https://github.com/").split("/")
        repository = Repository(github_url=body.github_url, owner=owner, name=name)
        session.add(repository)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(409, "This repository is already registered.") from exc
        return repository

    @application.get("/repositories", response_model=list[RepositoryRead])
    def list_repositories(session: Session = Depends(get_session)):
        return session.scalars(select(Repository).order_by(Repository.id)).all()

    @application.get("/repositories/{repository_id}", response_model=RepositoryRead)
    def get_repository(repository_id: int, session: Session = Depends(get_session)):
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise HTTPException(404, "Repository not found.")
        return repository

    @application.post("/repositories/{repository_id}/ingest", response_model=SnapshotRead)
    def ingest(repository_id: int, session: Session = Depends(get_session)):
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise HTTPException(404, "Repository not found.")
        if not application.state.ingestion_lock.acquire(blocking=False):
            raise HTTPException(409, "Another ingestion is running. Try again when it finishes.")
        try:
            snapshot = ingest_repository(session, repository)
            session.commit()
            return snapshot
        except IngestionError as exc:
            session.rollback()
            raise HTTPException(422, str(exc)) from exc
        finally:
            application.state.ingestion_lock.release()

    @application.get("/repositories/{repository_id}/snapshot", response_model=SnapshotRead)
    def get_snapshot(repository_id: int, session: Session = Depends(get_session)):
        snapshot = session.get(RepositorySnapshot, repository_id)
        if snapshot is None:
            raise HTTPException(404, "No ingested snapshot found.")
        return snapshot

    @application.get("/repositories/{repository_id}/files", response_model=list[FileRead])
    def list_files(repository_id: int, session: Session = Depends(get_session)):
        if session.get(Repository, repository_id) is None:
            raise HTTPException(404, "Repository not found.")
        return session.scalars(select(SourceFile).where(
            SourceFile.repository_id == repository_id).order_by(SourceFile.path)).all()

    return application


app = create_app()
