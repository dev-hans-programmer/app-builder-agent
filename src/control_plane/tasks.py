"""Durable dispatcher, run worker, heartbeat, and stale-run recovery tasks."""

from __future__ import annotations

import asyncio
import socket
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import Task
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select

from src.control_plane.config import get_settings
from src.control_plane.application.artifact_retention import LocalBuildRetentionService
from src.control_plane.application.github_delivery import GitHubDeliveryService
from src.control_plane.infrastructure.artifacts import LocalArtifactStore
from src.control_plane.infrastructure.database import AsyncSessionFactory
from src.control_plane.infrastructure.database.models import (
    Artifact,
    OutboxMessage,
    Project,
    Run,
    RunEvent,
)
from src.control_plane.infrastructure.events import AsyncRunEventBridge
from src.control_plane.queue import celery_app
from src.graph import create_initial_state, create_workflow
from src.observability import (
    RunCancellationRequested,
    use_cancellation_checker,
    use_event_sink,
)

settings = get_settings()
artifact_store = LocalArtifactStore(settings.artifact_root)
github_delivery = GitHubDeliveryService(
    settings=settings,
    session_factory=AsyncSessionFactory,
)
build_retention = LocalBuildRetentionService(
    session_factory=AsyncSessionFactory,
    artifact_store=artifact_store,
)


def _run_async(coroutine):
    """Use one stable event loop per Celery child process."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coroutine)


@celery_app.task(name="control_plane.dispatch_outbox", bind=True)
def dispatch_outbox(self: Task) -> int:
    return _run_async(_dispatch_outbox())


async def _dispatch_outbox() -> int:
    now = datetime.now(timezone.utc)
    published = 0
    async with AsyncSessionFactory() as session:
        messages = list(
            (
                await session.scalars(
                    select(OutboxMessage)
                    .where(
                        OutboxMessage.published_at.is_(None),
                        OutboxMessage.available_at <= now,
                    )
                    .order_by(OutboxMessage.created_at)
                    .limit(settings.outbox_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for message in messages:
            try:
                await asyncio.to_thread(
                    celery_app.send_task,
                    "control_plane.execute_run",
                    kwargs=message.payload,
                    task_id=str(message.id),
                    queue="runs",
                    routing_key="run.execute",
                )
            except Exception as error:
                message.attempts += 1
                message.last_error = f"{type(error).__name__}: {error}"
                message.available_at = now + timedelta(
                    seconds=min(300, 2 ** min(message.attempts, 8))
                )
            else:
                message.attempts += 1
                message.published_at = datetime.now(timezone.utc)
                message.last_error = None
                published += 1
        await session.commit()
    return published


@celery_app.task(name="control_plane.execute_run", bind=True)
def execute_run(self: Task, run_id: str, resume: bool = False) -> str:
    # Also load at the task boundary for solo/eager/custom worker pools where
    # Celery worker lifecycle signals may not run in the usual order.
    load_dotenv()
    return _run_async(_execute_run(UUID(run_id), str(self.request.id), resume=resume))


async def _claim_run(run_id: UUID, task_id: str) -> tuple[Run, Project] | None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update()
        )
        if run is None or run.status not in {"queued", "running"}:
            return None
        if run.cancel_requested_at is not None:
            run.status = "cancelled"
            run.phase = "cancelled"
            run.finished_at = now
            run.delivery_status = "not_attempted"
            await session.commit()
            return None
        active_other_delivery = (
            run.status == "running"
            and run.queue_task_id != task_id
            and run.lease_expires_at is not None
            and run.lease_expires_at > now
        )
        if active_other_delivery:
            return None
        project = await session.get(Project, run.project_id)
        if project is None:
            raise RuntimeError(f"Project for run {run_id} does not exist")
        run.status = "running"
        run.phase = run.phase if run.phase != "queued" else "intake"
        run.queue_task_id = task_id
        run.worker_id = socket.gethostname()
        run.started_at = run.started_at or now
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(minutes=5)
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="worker_claimed",
                status="running",
                message="Durable worker claimed the run",
                payload={"task_id": task_id, "worker_id": run.worker_id},
            )
        )
        await session.commit()
        return run, project


async def _execute_run(run_id: UUID, task_id: str, *, resume: bool) -> str:
    claimed = await _claim_run(run_id, task_id)
    if claimed is None:
        return "ignored"
    run, project = claimed
    loop = asyncio.get_running_loop()
    bridge = AsyncRunEventBridge(
        loop=loop,
        session_factory=AsyncSessionFactory,
        redis_url=settings.redis_url,
        run_id=run.id,
    )
    heartbeat = asyncio.create_task(_heartbeat(run.id, task_id))
    workspace = artifact_store.run_root(project.id, run.id)
    config = {"configurable": {"thread_id": str(run.id)}}
    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            graph = create_workflow(checkpointer=checkpointer)
            checkpoint = await checkpointer.aget(config)
            state: dict[str, Any] | None = None
            if checkpoint is None:
                with use_event_sink(bridge.emit):
                    state = await asyncio.to_thread(
                        create_initial_state,
                        run.request,
                        project.slug,
                        clarification_gate_enabled=run.clarification_gate_enabled,
                        target_stack=run.target_stack,
                        workspace_root=workspace,
                        job_id=f"job-{run.id}",
                        run_id=str(run.id),
                    )
                state["queue_job_id"] = task_id
            with (
                use_event_sink(bridge.emit),
                use_cancellation_checker(bridge.cancellation_requested),
            ):
                final_state = await graph.ainvoke(state, config=config)
        try:
            await _index_artifacts(run.id, workspace)
        except Exception as error:
            await _record_postprocessing_failure(run.id, "artifact_index_failed", error)
            if final_state.get("job_status") == "completed":
                raise
        if final_state.get("job_status") == "completed":
            published = await github_delivery.deliver(
                run_id=run.id,
                project=project,
                state=final_state,
                workspace=workspace,
            )
            if published and not settings.retain_local_builds:
                await build_retention.remove_published_builds(run.id, workspace)
        await _finalize_from_state(run.id, final_state)
        return str(final_state.get("job_status", "completed"))
    except RunCancellationRequested:
        await _mark_terminal(run.id, "cancelled", None)
        return "cancelled"
    except Exception as error:
        await _mark_terminal(run.id, "failed", error)
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _heartbeat(run_id: UUID, task_id: str) -> None:
    while True:
        await asyncio.sleep(30)
        now = datetime.now(timezone.utc)
        async with AsyncSessionFactory() as session:
            run = await session.get(Run, run_id)
            if run is None or run.queue_task_id != task_id or run.status != "running":
                return
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(minutes=5)
            await session.commit()


async def _finalize_from_state(run_id: UUID, state: dict[str, Any]) -> None:
    status = str(state.get("job_status") or "failed")
    async with AsyncSessionFactory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = status
        run.phase = str(state.get("current_phase") or status)
        run.finished_at = datetime.now(timezone.utc)
        run.lease_expires_at = None
        if status == "completed":
            run.progress = 1.0
        else:
            if run.delivery_status == "pending":
                run.delivery_status = "not_attempted"
        if status == "failed" and not run.error_message:
            run.error_type, run.error_message = _failure_from_state(state)
        await session.commit()


def _failure_from_state(state: dict[str, Any]) -> tuple[str, str]:
    quality = state.get("quality_results") or {}
    if quality and not quality.get("passed"):
        failed_checks = [
            f"{stack.get('stack', 'unknown')}:{check.get('category', 'unknown')}"
            for stack in quality.get("stacks", [])
            for check in stack.get("checks", [])
            if check.get("status") == "failed"
        ]
        detail = ", ".join(failed_checks) or str(
            quality.get("error") or "One or more quality checks failed"
        )
        return "QualityGateFailed", f"Failed checks: {detail}"

    traceability = state.get("traceability_result") or {}
    if traceability and not traceability.get("passed"):
        missing = [
            f"{criterion.get('id', 'criterion')}: {', '.join(criterion.get('missing', []))}"
            for criterion in traceability.get("criteria", [])
            if criterion.get("status") != "satisfied"
        ]
        return (
            "TraceabilityGateFailed",
            "; ".join(missing) or "Requirement traceability did not pass",
        )

    selected_outputs = []
    target_stack = state.get("target_stack", "both")
    if target_stack in {"python", "both"}:
        selected_outputs.append(state.get("python_output") or {})
    if target_stack in {"nodejs", "both"}:
        selected_outputs.append(state.get("nodejs_output") or {})
    incomplete = next(
        (output for output in selected_outputs if output.get("status") != "success"),
        {},
    )
    return (
        "GenerationIncomplete",
        str(
            incomplete.get("error")
            or incomplete.get("message")
            or "A selected builder did not produce a successful output"
        ),
    )


async def _record_postprocessing_failure(
    run_id: UUID, event_type: str, error: Exception
) -> None:
    async with AsyncSessionFactory() as session:
        session.add(
            RunEvent(
                run_id=run_id,
                event_type=event_type,
                level="error",
                status="failed",
                message=str(error),
                payload={"error_type": type(error).__name__},
            )
        )
        await session.commit()


async def _mark_terminal(run_id: UUID, status: str, error: Exception | None) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = status
        run.phase = status
        run.finished_at = now
        run.lease_expires_at = None
        if run.delivery_status == "pending":
            run.delivery_status = "not_attempted"
        if error is not None and not run.error_message:
            run.error_type = type(error).__name__
            run.error_message = str(error)
        session.add(
            RunEvent(
                run_id=run_id,
                event_type=f"run_{status}",
                status=status,
                message=str(error) if error else f"Run {status}",
                payload={"error_type": type(error).__name__ if error else None},
            )
        )
        await session.commit()


async def _index_artifacts(run_id: UUID, workspace: Path) -> None:
    async with AsyncSessionFactory() as session:
        known = set(
            (
                await session.scalars(
                    select(Artifact.storage_key).where(Artifact.run_id == run_id)
                )
            ).all()
        )
        for path in artifact_store.iter_files(workspace):
            inspected = await asyncio.to_thread(artifact_store.inspect, path)
            if inspected.storage_key in known:
                continue
            session.add(
                Artifact(
                    run_id=run_id,
                    kind="file",
                    storage_key=inspected.storage_key,
                    filename=inspected.filename,
                    mime_type=inspected.mime_type,
                    sha256=inspected.sha256,
                    size_bytes=inspected.size_bytes,
                )
            )
        await session.commit()


@celery_app.task(name="control_plane.recover_stale_runs")
def recover_stale_runs() -> int:
    return _run_async(_recover_stale_runs())


async def _recover_stale_runs() -> int:
    now = datetime.now(timezone.utc)
    recovered = 0
    async with AsyncSessionFactory() as session:
        stale = list(
            (
                await session.scalars(
                    select(Run)
                    .where(
                        Run.status == "running",
                        Run.lease_expires_at.is_not(None),
                        Run.lease_expires_at < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for run in stale:
            run.status = "queued"
            run.phase = "queued"
            run.queued_at = now
            run.version += 1
            session.add(
                OutboxMessage(
                    topic="run.execute",
                    aggregate_id=run.id,
                    payload={"run_id": str(run.id), "resume": True},
                )
            )
            session.add(
                RunEvent(
                    run_id=run.id,
                    event_type="stale_run_recovered",
                    status="queued",
                    message="Expired worker lease; queued from last checkpoint",
                    payload={"version": run.version},
                )
            )
            recovered += 1
        await session.commit()
    return recovered


def run_worker() -> None:
    celery_app.worker_main(["worker", "-Q", "runs,maintenance", "--loglevel=INFO"])
