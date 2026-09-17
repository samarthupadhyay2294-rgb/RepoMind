"""Repository request/response schemas. No SQLAlchemy internals leak here."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.repository import RepositoryStatus, SourceType

# Schemes a future clone step may fetch from. `file://` is excluded so a URL
# can never smuggle local-filesystem access; credentials are rejected so they
# are never stored in the database or echoed in API responses.
_ALLOWED_URL_SCHEMES = frozenset({"http", "https", "ssh", "git"})


def validate_source_url(value: str | None) -> str | None:
    """Reject unsafe repository URLs (unsupported scheme, credentials, paths)."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return stripped
    if "://" in stripped:
        scheme, _, rest = stripped.partition("://")
        if scheme.lower() not in _ALLOWED_URL_SCHEMES:
            raise ValueError(f"unsupported URL scheme: {scheme}")
        authority = rest.split("/", 1)[0]
        userinfo, at, _host = authority.rpartition("@")
        if at and ":" in userinfo:
            raise ValueError("URL must not contain credentials")
        if not authority:
            raise ValueError("URL must include a host")
    else:
        # scp-like syntax only (e.g. git@github.com:org/repo.git); a bare
        # local path here would bypass the source_type boundary.
        _, at, after = stripped.partition("@")
        if not at or ":" not in after:
            raise ValueError("URL must use http(s), ssh, git, or scp-like syntax")
    return stripped


class RepositoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    source_url: str | None = Field(default=None, max_length=2000)
    local_path: str | None = Field(default=None, max_length=2000)
    default_branch: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped

    @model_validator(mode="after")
    def source_metadata_matches_type(self) -> "RepositoryCreate":
        if self.source_type == SourceType.LOCAL and not (self.local_path or "").strip():
            raise ValueError("local_path is required when source_type is 'local'")
        if self.source_type == SourceType.GIT and not (self.source_url or "").strip():
            raise ValueError("source_url is required when source_type is 'git'")
        return self

    @field_validator("source_url")
    @classmethod
    def source_url_is_safe(cls, value: str | None) -> str | None:
        return validate_source_url(value)


class RepositoryUpdate(BaseModel):
    """Only client-editable fields. status/owner_id/sha are never set here."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2000)
    default_branch: str | None = Field(default=None, max_length=100)

    @field_validator("source_url")
    @classmethod
    def source_url_is_safe(cls, value: str | None) -> str | None:
        return validate_source_url(value)


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: str
    name: str
    source_type: SourceType
    source_url: str | None
    local_path: str | None
    default_branch: str | None
    current_commit_sha: str | None
    status: RepositoryStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
    total: int
