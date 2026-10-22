"""Transactional indexing with a versioned per-file syntax cache."""
from collections import Counter
from datetime import datetime, timezone
import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .models import (FileParse, ParseSnapshot, Repository, RepositorySnapshot, SourceFile,
                     Symbol, Relationship, RelationshipSnapshot, CallSite, CallSnapshot,
                     FileIndexState, IndexChanges, CallOrigin, SearchDocument, SemanticSnapshot)
from .parser import ParsingError, parse_source
from .relationships import build_relationships
from .calls import build_calls, resolve_repository_calls

MAX_SYMBOLS = 100_000
MAX_CALLS = 100_000
# Bump whenever extraction, scope serialization, or call matching changes.
INDEX_FORMAT_VERSION = "3"


def invalidate_snapshot(session: Session, repository_id: int) -> None:
    session.execute(delete(SemanticSnapshot).where(SemanticSnapshot.repository_id == repository_id))
    # Cross-file targets must be detached before changed definitions are deleted.
    origin = select(CallOrigin.call_id).where(CallOrigin.call_id == CallSite.id).exists()
    session.execute(update(CallSite).where(CallSite.repository_id == repository_id, origin)
        .values(target_symbol_id=select(CallOrigin.target_symbol_id).where(CallOrigin.call_id == CallSite.id).scalar_subquery(),
                resolution=select(CallOrigin.resolution).where(CallOrigin.call_id == CallSite.id).scalar_subquery()),
        execution_options={"synchronize_session": False})
    # Imports can point into any file, so remove these before deleting symbols/files.
    session.execute(delete(Relationship).where(Relationship.repository_id == repository_id))
    session.execute(delete(RelationshipSnapshot).where(RelationshipSnapshot.repository_id == repository_id))
    session.execute(delete(CallSnapshot).where(CallSnapshot.repository_id == repository_id))
    session.execute(delete(ParseSnapshot).where(ParseSnapshot.repository_id == repository_id))


def clear_file_results(session: Session, file_ids) -> None:
    session.execute(delete(SearchDocument).where(SearchDocument.file_id.in_(file_ids)))
    calls = select(CallSite.id).where(CallSite.file_id.in_(file_ids))
    session.execute(delete(CallOrigin).where(CallOrigin.call_id.in_(calls)))
    session.execute(delete(CallSite).where(CallSite.file_id.in_(file_ids)))
    session.execute(delete(Symbol).where(Symbol.file_id.in_(file_ids)))
    session.execute(delete(FileParse).where(FileParse.file_id.in_(file_ids)))
    session.execute(delete(FileIndexState).where(FileIndexState.file_id.in_(file_ids)))


def clear_parse_results(session: Session, repository_id: int) -> None:
    invalidate_snapshot(session, repository_id)
    clear_file_results(session, select(SourceFile.id).where(SourceFile.repository_id == repository_id))


def cached_structure(state, file, file_parse, symbols):
    if (state is None or file_parse is None or state.content_hash != file.content_hash
            or state.format_version != INDEX_FORMAT_VERSION):
        return None
    try:
        data = json.loads(state.structure)
        ids, parents = data["symbols"], data["parents"]
        by_id = {symbol.id: symbol for symbol in symbols}
        if (len(ids) != len(symbols) or len(set(ids)) != len(ids)
                or set(ids) != set(by_id) or len(parents) != len(ids)
                or file_parse.symbol_count != len(ids)
                or any(parent is not None and (type(parent) is not int or not 0 <= parent < index)
                       for index, parent in enumerate(parents))):
            return None
        return parents, [by_id[symbol_id] for symbol_id in ids]
    except (ValueError, KeyError, TypeError):
        return None


def parse_repository(session: Session, repository: Repository) -> ParseSnapshot:
    snapshot = session.get(RepositorySnapshot, repository.id)
    if snapshot is None:
        raise ParsingError("Ingest this repository before parsing its source.")
    files = session.scalars(select(SourceFile).where(
        SourceFile.repository_id == repository.id).order_by(SourceFile.path)).all()
    file_ids = [file.id for file in files]
    states = {state.file_id: state for state in session.scalars(select(FileIndexState).where(
        FileIndexState.file_id.in_(file_ids)))}
    file_results = {result.file_id: result for result in session.scalars(select(FileParse).where(
        FileParse.file_id.in_(file_ids)))}
    symbols_by_file = {file.id: [] for file in files}
    for symbol in session.scalars(select(Symbol).where(Symbol.file_id.in_(file_ids))):
        symbols_by_file[symbol.file_id].append(symbol)
    calls_by_file = dict(session.execute(select(CallSite.file_id, func.count()).where(
        CallSite.file_id.in_(file_ids)).group_by(CallSite.file_id)).all())
    reused, dirty = [], []
    symbol_count = call_count = 0
    for file in files:
        cached = cached_structure(states.get(file.id), file, file_results.get(file.id),
                                  symbols_by_file[file.id])
        if cached is None:
            dirty.append(file)
        else:
            parents, symbols = cached
            reused.append((file, parents, symbols))
            symbol_count += len(symbols)
            call_count += calls_by_file.get(file.id, 0)
    if symbol_count > MAX_SYMBOLS or call_count > MAX_CALLS:
        raise ParsingError("Repository exceeds the symbol or call limit.")
    parsed_files = []
    for file in dirty:
        result = parse_source(file.source, file.path, max_symbols=MAX_SYMBOLS - symbol_count,
                              max_calls=MAX_CALLS - call_count)
        symbols = [Symbol(file_id=file.id, **vars(symbol)) for symbol in result.symbols]
        symbol_count += len(symbols)
        call_count += len(result.calls)
        parsed_files.append((file, result, symbols))

    # Extract everything before replacing results. The caller owns commit/rollback.
    invalidate_snapshot(session, repository.id)
    dirty_ids = [file.id for file in dirty]
    clear_file_results(session, dirty_ids)
    for file_id in dirty_ids:
        file_results.pop(file_id, None)
    for file, result, symbols in parsed_files:
        metadata = FileParse(file_id=file.id, has_parse_errors=result.has_parse_errors,
                             symbol_count=len(symbols))
        file_results[file.id] = metadata
        session.add_all([metadata, *symbols])
    session.flush()
    structure = reused + [(file, result.parents, symbols) for file, result, symbols in parsed_files]
    counts = Counter(symbol.symbol_type for _, _, symbols in structure for symbol in symbols)
    for file, result, symbols in parsed_files:
        session.add(FileIndexState(file_id=file.id, content_hash=file.content_hash,
            format_version=INDEX_FORMAT_VERSION, structure=json.dumps(dict(
                symbols=[symbol.id for symbol in symbols], parents=result.parents))))
    parsed = ParseSnapshot(repository_id=repository.id, commit_sha=snapshot.commit_sha,
        parsed_at=datetime.now(timezone.utc), file_count=len(files), symbol_count=symbol_count,
        functions=counts["function"], classes=counts["class"], methods=counts["method"],
        imports=counts["import"], parse_error_files=sum(item.has_parse_errors for item in file_results.values()))
    session.add(parsed)
    repository.status = "parsed"
    build_relationships(session, repository.id, snapshot.commit_sha, files, structure)
    build_calls(session, repository.id, parsed_files)
    session.flush()
    resolve_repository_calls(session, repository.id, files, structure)
    session.add(CallSnapshot(repository_id=repository.id, commit_sha=snapshot.commit_sha))
    changes = session.get(IndexChanges, repository.id)
    if changes is not None:
        changes.parsed_files, changes.reused_files = len(dirty), len(reused)
    session.flush()
    return parsed
