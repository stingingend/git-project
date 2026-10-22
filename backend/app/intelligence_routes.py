from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
import logging

from .semantic import (SemanticError, build_semantic_index, semantic_search, semantic_status)
from .answers import answer_question

logger = logging.getLogger(__name__)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    generate: bool = False


def install(application, get_session, get_index_session):
    @application.post("/repositories/{repository_id}/questions")
    def question(repository_id: int, body: Question, session=Depends(get_index_session)):
        try:
            return answer_question(session, repository_id, body.question, body.generate)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SemanticError as exc:
            raise HTTPException(409, str(exc)) from exc
    @application.get("/repositories/{repository_id}/semantic")
    def status(repository_id: int, session=Depends(get_index_session)):
        try:
            return semantic_status(session, repository_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SemanticError as exc:
            raise HTTPException(409, str(exc)) from exc

    @application.post("/repositories/{repository_id}/semantic")
    def build(repository_id: int, session=Depends(get_session)):
        if not application.state.ingestion_lock.acquire(blocking=False):
            raise HTTPException(409, "An indexing operation is running. Try again when it finishes.")
        try:
            result = build_semantic_index(session, repository_id)
            session.commit()
            return result
        except LookupError as exc:
            session.rollback()
            raise HTTPException(404, str(exc)) from exc
        except SemanticError as exc:
            session.rollback()
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            session.rollback()
            logger.exception("Local embedding build failed")
            raise HTTPException(503, "Could not build local embeddings. Check API logs/model download access and retry.") from exc
        finally:
            application.state.ingestion_lock.release()

    @application.get("/repositories/{repository_id}/semantic/search")
    def search(repository_id: int, q: str = Query(min_length=2, max_length=500),
               limit: int = Query(10, ge=1, le=20), session=Depends(get_index_session)):
        try:
            return semantic_search(session, repository_id, q, limit)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SemanticError as exc:
            raise HTTPException(409, str(exc)) from exc
