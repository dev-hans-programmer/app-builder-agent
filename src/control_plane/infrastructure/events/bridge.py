"""Thread-safe bridge from synchronous workflow hooks to async persistence."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.control_plane.infrastructure.database.models import Run, RunEvent, RunStep

WORKFLOW_STEPS = (
    "parse_input",
    "backend_policy",
    "requirement_analysis",
    "acceptance_approval",
    "architecture_planning",
    "spec_decomposition",
    "planning",
    "generation_start",
    "python_builder",
    "quality_gate",
    "targeted_repair",
    "traceability",
    "generate_report",
)


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class AsyncRunEventBridge:
    """Persists each workflow event before allowing the node to continue."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        session_factory: async_sessionmaker[AsyncSession],
        redis_url: str,
        run_id: UUID,
    ):
        self.loop = loop
        self.session_factory = session_factory
        self.redis_url = redis_url
        self.run_id = run_id

    def emit(self, event: dict[str, Any]) -> None:
        future = asyncio.run_coroutine_threadsafe(self._persist(event), self.loop)
        future.result(timeout=30)

    def cancellation_requested(self) -> bool:
        future = asyncio.run_coroutine_threadsafe(self._is_cancelled(), self.loop)
        return bool(future.result(timeout=10))

    async def _is_cancelled(self) -> bool:
        async with self.session_factory() as session:
            requested = await session.scalar(
                select(Run.cancel_requested_at).where(Run.id == self.run_id)
            )
            return requested is not None

    async def _persist(self, payload: dict[str, Any]) -> None:
        source_event_id = str(payload.get("event_id") or "") or None
        async with self.session_factory() as session:
            if source_event_id:
                existing = await session.scalar(
                    select(RunEvent.id).where(
                        RunEvent.run_id == self.run_id,
                        RunEvent.source_event_id == source_event_id,
                    )
                )
                if existing is not None:
                    return

            run = await session.scalar(
                select(Run).where(Run.id == self.run_id).with_for_update()
            )
            if run is None:
                raise RuntimeError(f"Run {self.run_id} disappeared while executing")

            event_type = str(payload.get("event_type") or "event")
            step_id = payload.get("step_id")
            event = RunEvent(
                run_id=self.run_id,
                source_event_id=source_event_id,
                step_id=str(step_id) if step_id else None,
                event_type=event_type,
                level="error" if payload.get("error_message") else "info",
                status=payload.get("status"),
                message=payload.get("message") or payload.get("error_message"),
                payload=payload,
                occurred_at=_datetime(payload.get("timestamp"))
                or datetime.now(timezone.utc),
            )
            session.add(event)
            await self._update_run(session, run, payload)
            await self._upsert_step(session, payload)
            await session.commit()
            await session.refresh(event)

        redis = Redis.from_url(self.redis_url)
        try:
            try:
                await redis.publish(
                    f"run:{self.run_id}:events",
                    json.dumps({"run_id": str(self.run_id), "event_id": event.id}),
                )
            except Exception:
                # PostgreSQL is authoritative; SSE polling still works without Redis.
                pass
        finally:
            await redis.aclose()

    async def _update_run(
        self, session: AsyncSession, run: Run, payload: dict[str, Any]
    ) -> None:
        now = datetime.now(timezone.utc)
        event_type = payload.get("event_type")
        step_id = payload.get("step_id")
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(minutes=5)
        if payload.get("phase"):
            run.phase = str(payload["phase"])
        if step_id and step_id != "workflow":
            run.current_step_id = str(step_id)
            if step_id in WORKFLOW_STEPS:
                run.progress = round(
                    (WORKFLOW_STEPS.index(step_id) + 1) / len(WORKFLOW_STEPS), 4
                )
        if event_type == "run_started":
            run.status = "running"
            run.started_at = _datetime(payload.get("started_at")) or now
        elif event_type == "run_finished":
            # LangGraph is finished, but artifact indexing and external delivery
            # are still part of the durable run contract.
            run.phase = "finalizing"
        elif event_type == "run_cancelled":
            run.status = "cancelled"
            run.phase = "cancelled"
            run.finished_at = now
            run.lease_expires_at = None
        if not payload.get("usage_detail"):
            run.input_tokens += int(payload.get("input_tokens") or 0)
            run.output_tokens += int(payload.get("output_tokens") or 0)
            run.cached_tokens += int(payload.get("cached_tokens") or 0)
            run.estimated_cost += float(payload.get("estimated_cost") or 0)

    async def _upsert_step(
        self, session: AsyncSession, payload: dict[str, Any]
    ) -> None:
        if payload.get("event_type") not in {"step_started", "step_finished"}:
            return
        step_id = str(payload.get("step_id") or "")
        if not step_id:
            return
        attempt = int(payload.get("attempt") or 1)
        step = await session.scalar(
            select(RunStep).where(
                RunStep.run_id == self.run_id,
                RunStep.step_id == step_id,
                RunStep.attempt == attempt,
            )
        )
        if step is None:
            step = RunStep(run_id=self.run_id, step_id=step_id, attempt=attempt)
            session.add(step)
        for field in (
            "parent_step_id",
            "spec_id",
            "task_id",
            "status",
            "model",
            "prompt_version",
            "prompt_hash",
            "command",
            "exit_code",
            "retry_reason",
            "error_type",
            "error_message",
            "stack_trace",
            "duration_ms",
            "worker_id",
        ):
            value = payload.get(field)
            if value is not None:
                setattr(step, field, value)
        step.queue_task_id = payload.get("queue_job_id") or step.queue_task_id
        step.started_at = _datetime(payload.get("started_at")) or step.started_at
        step.ended_at = _datetime(payload.get("ended_at")) or step.ended_at
        step.input_tokens = int(payload.get("input_tokens") or step.input_tokens or 0)
        step.output_tokens = int(
            payload.get("output_tokens") or step.output_tokens or 0
        )
        step.cached_tokens = int(
            payload.get("cached_tokens") or step.cached_tokens or 0
        )
        step.estimated_cost = float(
            payload.get("estimated_cost") or step.estimated_cost or 0
        )
