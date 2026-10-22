from contextlib import asynccontextmanager
import asyncio
import os
import threading
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import Base, create_database
from .migrations import upgrade_database
from .intelligence_routes import install as install_intelligence_routes
from .ingestion import IngestionError, ingest_repository
from .index import file_detail, repository_overview, search_symbols, symbol_detail
from .models import FileParse, ParseSnapshot, Repository, RepositorySnapshot, SourceFile, Symbol
from .parsing import ParsingError, parse_repository
from .relationships import dependency_graph, file_relationships
from .schemas import DependencyGraphRead, RelationshipPageRead
from .schemas import CallPageRead
from .calls import file_calls
from .jobs import IndexingBusy, IndexWorker, read_jobs
from .models import IndexJob
from .schemas import IndexJobRead
from .schemas import (FileDetailRead, FileParseRead, FileRead, ParseSnapshotRead,
                      RepositoryCreate, RepositoryOverviewRead, RepositoryRead,
                      SnapshotRead, SymbolDetailRead, SymbolRead, SymbolSearchRead)


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


def get_index_session(request: Request):
    with request.app.state.sessions() as session:
        if session.get_bind().dialect.name == "sqlite":
            # SQLite's legacy driver mode does not begin a transaction for SELECT.
            # Keep source, parse metadata, and symbol pages on the same read snapshot.
            session.connection().exec_driver_sql("BEGIN")
        elif session.get_bind().dialect.name == "postgresql":
            # READ COMMITTED can mix two index generations across SELECTs.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        yield session


def create_app(database_url: str | None = None) -> FastAPI:
    engine, sessions = create_database(
        database_url or os.getenv("DATABASE_URL", "sqlite:///./codeatlas-metadata.db")
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        upgrade_database(engine)
        worker = IndexWorker(sessions, application.state.ingestion_lock)
        application.state.index_worker = worker
        try:
            worker.recover()
            yield
        finally:
            await asyncio.to_thread(worker.close)
            engine.dispose()

    application = FastAPI(title="CodeAtlas", version="0.18.0", lifespan=lifespan)
    application.state.sessions = sessions
    application.state.ingestion_lock = threading.Lock()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready", summary="Check database connectivity")
    def ready(session: Session = Depends(get_session)):
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Database unavailable.") from exc
        return {"status": "ready"}

    @application.post("/repositories", response_model=RepositoryRead, status_code=201,
                      summary="Register a GitHub repository URL (step 1)")
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

    @application.post("/repositories/{repository_id}/ingest", response_model=SnapshotRead,
                      summary="Download Python source for a registered repository (step 2)")
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

    @application.post("/repositories/{repository_id}/parse", response_model=ParseSnapshotRead,
                      summary="Extract symbols from saved source (step 3)")
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

    @application.get("/repositories/{repository_id}/overview", response_model=RepositoryOverviewRead,
                     summary="Inspect repository metadata and indexing statistics")
    def get_overview(repository_id: int, session: Session = Depends(get_index_session)):
        result = repository_overview(session, repository_id)
        if result is None:
            raise HTTPException(404, "Repository not found.")
        return result

    @application.get("/repositories/{repository_id}/files/{file_id}", response_model=FileDetailRead,
                     summary="Inspect saved source and a page of its symbols")
    def get_file_detail(repository_id: int, file_id: int,
                        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                        session: Session = Depends(get_index_session)):
        result = file_detail(session, repository_id, file_id, limit, offset)
        if result is None:
            raise HTTPException(404, "File not found in this repository.")
        return result

    @application.get("/repositories/{repository_id}/symbols/{symbol_id}", response_model=SymbolDetailRead,
                     summary="Inspect a symbol's source snippet and GitHub line link")
    def get_symbol_detail(repository_id: int, symbol_id: int, session: Session = Depends(get_index_session)):
        result = symbol_detail(session, repository_id, symbol_id)
        if result is None:
            raise HTTPException(404, "Symbol not found in this repository.")
        return result

    @application.get("/repositories/{repository_id}/search", response_model=SymbolSearchRead,
                     summary="Search saved symbol names, scopes, signatures, and file paths")
    def search(repository_id: int, q: str = Query(min_length=1, max_length=200),
               kind: Literal["function", "class", "method", "import"] | None = None,
               limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               session: Session = Depends(get_index_session)):
        query = q.strip()
        if not query:
            raise HTTPException(422, "Enter a non-empty search term.")
        result = search_symbols(session, repository_id, query, kind, limit, offset)
        if result is None:
            raise HTTPException(404, "Repository not found.")
        return result

    @application.get("/repositories/{repository_id}/files/{file_id}/relationships",
                     response_model=RelationshipPageRead)
    def relationships(repository_id: int, file_id: int,
                      kind: Literal["contains", "imports"] | None = None,
                      direction: Literal["outgoing", "incoming"] = "outgoing",
                      limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                      session: Session = Depends(get_index_session)):
        result = file_relationships(session, repository_id, file_id, kind, direction, limit, offset)
        if result is None:
            raise HTTPException(404, "File not found in this repository.")
        return result

    @application.get("/repositories/{repository_id}/files/{file_id}/graph",
                     response_model=DependencyGraphRead,
                     summary="Inspect up to 12 directly connected local Python files")
    def graph(repository_id: int, file_id: int, session: Session = Depends(get_index_session)):
        result = dependency_graph(session, repository_id, file_id)
        if result is None:
            raise HTTPException(404, "File not found in this repository.")
        return result

    @application.get("/repositories/{repository_id}/files/{file_id}/calls", response_model=CallPageRead,
                     summary="Inspect call sites and approximate same-file definition matches")
    def calls(repository_id: int, file_id: int,
              resolution: Literal["candidate", "ambiguous", "unresolved"] | None = None,
              limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
              session: Session = Depends(get_index_session)):
        result = file_calls(session, repository_id, file_id, resolution, limit, offset)
        if result is None:
            raise HTTPException(404, "File not found in this repository.")
        return result

    @application.post("/repositories/{repository_id}/jobs", response_model=IndexJobRead, status_code=202,
                      summary="Start a durable background ingestion and parse job")
    def start_job(repository_id: int, session: Session = Depends(get_session)):
        if session.get(Repository, repository_id) is None:
            raise HTTPException(404, "Repository not found.")
        try:
            return application.state.index_worker.submit(repository_id)
        except IndexingBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except (RuntimeError, SQLAlchemyError) as exc:
            raise HTTPException(503, "Could not start the indexing worker. Try again.") from exc

    @application.get("/jobs", response_model=list[IndexJobRead], summary="Inspect recent indexing jobs")
    def recent_jobs(limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
        jobs = session.scalars(select(IndexJob).order_by(
            IndexJob.created_at.desc(), IndexJob.id.desc()).limit(limit)).all()
        return read_jobs(session, jobs)

    @application.get("/jobs/{job_id}", response_model=IndexJobRead)
    def get_job(job_id: str, session: Session = Depends(get_session)):
        job = session.get(IndexJob, job_id)
        if job is None:
            raise HTTPException(404, "Indexing job not found.")
        return read_jobs(session, [job])[0]

    install_intelligence_routes(application, get_session, get_index_session)
    return application


app = create_app()
