"""Durable GitHub delivery use case executed after generation gates pass."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.control_plane.config import ControlPlaneSettings
from src.control_plane.infrastructure.database.models import Project, Run, RunEvent
from src.control_plane.infrastructure.github import (
    GitHubPublisher,
    GitHubPublishingError,
    PublishedRepository,
    RepositoryNameCollision,
)


class GitHubDeliveryService:
    def __init__(
        self,
        *,
        settings: ControlPlaneSettings,
        session_factory: async_sessionmaker[AsyncSession],
        publisher_factory: Callable[[], GitHubPublisher] | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.publisher_factory = publisher_factory or self._build_publisher

    async def deliver(
        self,
        *,
        run_id: UUID,
        project: Project,
        state: dict[str, Any],
        workspace: Path,
    ) -> bool:
        if not self.settings.github_delivery_requested:
            await self._record_skipped(run_id)
            return False
        if not self.settings.github_delivery_enabled:
            error = GitHubPublishingError(
                "GitHub delivery requires both GITHUB_OWNER and GITHUB_TOKEN"
            )
            await self._record_failed(run_id, error)
            raise error

        source_root, delivery_stack = self._delivery_source(workspace, state)
        try:
            async with self.session_factory() as session:
                current = await session.get(Run, run_id)
                if (
                    current is not None
                    and current.delivery_status == "completed"
                    and current.repository_commit_sha
                ):
                    return True
                reserved_name = current.repository_name if current is not None else None

            async with self.publisher_factory() as publisher:
                await publisher.verify_owner()
                candidate = reserved_name or await publisher.available_repository_name(
                    project.slug
                )
                for _ in range(5):
                    await self._record_started(
                        run_id,
                        repository_name=candidate,
                        delivery_stack=delivery_stack,
                    )
                    try:
                        published = await publisher.publish(
                            source_root=source_root,
                            repository_name=candidate,
                            project_name=project.name,
                            run_id=run_id,
                        )
                    except RepositoryNameCollision:
                        candidate = await publisher.available_repository_name(
                            project.slug
                        )
                        continue
                    await self._record_completed(run_id, published)
                    return True
            raise GitHubPublishingError(
                "Repository name collisions exhausted all retries"
            )
        except Exception as error:
            await self._record_failed(run_id, error)
            raise

    def _build_publisher(self) -> GitHubPublisher:
        if not self.settings.github_owner or not self.settings.github_token:
            raise GitHubPublishingError(
                "GitHub delivery requires both GITHUB_OWNER and GITHUB_TOKEN"
            )
        return GitHubPublisher(
            owner=self.settings.github_owner,
            token=self.settings.github_token.get_secret_value(),
            visibility=self.settings.github_repository_visibility,
            author_name=self.settings.github_commit_author_name,
            author_email=self.settings.github_commit_author_email,
            api_url=self.settings.github_api_url,
            timeout_seconds=self.settings.github_request_timeout_seconds,
            blob_concurrency=self.settings.github_blob_concurrency,
            max_files=self.settings.github_max_files,
            max_file_bytes=self.settings.github_max_file_bytes,
        )

    @staticmethod
    def _delivery_source(workspace: Path, state: dict[str, Any]) -> tuple[Path, str]:
        target_stack = str(state.get("target_stack") or "both")
        if target_stack == "python":
            return workspace / "builds" / "python", "python"
        if target_stack == "nodejs":
            return workspace / "builds" / "nodejs", "nodejs"
        return workspace / "builds", "both"

    async def _record_started(
        self, run_id: UUID, *, repository_name: str, delivery_stack: str
    ) -> None:
        async with self.session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"Run {run_id} disappeared during GitHub delivery")
            run.status = "running"
            run.phase = "github_delivery"
            run.delivery_status = "publishing"
            run.delivery_error = None
            run.repository_owner = self.settings.github_owner
            run.repository_name = repository_name
            session.add(
                RunEvent(
                    run_id=run_id,
                    event_type="github_publish_started",
                    status="publishing",
                    message=f"Publishing generated {delivery_stack} code to GitHub",
                    payload={
                        "repository_owner": self.settings.github_owner,
                        "repository_name": repository_name,
                        "stack": delivery_stack,
                    },
                )
            )
            await session.commit()

    async def _record_completed(
        self, run_id: UUID, published: PublishedRepository
    ) -> None:
        async with self.session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"Run {run_id} disappeared during GitHub delivery")
            run.delivery_status = "completed"
            run.delivery_error = None
            run.repository_owner = published.owner
            run.repository_name = published.name
            run.repository_url = published.url
            run.repository_branch = published.branch
            run.repository_commit_sha = published.commit_sha
            run.repository_commit_url = published.commit_url
            run.published_at = datetime.now(timezone.utc)
            session.add(
                RunEvent(
                    run_id=run_id,
                    event_type="github_publish_completed",
                    status="completed",
                    message="Generated code committed to GitHub",
                    payload={
                        "repository_url": published.url,
                        "repository_name": published.name,
                        "branch": published.branch,
                        "commit_sha": published.commit_sha,
                        "commit_url": published.commit_url,
                        "file_count": published.file_count,
                    },
                )
            )
            await session.commit()

    async def _record_failed(self, run_id: UUID, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:2000]
        async with self.session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.delivery_status = "failed"
            run.delivery_error = message
            session.add(
                RunEvent(
                    run_id=run_id,
                    event_type="github_publish_failed",
                    level="error",
                    status="failed",
                    message=message,
                    payload={"error_type": type(error).__name__},
                )
            )
            await session.commit()

    async def _record_skipped(self, run_id: UUID) -> None:
        async with self.session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.delivery_status = "skipped"
            run.delivery_error = None
            session.add(
                RunEvent(
                    run_id=run_id,
                    event_type="github_publish_skipped",
                    status="skipped",
                    message="GitHub delivery is not configured",
                    payload={},
                )
            )
            await session.commit()
