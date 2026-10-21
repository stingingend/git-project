from contextlib import asynccontextmanager
import os
import threading
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, create_database
from .ingestion import IngestionError, ingest_repository
from .models import FileParse, ParseSnapshot, Repository, RepositorySnapshot, SourceFile, Symbol
from .parsing import ParsingError, parse_repository
from .schemas import (FileParseRead, FileRead, ParseSnapshotRead, RepositoryCreate,
                      RepositoryRead, SnapshotRead, SymbolRead)


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

    application = FastAPI(title="CodeAtlas", version="0.4.0", lifespan=lifespan)
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
            raise HTTPException(409, "Another ingestion or parse is running. Try again when it finishes.")
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

    @application.post("/repositories/{repository_id}/parse", response_model=ParseSnapshotRead)
    def parse(repository_id: int, session: Session = Depends(get_session)):
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise HTTPException(404, "Repository not found.")
        # Parsing and ingestion both replace snapshot data; they share one lock.
        if not application.state.ingestion_lock.acquire(blocking=False):
            raise HTTPException(409, "Another ingestion or parse is running. Try again when it finishes.")
        try:
            if session.get(RepositorySnapshot, repository_id) is None:
                raise HTTPException(409, "Ingest this repository before parsing its source.")
            parsed = parse_repository(session, repository)
            session.commit()
            return parsed
        except ParsingError as exc:
            session.rollback()
            raise HTTPException(422, str(exc)) from exc
        finally:
            application.state.ingestion_lock.release()

    @application.get("/repositories/{repository_id}/parse", response_model=ParseSnapshotRead)
    def get_parse(repository_id: int, session: Session = Depends(get_session)):
        parsed = session.get(ParseSnapshot, repository_id)
        if parsed is None:
            raise HTTPException(404, "No parsed snapshot found.")
        return parsed

    @application.get("/repositories/{repository_id}/parse/files", response_model=list[FileParseRead])
    def list_file_parses(repository_id: int, session: Session = Depends(get_session)):
        if session.get(ParseSnapshot, repository_id) is None:
            raise HTTPException(404, "No parsed snapshot found.")
        return session.scalars(select(FileParse).join(SourceFile).where(
            SourceFile.repository_id == repository_id).order_by(SourceFile.path)).all()

    @application.get("/repositories/{repository_id}/symbols", response_model=list[SymbolRead])
    def list_symbols(repository_id: int, file_id: int | None = None,
                     kind: Literal["function", "class", "method", "import"] | None = None,
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                     session: Session = Depends(get_session)):
        if session.get(Repository, repository_id) is None:
            raise HTTPException(404, "Repository not found.")
        query = select(Symbol).join(SourceFile).where(SourceFile.repository_id == repository_id)
        if file_id is not None:
            query = query.where(Symbol.file_id == file_id)
        if kind is not None:
            query = query.where(Symbol.symbol_type == kind)
        return session.scalars(query.order_by(SourceFile.path, Symbol.start_line, Symbol.id)
                               .limit(limit).offset(offset)).all()

    return application


app = create_app()
