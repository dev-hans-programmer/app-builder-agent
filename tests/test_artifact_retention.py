from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from src.control_plane.application.artifact_retention import LocalBuildRetentionService
from src.control_plane.infrastructure.artifacts import LocalArtifactStore
from src.control_plane.infrastructure.database import Base, build_session_factory
from src.control_plane.infrastructure.database import models  # noqa: F401
from src.control_plane.infrastructure.database.models import (
    Artifact,
    Project,
    Run,
    RunEvent,
)


def test_published_builds_are_removed_but_metadata_and_diagnostics_remain(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    session_factory = build_session_factory(engine)
    store = LocalArtifactStore(tmp_path / "artifacts")

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
            await session.flush()

            workspace = store.run_root(project.id, run.id)
            build_file = workspace / "builds" / "python" / "app.py"
            build_file.parent.mkdir(parents=True)
            build_file.write_text("app = object()\n", encoding="utf-8")
            report = workspace / "README.md"
            report.write_text("# Run report\n", encoding="utf-8")

            build_artifact = store.inspect(build_file)
            report_artifact = store.inspect(report)
            session.add_all(
                [
                    Artifact(
                        run_id=run.id,
                        storage_key=build_artifact.storage_key,
                        filename=build_artifact.filename,
                        sha256=build_artifact.sha256,
                        size_bytes=build_artifact.size_bytes,
                    ),
                    Artifact(
                        run_id=run.id,
                        storage_key=report_artifact.storage_key,
                        filename=report_artifact.filename,
                        sha256=report_artifact.sha256,
                        size_bytes=report_artifact.size_bytes,
                    ),
                ]
            )
            await session.commit()
            run_id = run.id

        service = LocalBuildRetentionService(
            session_factory=session_factory,
            artifact_store=store,
        )
        affected = await service.remove_published_builds(run_id, workspace)
        assert affected == 1
        assert not (workspace / "builds").exists()
        assert report.exists()

        async with session_factory() as session:
            artifacts = list(
                (
                    await session.scalars(
                        select(Artifact)
                        .where(Artifact.run_id == run_id)
                        .order_by(Artifact.filename)
                    )
                ).all()
            )
            by_name = {artifact.filename: artifact for artifact in artifacts}
            assert by_name["app.py"].local_available is False
            assert by_name["app.py"].local_deleted_at is not None
            assert by_name["README.md"].local_available is True
            event = await session.scalar(
                select(RunEvent).where(
                    RunEvent.run_id == run_id,
                    RunEvent.event_type == "local_builds_removed",
                )
            )
            assert event is not None
            assert event.payload["artifact_count"] == 1
        await engine.dispose()

    asyncio.run(exercise())
