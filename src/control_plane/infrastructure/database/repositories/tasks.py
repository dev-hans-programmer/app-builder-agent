from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.control_plane.infrastructure.database.models import RunTask, RunTaskAttempt


class RunTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_run(self, run_id: UUID) -> list[RunTask]:
        return list(
            (
                await self.session.scalars(
                    select(RunTask)
                    .where(RunTask.run_id == run_id)
                    .options(selectinload(RunTask.dependencies))
                    .order_by(RunTask.sequence, RunTask.created_at)
                )
            ).all()
        )

    async def get(
        self, run_id: UUID, task_id: UUID, *, for_update: bool = False
    ) -> RunTask | None:
        statement = (
            select(RunTask)
            .where(RunTask.run_id == run_id, RunTask.id == task_id)
            .options(selectinload(RunTask.dependencies))
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def attempts(self, task_id: UUID) -> list[RunTaskAttempt]:
        return list(
            (
                await self.session.scalars(
                    select(RunTaskAttempt)
                    .where(RunTaskAttempt.task_id == task_id)
                    .order_by(RunTaskAttempt.attempt)
                )
            ).all()
        )

    def add(self, entity: object) -> None:
        self.session.add(entity)
