from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_url: Mapped[str] = mapped_column(String(500), unique=True)
    owner: Mapped[str] = mapped_column(String(39))
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="registered")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    commit_sha: Mapped[str] = mapped_column(String(40))
    default_branch: Mapped[str] = mapped_column(String(250))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    file_count: Mapped[int]
    skipped_files: Mapped[int]
    line_count: Mapped[int]


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (UniqueConstraint("repository_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(30), default="Python")
    content_hash: Mapped[str] = mapped_column(String(64))
    line_count: Mapped[int]
    source: Mapped[str] = mapped_column(Text)


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    qualified_name: Mapped[str] = mapped_column(Text)
    parent_qualified_name: Mapped[str | None] = mapped_column(Text)
    symbol_type: Mapped[str] = mapped_column(String(30))
    start_line: Mapped[int]
    end_line: Mapped[int]
    signature: Mapped[str] = mapped_column(Text)


class FileParse(Base):
    __tablename__ = "file_parses"

    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), primary_key=True)
    has_parse_errors: Mapped[bool]
    symbol_count: Mapped[int]


class ParseSnapshot(Base):
    __tablename__ = "parse_snapshots"

    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    commit_sha: Mapped[str] = mapped_column(String(40))
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    file_count: Mapped[int]
    symbol_count: Mapped[int]
    functions: Mapped[int]
    classes: Mapped[int]
    methods: Mapped[int]
    imports: Mapped[int]
    parse_error_files: Mapped[int]
