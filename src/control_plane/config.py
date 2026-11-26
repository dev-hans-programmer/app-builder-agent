"""Typed runtime configuration for the API, dispatcher, and workers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ControlPlaneSettings(BaseSettings):
    """Environment-backed settings shared by every control-plane process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONTROL_",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = (
        "postgresql+asyncpg://app_builder:app_builder@127.0.0.1:5433/app_builder"
    )
    broker_url: str = "amqp://app_builder:app_builder@127.0.0.1:5672/app_builder"
    redis_url: str = "redis://127.0.0.1:6379/0"
    artifact_root: Path = Path("./data")
    retain_local_builds: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    api_key: str | None = None
    event_poll_seconds: float = Field(default=1.0, gt=0)
    event_heartbeat_seconds: float = Field(default=15.0, gt=0)
    outbox_batch_size: int = Field(default=50, ge=1, le=500)
    github_owner: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_OWNER", "CONTROL_GITHUB_OWNER"),
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_TOKEN", "CONTROL_GITHUB_TOKEN"),
    )
    github_repository_visibility: Literal["private", "public"] = Field(
        default="private",
        validation_alias=AliasChoices(
            "GITHUB_REPOSITORY_VISIBILITY",
            "CONTROL_GITHUB_REPOSITORY_VISIBILITY",
        ),
    )
    github_commit_author_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GITHUB_COMMIT_AUTHOR_NAME", "CONTROL_GITHUB_COMMIT_AUTHOR_NAME"
        ),
    )
    github_commit_author_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GITHUB_COMMIT_AUTHOR_EMAIL", "CONTROL_GITHUB_COMMIT_AUTHOR_EMAIL"
        ),
    )
    github_api_url: str = "https://api.github.com"
    github_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    github_blob_concurrency: int = Field(default=8, ge=1, le=20)
    github_max_files: int = Field(default=2000, ge=1, le=10000)
    github_max_file_bytes: int = Field(
        default=25 * 1024 * 1024, ge=1, le=100 * 1024 * 1024
    )

    @property
    def github_delivery_requested(self) -> bool:
        return bool(self.github_owner or self.github_token)

    @property
    def github_delivery_enabled(self) -> bool:
        return bool(self.github_owner and self.github_token)

    @property
    def checkpoint_database_url(self) -> str:
        """Return a psycopg URL accepted by LangGraph's Postgres checkpointer."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache(maxsize=1)
def get_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()
