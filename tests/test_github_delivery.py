from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from src.control_plane.application.github_delivery import GitHubDeliveryService
from src.control_plane.config import ControlPlaneSettings
from src.control_plane.infrastructure.database import Base, build_session_factory
from src.control_plane.infrastructure.database import models  # noqa: F401
from src.control_plane.infrastructure.database.models import Project, Run, RunEvent
from src.control_plane.infrastructure.github import PublishedRepository


class FakePublisher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def verify_owner(self) -> None:
        return None

    async def available_repository_name(self, project_name: str) -> str:
        assert project_name == "todo"
        return "todo"

    async def publish(self, **kwargs) -> PublishedRepository:
        assert kwargs["source_root"].name == "python"
        return PublishedRepository(
            owner="hasanali",
            name=kwargs["repository_name"],
            url="https://github.com/hasanali/todo",
            branch="main",
            commit_sha="a" * 40,
            commit_url=f"https://github.com/hasanali/todo/commit/{'a' * 40}",
            file_count=2,
        )


def test_delivery_records_repository_and_auditable_events(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    session_factory = build_session_factory(engine)
    settings = ControlPlaneSettings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        github_owner="hasanali",
        github_token="test-token",
        github_repository_visibility="private",
        artifact_root=tmp_path / "artifacts",
    )
    workspace = tmp_path / "workspace"
    (workspace / "builds" / "python").mkdir(parents=True)
    (workspace / "builds" / "python" / "main.py").write_text("pass\n", encoding="utf-8")

    async def exercise() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            project = Project(name="Todo", slug="todo")
            session.add(project)
            await session.flush()
            run = Run(
                project_id=project.id,
                request="Build Todo",
                target_stack="python",
                status="running",
            )
            session.add(run)
            await session.commit()
            run_id = run.id
            project_id = project.id

        service = GitHubDeliveryService(
            settings=settings,
            session_factory=session_factory,
            publisher_factory=FakePublisher,
        )
        async with session_factory() as session:
            project = await session.get(Project, project_id)
        assert project is not None
        published = await service.deliver(
            run_id=run_id,
            project=project,
            state={"target_stack": "python"},
            workspace=workspace,
        )
        assert published is True

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            assert run is not None
            assert run.delivery_status == "completed"
            assert run.repository_name == "todo"
            assert run.repository_commit_sha == "a" * 40
            events = list(
                (
                    await session.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id)
                        .order_by(RunEvent.id)
                    )
                ).all()
            )
            assert [event.event_type for event in events] == [
                "github_publish_started",
                "github_publish_completed",
            ]
            assert settings.github_token is not None
            assert settings.github_token.get_secret_value() not in str(
                events[-1].payload
            )
        await engine.dispose()

    asyncio.run(exercise())
