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
