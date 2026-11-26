"""FastAPI application factory for the durable builder control plane."""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.control_plane.api.routes import api_router
from src.control_plane.api.routes.health import router as health_router
from src.control_plane.application.errors import ConflictError, NotFoundError
from src.control_plane.config import ControlPlaneSettings, get_settings
from src.control_plane.infrastructure.artifacts import ArtifactStore, LocalArtifactStore
from src.control_plane.infrastructure.database import AsyncSessionFactory, async_engine


def create_app(
    *,
    settings: ControlPlaneSettings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    artifact_store: ArtifactStore | None = None,
    engine: AsyncEngine | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_engine = engine or async_engine
    owns_engine = session_factory is None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_engine:
            await resolved_engine.dispose()

    application = FastAPI(
        title="App Builder Control Plane",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.session_factory = session_factory or AsyncSessionFactory
    application.state.artifact_store = artifact_store or LocalArtifactStore(
        resolved_settings.artifact_root
    )

    @application.exception_handler(NotFoundError)
    async def not_found(_: Request, error: NotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": str(error)}},
        )

    @application.exception_handler(ConflictError)
    async def conflict(_: Request, error: ConflictError):
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "conflict", "message": str(error)}},
        )

    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "src.control_plane.app:app",
        host=settings.api_host,
        port=settings.api_port,
    )
