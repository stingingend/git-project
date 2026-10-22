"""Local semantic retrieval over syntax units; source never leaves this process."""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import re
import threading

from sqlalchemy import inspect, select, text

from .index import source_url
from .models import (ParseSnapshot, Repository, RepositorySnapshot, SearchDocument,
                     SemanticSnapshot, SourceFile, Symbol)
from .schemas import SymbolRead

MODEL = "minishlab/potion-base-8M"
REVISION = "bf8b056651a2c21b8d2565580b8569da283cab23"
MODEL_KEY = f"{MODEL}@{REVISION}:units-v2"
MAX_DOCUMENTS = 10_000
MAX_UNIT_CHARACTERS = 8_000
_model_lock = threading.Lock()


class SemanticError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_model():
    from huggingface_hub import snapshot_download
    from model2vec import StaticModel
    # Download data-only weights/tokenizer at a pinned revision. No remote Python.
    path = snapshot_download(MODEL, revision=REVISION, token=False,
                             allow_patterns=["*.json", "*.safetensors"])
    return StaticModel.from_pretrained(path, normalize=True)


def encode(documents):
    with _model_lock:
        model = load_model()
        vectors = model.encode(documents).tolist()
    if len(vectors) != len(documents) or any(len(vector) != 256 or
            not all(math.isfinite(value) for value in vector) for vector in vectors):
        raise SemanticError("The embedding model returned invalid vectors.")
    return vectors


def require_index(session, repository_id):
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise LookupError("Repository not found.")
    snapshot = session.get(RepositorySnapshot, repository_id)
    parsed = session.get(ParseSnapshot, repository_id)
    if snapshot is None or parsed is None or snapshot.commit_sha != parsed.commit_sha:
        raise SemanticError("Re-index this repository before using intelligence features.")
    return repository, snapshot


def units(session, repository_id):
    files = session.scalars(select(SourceFile).where(SourceFile.repository_id == repository_id)
                           .order_by(SourceFile.path)).all()
    by_file = {file.id: [] for file in files}
    for symbol in session.scalars(select(Symbol).where(Symbol.file_id.in_(by_file))
                                  .where(Symbol.symbol_type != "import").order_by(Symbol.id)):
        by_file[symbol.file_id].append(symbol)
    if len(files) + sum(len(items) for items in by_file.values()) > MAX_DOCUMENTS:
        raise SemanticError(f"Semantic indexing is limited to {MAX_DOCUMENTS:,} syntax units per repository.")
    result = []
    for file in files:
        if not file.source.strip():
            continue
        lines = file.source.split("\n")
        for symbol in [None, *by_file[file.id]]:
            start, end = (symbol.start_line, symbol.end_line) if symbol else (1, max(1, len(lines)))
            source = "\n".join(lines[start - 1:end])
            heading = f"{file.path}\n{symbol.symbol_type} {symbol.name}\n{symbol.signature}" if symbol else f"module {file.path}"
            words = re.sub(r"([a-z])([A-Z])", r"\1 \2", heading).replace("_", " ")
            content = f"{words}\n{source[:MAX_UNIT_CHARACTERS]}"
            result.append(dict(file=file, symbol=symbol, start_line=start, end_line=end,
                truncated=len(source) > MAX_UNIT_CHARACTERS, content=content,
                unit_key=f"symbol:{symbol.id}" if symbol else "module",
                content_hash=hashlib.sha256(content.encode()).hexdigest()))
    return result


def native_vectors(session):
    return session.get_bind().dialect.name == "postgresql" and inspect(session.connection()).has_table("search_vectors")


def build_semantic_index(session, repository_id):
    _, snapshot = require_index(session, repository_id)
    documents = units(session, repository_id)
    existing = {(row.file_id, row.unit_key): row for row in session.scalars(select(SearchDocument)
        .where(SearchDocument.repository_id == repository_id))}
    active_keys = {(unit["file"].id, unit["unit_key"]) for unit in documents}
    for key, row in existing.items():
        if key not in active_keys:
            session.delete(row)
    dirty = []
    for unit in documents:
        row = existing.get((unit["file"].id, unit["unit_key"]))
        if row is None or row.content_hash != unit["content_hash"] or row.model != MODEL_KEY:
            dirty.append((unit, row))
    vectors = []
    for offset in range(0, len(dirty), 64):
        vectors.extend(encode([unit["content"] for unit, _ in dirty[offset:offset + 64]]))
    use_native = native_vectors(session)
    for (unit, row), vector in zip(dirty, vectors):
        if row is None:
            row = SearchDocument(repository_id=repository_id, file_id=unit["file"].id,
                symbol_id=unit["symbol"].id if unit["symbol"] else None, unit_key=unit["unit_key"])
            session.add(row)
        row.content_hash, row.model, row.embedding = unit["content_hash"], MODEL_KEY, json.dumps(vector)
        session.flush()
        if use_native:
            session.execute(text("INSERT INTO search_vectors(document_id, embedding) VALUES (:id, CAST(:v AS public.vector)) "
                "ON CONFLICT(document_id) DO UPDATE SET embedding=EXCLUDED.embedding"), {"id": row.id, "v": row.embedding})
    marker = session.get(SemanticSnapshot, repository_id)
    if marker is None:
        marker = SemanticSnapshot(repository_id=repository_id)
        session.add(marker)
    marker.commit_sha, marker.model, marker.document_count = snapshot.commit_sha, MODEL_KEY, len(documents)
    marker.indexed_at = datetime.now(timezone.utc)
    session.flush()
    return dict(commit_sha=snapshot.commit_sha, model=MODEL_KEY, document_count=len(documents),
                embedded=len(dirty), reused=len(documents) - len(dirty), storage="pgvector" if use_native else "portable")


def semantic_status(session, repository_id):
    _, snapshot = require_index(session, repository_id)
    marker = session.get(SemanticSnapshot, repository_id)
    ready = marker is not None and marker.commit_sha == snapshot.commit_sha and marker.model == MODEL_KEY
    return dict(ready=ready, document_count=marker.document_count if ready else 0, model=MODEL_KEY)


def semantic_search(session, repository_id, query, limit=10):
    repository, snapshot = require_index(session, repository_id)
    if not semantic_status(session, repository_id)["ready"]:
        raise SemanticError("Build the semantic index for the current commit first.")
    vector = encode([query])[0]
    rows = session.scalars(select(SearchDocument).where(SearchDocument.repository_id == repository_id)).all()
    if native_vectors(session):
        scored = session.execute(text("SELECT d.id, 1 - (v.embedding OPERATOR(public.<=>) CAST(:v AS public.vector)) AS score "
            "FROM search_vectors v JOIN search_documents d ON d.id=v.document_id WHERE d.repository_id=:repo "
            "ORDER BY v.embedding OPERATOR(public.<=>) CAST(:v AS public.vector), d.id LIMIT :limit"),
            {"v": json.dumps(vector), "repo": repository_id, "limit": limit}).all()
        scores = {row.id: row.score for row in scored}
    else:
        norm = math.sqrt(sum(value * value for value in vector))
        scores = {}
        for row in rows:
            other = json.loads(row.embedding)
            denominator = norm * math.sqrt(sum(value * value for value in other))
            scores[row.id] = sum(a * b for a, b in zip(vector, other)) / denominator if denominator else 0
    ranked = sorted((row for row in rows if scores.get(row.id, 0) > 0.1), key=lambda row: (-scores[row.id], row.id))[:limit]
    current_units = {(unit["file"].id, unit["unit_key"]): unit for unit in units(session, repository_id)}
    items = []
    for row in ranked:
        unit = current_units.get((row.file_id, row.unit_key))
        if unit is None or row.content_hash != unit["content_hash"]:
            raise SemanticError("The semantic index is stale. Build it again.")
        symbol = unit["symbol"]
        items.append(dict(document_id=row.id, score=round(float(scores[row.id]), 6), path=unit["file"].path,
            file_id=row.file_id, symbol=SymbolRead.model_validate(symbol).model_dump() if symbol else None,
            title=symbol.qualified_name if symbol else unit["file"].path,
            start_line=unit["start_line"], end_line=unit["end_line"], truncated=unit["truncated"],
            excerpt=unit["content"][:1500],
            github_url=f"{source_url(repository, snapshot, unit['file'].path)}#L{unit['start_line']}-L{unit['end_line']}"))
    return dict(repository_id=repository_id, commit_sha=snapshot.commit_sha, query=query, model=MODEL_KEY, items=items)
