from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, create_database
from .models import Repository
from .schemas import RepositoryCreate, RepositoryRead


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

    application = FastAPI(title="CodeAtlas", version="0.2.0", lifespan=lifespan)
    application.state.sessions = sessions

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

    return application


app = create_app()
