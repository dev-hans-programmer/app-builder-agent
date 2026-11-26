from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.config import ControlPlaneSettings
from src.control_plane.infrastructure.artifacts import ArtifactStore


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_settings(request: Request) -> ControlPlaneSettings:
    return request.app.state.settings


def get_artifact_store(request: Request) -> ArtifactStore:
    return request.app.state.artifact_store


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    configured = request.app.state.settings.api_key
    if configured and (
        x_api_key is None or not secrets.compare_digest(x_api_key, configured)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
