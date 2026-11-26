"""AsyncEngine and AsyncSession construction over asyncpg."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.control_plane.config import get_settings


def build_async_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True)


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async_engine = build_async_engine()
AsyncSessionFactory = build_session_factory(async_engine)
