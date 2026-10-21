from datetime import datetime, timezone
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_url: str = Field(max_length=500)

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
