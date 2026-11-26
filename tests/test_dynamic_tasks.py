from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from src.control_plane.application.dynamic_tasks import (
    persist_task_plan,
    schedule_ready_tasks,
)
from src.control_plane.infrastructure.database import Base, build_session_factory
from src.control_plane.infrastructure.database import models  # noqa: F401
from src.control_plane.infrastructure.database.models import (
    OutboxMessage,
    Project,
    Run,
    RunTask,
)


def test_dynamic_serial_scheduler_unlocks_one_dependency_at_a_time(tmp_path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}")
        factory = build_session_factory(engine)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with factory() as session:
                project = Project(name="Catalog", slug=f"catalog-{uuid4().hex[:8]}")
                session.add(project)
                await session.flush()
                run = Run(
                    project_id=project.id,
                    request="Build a catalog",
                    target_stack="python",
                    execution_mode="dynamic_serial",
                    status="running",
                    phase="planning",
                )
                session.add(run)
                await session.flush()
                await persist_task_plan(
                    session,
                    run,
                    [
                        {
                            "id": "PY-TASK-001",
                            "task_key": "foundation",
                            "kind": "foundation",
                            "title": "Foundation",
                            "objective": "Create the project",
                            "dependencies": [],
                        },
                        {
                            "id": "PY-TASK-002",
                            "task_key": "catalog",
                            "kind": "feature",
                            "title": "Catalog",
                            "objective": "Implement catalog",
                            "dependencies": ["PY-TASK-001"],
                            "acceptance_criteria_ids": ["AC-001"],
                        },
                    ],
                )
                assert await schedule_ready_tasks(session, run) == 1
                await session.commit()

                tasks = list(
                    (
                        await session.scalars(
                            select(RunTask).order_by(RunTask.sequence)
                        )
                    ).all()
                )
                assert [task.status for task in tasks] == [
                    "queued",
                    "waiting_dependencies",
                ]
                outbox = list((await session.scalars(select(OutboxMessage))).all())
                assert [message.topic for message in outbox] == ["run.task.execute"]

                tasks[0].status = "succeeded"
                assert await schedule_ready_tasks(session, run) == 1
                await session.commit()
                await session.refresh(tasks[1])
                assert tasks[1].status == "queued"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
