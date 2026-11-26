from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.control_plane.application.commands import CreateRunCommand
from src.control_plane.application.errors import ConflictError, NotFoundError
from src.control_plane.domain.run_status import can_cancel, can_resume
from src.control_plane.infrastructure.database.models import (
    OutboxMessage,
    Project,
    Run,
    RunEvent,
    RunTask,
)
from src.control_plane.infrastructure.database.repositories import RunRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.runs = RunRepository(session)

    async def require(self, run_id: UUID, *, for_update: bool = False) -> Run:
        run = await self.runs.get(run_id, for_update=for_update)
        if run is None:
            raise NotFoundError("Run not found")
        return run

    async def create(
        self,
        project: Project,
        command: CreateRunCommand,
        *,
        retry_of_id: UUID | None = None,
    ) -> tuple[Run, bool]:
        if project.archived_at is not None:
            raise ConflictError("Cannot create a run for an archived project")
        execution_mode = command.execution_mode or "legacy"
        if execution_mode == "dynamic_parallel":
            raise ConflictError(
                "dynamic_parallel is reserved until shared workspaces and conflict-safe merges are enabled"
            )
        if command.idempotency_key:
            existing = await self.runs.find_idempotent(
                project.id, command.idempotency_key
            )
            if existing is not None:
                return existing, False

        run = Run(
            project_id=project.id,
            retry_of_id=retry_of_id,
            request=command.request.strip(),
            target_stack="python",
            execution_mode=execution_mode,
            clarification_gate_enabled=command.clarification_gate_enabled,
            idempotency_key=command.idempotency_key,
            status="queued",
            phase="queued",
            queued_at=utc_now(),
        )
        self.runs.add(run)
        await self.session.flush()
        self._add_event(
            run.id,
            "run_queued",
            "queued",
            "Run accepted and awaiting durable dispatch",
            {
                "language": "python",
                "execution_mode": run.execution_mode,
            },
        )
        self._add_outbox(run.id, resume=False)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            if command.idempotency_key:
                existing = await self.runs.find_idempotent(
                    project.id, command.idempotency_key
                )
                if existing is not None:
                    return existing, False
            raise ConflictError("Could not create run") from error
        await self.session.refresh(run)
        return run, True

    async def cancel(self, run_id: UUID) -> Run:
        run = await self.require(run_id, for_update=True)
        if not can_cancel(run.status):
            raise ConflictError(f"Run is already {run.status}")
        now = utc_now()
        run.cancel_requested_at = now
        if run.status == "queued":
            run.status = "cancelled"
            run.phase = "cancelled"
            run.finished_at = now
            run.delivery_status = "not_attempted"
        else:
            run.status = "cancelling"
        self._add_event(
            run.id, "cancellation_requested", run.status, "Cancellation requested", {}
        )
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def resume(self, run_id: UUID) -> Run:
        run = await self.require(run_id, for_update=True)
        if not can_resume(run.status):
            raise ConflictError("Only failed, cancelled, or paused runs can be resumed")
        if run.execution_mode != "legacy":
            failed_task_id = await self.session.scalar(
                select(RunTask.id).where(
                    RunTask.run_id == run.id,
                    RunTask.status == "failed",
                )
            )
            if failed_task_id is not None:
                raise ConflictError(
                    "This dynamic run has a failed feature task; retry that task "
                    "with POST /api/v1/runs/{run_id}/tasks/{task_id}/retry"
                )
        run.status = "queued"
        run.phase = "queued"
        run.error_type = None
        run.error_message = None
        run.finished_at = None
        run.cancel_requested_at = None
        run.queued_at = utc_now()
        run.version += 1
        self._add_event(
            run.id,
            "run_requeued",
            "queued",
            "Run queued for checkpoint resume",
            {"version": run.version},
        )
        self._add_outbox(run.id, resume=True)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    def _add_outbox(self, run_id: UUID, *, resume: bool) -> None:
        self.runs.add(
            OutboxMessage(
                topic="run.execute",
                aggregate_id=run_id,
                payload={"run_id": str(run_id), "resume": resume},
            )
        )

    def _add_event(
        self,
        run_id: UUID,
        event_type: str,
        status: str,
        message: str,
        payload: dict,
    ) -> None:
        self.runs.add(
            RunEvent(
                run_id=run_id,
                event_type=event_type,
                status=status,
                message=message,
                payload=payload,
            )
        )
