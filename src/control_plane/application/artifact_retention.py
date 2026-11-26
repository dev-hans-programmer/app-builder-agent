"""Post-delivery retention policy for generated source trees."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.control_plane.infrastructure.artifacts import ArtifactStore
from src.control_plane.infrastructure.database.models import Artifact, RunEvent


class LocalBuildRetentionService:
    """Remove published build bytes while retaining their durable metadata."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        artifact_store: ArtifactStore,
    ) -> None:
        self.session_factory = session_factory
        self.artifact_store = artifact_store

    async def remove_published_builds(self, run_id: UUID, workspace: Path) -> int:
        storage_root = await asyncio.to_thread(
            self.artifact_store.remove_tree, workspace / "builds"
        )
        if storage_root is None:
            return 0

        deleted_at = datetime.now(timezone.utc)
        storage_prefix = f"{storage_root.rstrip('/')}/%"
        async with self.session_factory() as session:
            result = await session.execute(
                update(Artifact)
                .where(
                    Artifact.run_id == run_id,
                    Artifact.storage_key.like(storage_prefix),
                )
                .values(local_available=False, local_deleted_at=deleted_at)
            )
            affected = int(result.rowcount or 0)
            session.add(
                RunEvent(
                    run_id=run_id,
                    event_type="local_builds_removed",
                    status="completed",
                    message="Published build files removed by local retention policy",
                    payload={"artifact_count": affected},
                )
            )
            await session.commit()
        return affected
