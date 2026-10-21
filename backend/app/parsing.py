from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import FileParse, ParseSnapshot, Repository, RepositorySnapshot, SourceFile, Symbol
from .parser import ParsingError, parse_python
from .relationships import build_relationships
from .models import Relationship, RelationshipSnapshot
from .models import CallSite, CallSnapshot
from .calls import build_calls

MAX_SYMBOLS = 100_000
MAX_CALLS = 100_000


def clear_parse_results(session: Session, repository_id: int) -> None:
    session.execute(delete(CallSite).where(CallSite.repository_id == repository_id))
    session.execute(delete(CallSnapshot).where(CallSnapshot.repository_id == repository_id))
    session.execute(delete(Relationship).where(Relationship.repository_id == repository_id))
    session.execute(delete(RelationshipSnapshot).where(RelationshipSnapshot.repository_id == repository_id))
    file_ids = select(SourceFile.id).where(SourceFile.repository_id == repository_id)
    session.execute(delete(Symbol).where(Symbol.file_id.in_(file_ids)))
    session.execute(delete(FileParse).where(FileParse.file_id.in_(file_ids)))
    session.execute(delete(ParseSnapshot).where(ParseSnapshot.repository_id == repository_id))


def parse_repository(session: Session, repository: Repository) -> ParseSnapshot:
    snapshot = session.get(RepositorySnapshot, repository.id)
    if snapshot is None:
        raise ParsingError("Ingest this repository before parsing its source.")
    extracted = []
    file_results = []
    counts = Counter()
    parsed_files = []
    call_count = 0
    files = session.scalars(select(SourceFile).where(
        SourceFile.repository_id == repository.id).order_by(SourceFile.path)).all()
    for file in files:
        result = parse_python(file.source, file.path, max_symbols=MAX_SYMBOLS - len(extracted),
                              max_calls=MAX_CALLS - call_count)
        call_count += len(result.calls)
        start = len(extracted)
        file_results.append(FileParse(file_id=file.id, has_parse_errors=result.has_parse_errors,
                                      symbol_count=len(result.symbols)))
        for symbol in result.symbols:
            counts[symbol.symbol_type] += 1
            extracted.append(Symbol(file_id=file.id, **vars(symbol)))
        parsed_files.append((file, result, extracted[start:]))

    # Complete extraction before replacing old results; commit is owned by the route.
    clear_parse_results(session, repository.id)
    parsed = ParseSnapshot(repository_id=repository.id, commit_sha=snapshot.commit_sha,
        parsed_at=datetime.now(timezone.utc), file_count=len(file_results), symbol_count=len(extracted),
        functions=counts["function"], classes=counts["class"], methods=counts["method"],
        imports=counts["import"], parse_error_files=sum(file.has_parse_errors for file in file_results))
    session.add_all([parsed, *file_results, *extracted])
    repository.status = "parsed"
    session.flush()
    build_relationships(session, repository.id, snapshot.commit_sha, files, parsed_files)
    build_calls(session, repository.id, snapshot.commit_sha, parsed_files)
    session.flush()
    return parsed
