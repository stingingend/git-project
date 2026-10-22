"""Read the stored index without cloning or parsing during a query."""
from urllib.parse import quote

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .models import FileParse, ParseSnapshot, Repository, RepositorySnapshot, SourceFile, Symbol


def source_url(repository: Repository, snapshot: RepositorySnapshot, path: str) -> str:
    return f"{repository.github_url}/blob/{snapshot.commit_sha}/{quote(path, safe='/')}"


def repository_overview(session: Session, repository_id: int) -> dict | None:
    row = session.execute(
        select(Repository, RepositorySnapshot, ParseSnapshot)
        .outerjoin(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
        .outerjoin(ParseSnapshot, ParseSnapshot.repository_id == Repository.id)
        .where(Repository.id == repository_id)
    ).one_or_none()
    if row is None:
        return None
    repository, snapshot, parsing = row
    languages = dict(session.execute(select(SourceFile.language, func.count())
        .where(SourceFile.repository_id == repository_id).group_by(SourceFile.language)).all())
    return {"repository": repository, "snapshot": snapshot, "parsing": parsing, "languages": languages}


def file_detail(session: Session, repository_id: int, file_id: int, limit: int, offset: int) -> dict | None:
    row = session.execute(
        select(SourceFile, Repository, RepositorySnapshot, FileParse)
        .join(Repository, Repository.id == SourceFile.repository_id)
        .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
        .outerjoin(FileParse, FileParse.file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository_id, SourceFile.id == file_id)
    ).one_or_none()
    if row is None:
        return None
    file, repository, snapshot, parsing = row
    symbols = session.scalars(select(Symbol).where(Symbol.file_id == file.id)
        .order_by(Symbol.start_line, Symbol.id).limit(limit).offset(offset)).all()
    return {
        "file": file, "source": file.source, "commit_sha": snapshot.commit_sha,
        "github_url": source_url(repository, snapshot, file.path), "parsing": parsing,
        "symbols": {"items": symbols, "total": parsing.symbol_count if parsing else None,
                    "limit": limit, "offset": offset},
    }


def symbol_detail(session: Session, repository_id: int, symbol_id: int) -> dict | None:
    row = session.execute(
        select(Symbol, SourceFile, Repository, RepositorySnapshot, FileParse)
        .join(SourceFile, SourceFile.id == Symbol.file_id)
        .join(Repository, Repository.id == SourceFile.repository_id)
        .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
        .join(FileParse, FileParse.file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository_id, Symbol.id == symbol_id)
    ).one_or_none()
    if row is None:
        return None
    symbol, file, repository, snapshot, parsing = row
    # Tree-sitter counts LF line boundaries; split only on LF, not every Unicode
    # separator that Python's str.splitlines() recognizes inside a string literal.
    source = "\n".join(file.source.split("\n")[symbol.start_line - 1:symbol.end_line])
    return {
        "symbol": symbol, "file": file, "source": source,
        "commit_sha": snapshot.commit_sha, "has_parse_errors": parsing.has_parse_errors,
        "github_url": f"{source_url(repository, snapshot, file.path)}#L{symbol.start_line}-L{symbol.end_line}",
    }


def search_symbols(session: Session, repository_id: int, query: str,
                   kind: str | None, limit: int, offset: int) -> dict | None:
    repository = session.get(Repository, repository_id)
    if repository is None:
        return None
    parsed = session.get(ParseSnapshot, repository_id)
    response = {"repository_id": repository_id, "query": query,
                "parsed": parsed is not None, "commit_sha": parsed.commit_sha if parsed else None,
                "items": [], "total": 0, "limit": limit, "offset": offset}
    if parsed is None:
        return response
    # Treat %, _, and the escape character as literal search text, not SQL wildcards.
    matches = or_(Symbol.name.icontains(query, autoescape=True),
                  Symbol.qualified_name.icontains(query, autoescape=True),
                  Symbol.signature.icontains(query, autoescape=True),
                  SourceFile.path.icontains(query, autoescape=True))
    conditions = [SourceFile.repository_id == repository_id, matches]
    if kind is not None:
        conditions.append(Symbol.symbol_type == kind)
    response["total"] = session.scalar(select(func.count(Symbol.id)).join(SourceFile).where(*conditions))
    rank = case((func.lower(Symbol.name) == query.lower(), 0),
                (Symbol.name.istartswith(query, autoescape=True), 1), else_=2)
    rows = session.execute(select(Symbol, SourceFile.path, FileParse.has_parse_errors)
        .join(SourceFile, SourceFile.id == Symbol.file_id)
        .join(FileParse, FileParse.file_id == SourceFile.id).where(*conditions)
        .order_by(rank, SourceFile.path, Symbol.start_line, Symbol.id).limit(limit).offset(offset))
    response["items"] = [{"symbol": symbol, "path": path, "has_parse_errors": errors}
                         for symbol, path, errors in rows]
    return response
