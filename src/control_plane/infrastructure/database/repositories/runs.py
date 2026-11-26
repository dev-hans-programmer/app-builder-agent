from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.infrastructure.database.models import (
    Artifact,
    Run,
    RunEvent,
    RunStep,
)


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, run_id: UUID, *, for_update: bool = False) -> Run | None:
        statement = select(Run).where(Run.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def find_idempotent(self, project_id: UUID, key: str) -> Run | None:
        return await self.session.scalar(
            select(Run).where(Run.project_id == project_id, Run.idempotency_key == key)
        )

    async def list_for_project(
        self, project_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[Run], int]:
        criteria = Run.project_id == project_id
        items = list(
            (
                await self.session.scalars(
                    select(Run)
                    .where(criteria)
                    .order_by(Run.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(Run).where(criteria)
            )
            or 0
        )
        return items, total

    async def steps(self, run_id: UUID) -> list[RunStep]:
        return list(
            (
                await self.session.scalars(
                    select(RunStep)
                    .where(RunStep.run_id == run_id)
                    .order_by(RunStep.started_at, RunStep.attempt)
                )
            ).all()
        )

    async def events(
        self,
        run_id: UUID,
        *,
        after_id: int = 0,
        limit: int = 250,
        logs_only: bool = False,
    ) -> list[RunEvent]:
        statement = select(RunEvent).where(
            RunEvent.run_id == run_id, RunEvent.id > after_id
        )
        if logs_only:
            statement = statement.where(
                (RunEvent.message.is_not(None))
                | RunEvent.event_type.in_(("log", "step_finished", "run_failed"))
            )
        return list(
            (
                await self.session.scalars(statement.order_by(RunEvent.id).limit(limit))
            ).all()
        )

    async def artifacts(self, run_id: UUID) -> list[Artifact]:
        return list(
            (
                await self.session.scalars(
                    select(Artifact)
                    .where(Artifact.run_id == run_id)
                    .order_by(Artifact.created_at)
                )
            ).all()
        )

    def add(self, entity: object) -> None:
        self.session.add(entity)
