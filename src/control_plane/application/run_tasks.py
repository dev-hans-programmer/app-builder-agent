from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.application.dynamic_tasks import requeue_task
from src.control_plane.application.errors import ConflictError, NotFoundError
from src.control_plane.infrastructure.database.models import Run, RunEvent, RunTask
from src.control_plane.infrastructure.database.repositories import RunTaskRepository


class RunTaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.tasks = RunTaskRepository(session)

    async def require(self, run_id: UUID, task_id: UUID) -> RunTask:
        task = await self.tasks.get(run_id, task_id)
        if task is None:
            raise NotFoundError("Run task not found")
        return task

    async def retry(self, run_id: UUID, task_id: UUID) -> RunTask:
        run = await self.session.get(Run, run_id, with_for_update=True)
        if run is None:
            raise NotFoundError("Run not found")
        task = await self.tasks.get(run_id, task_id, for_update=True)
        if task is None:
            raise NotFoundError("Run task not found")
        if task.status != "failed":
            raise ConflictError("Only failed run tasks can be retried")
        task.max_attempts = max(task.max_attempts, task.attempt_count + 1)
        task.error_type = None
        task.error_message = None
        task.finished_at = None
        run.status = "running"
        run.phase = "task_execution"
        run.finished_at = None
        run.error_type = None
        run.error_message = None
        run.delivery_status = "pending"
        await requeue_task(self.session, run, task)
        self.session.add(
            RunEvent(
                run_id=run.id,
                event_type="run_task_retry_requested",
                status="queued",
                message=f"Manual retry queued for task {task.task_key}",
                payload={
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "next_attempt": task.attempt_count + 1,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task
