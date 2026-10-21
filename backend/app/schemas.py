from datetime import datetime, timezone
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_url: str = Field(max_length=500, examples=["https://github.com/pallets/itsdangerous"])

    @field_validator("github_url")
    @classmethod
    def canonical_github_url(cls, value: str) -> str:
        match = re.fullmatch(
            r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/([A-Za-z0-9_.-]{1,100})/?",
            value.strip(),
        )
        if match is None:
            raise ValueError("Use a repository URL such as https://github.com/pallets/flask.")
        owner, name = match.groups()
        name = name.removesuffix(".git")
        if name in {"", ".", ".."}:
            raise ValueError("Invalid repository name.")
        return f"https://github.com/{owner.lower()}/{name.lower()}"


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_url: str
    owner: str
    name: str
    status: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def restore_sqlite_timezone(cls, value: datetime) -> datetime:
        # SQLite stores datetimes without an offset; all writes above use UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: int
    commit_sha: str
    default_branch: str
    ingested_at: datetime
    file_count: int
    skipped_files: int
    line_count: int

    @field_validator("ingested_at")
    @classmethod
    def restore_sqlite_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    path: str
    language: str
    content_hash: str
    line_count: int


class SymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    name: str
    qualified_name: str
    parent_qualified_name: str | None
    symbol_type: str
    start_line: int
    end_line: int
    signature: str


class ParseSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: int
    commit_sha: str
    parsed_at: datetime
    file_count: int
    symbol_count: int
    functions: int
    classes: int
    methods: int
    imports: int
    parse_error_files: int

    @field_validator("parsed_at")
    @classmethod
    def restore_sqlite_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class FileParseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: int
    has_parse_errors: bool
    symbol_count: int


class RepositoryOverviewRead(BaseModel):
    repository: RepositoryRead
    snapshot: SnapshotRead | None
    parsing: ParseSnapshotRead | None


class SymbolPageRead(BaseModel):
    items: list[SymbolRead]
    total: int | None
    limit: int
    offset: int


class FileDetailRead(BaseModel):
    file: FileRead
    source: str
    commit_sha: str
    github_url: str
    parsing: FileParseRead | None
    symbols: SymbolPageRead


class SymbolDetailRead(BaseModel):
    symbol: SymbolRead
    file: FileRead
    source: str
    commit_sha: str
    has_parse_errors: bool
    github_url: str


class SymbolSearchItemRead(BaseModel):
    symbol: SymbolRead
    path: str
    has_parse_errors: bool


class SymbolSearchRead(BaseModel):
    repository_id: int
    query: str
    parsed: bool
    commit_sha: str | None
    items: list[SymbolSearchItemRead]
    total: int
    limit: int
    offset: int


class RelationshipRead(BaseModel):
    id: int
    kind: str
    label: str
    resolution: str
    source_name: str
    source_symbol_id: int | None
    target_name: str
    target_symbol_id: int | None
    file_id: int
    path: str
    start_line: int
    target_file_id: int | None
    target_path: str | None


class RelationshipPageRead(BaseModel):
    file_id: int
    ready: bool
    commit_sha: str | None
    items: list[RelationshipRead]
    total: int
    limit: int
    offset: int


class GraphNodeRead(BaseModel):
    id: int
    path: str


class GraphEdgeRead(BaseModel):
    source: int
    target: int
    count: int


class DependencyGraphRead(BaseModel):
    file_id: int
    ready: bool
    commit_sha: str | None
    total_neighbors: int
    unresolved_imports: int
    self_imports: int
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
