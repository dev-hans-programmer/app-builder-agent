"""Durable dispatcher, run worker, heartbeat, and stale-run recovery tasks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import Task
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.agents.python_builder import build as build_python_task
from src.agents.task_quality import verify_python_task
from src.control_plane.application.dynamic_tasks import (
    persist_task_plan,
    requeue_task,
    schedule_ready_tasks,
    task_spec,
)
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
    RunTask,
    RunTaskAttempt,
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
                task_name, queue, routing_key = {
                    "run.execute": (
                        "control_plane.execute_run",
                        "runs",
                        "run.execute",
                    ),
                    "run.task.execute": (
                        "control_plane.execute_run_task",
                        "run_tasks",
                        "run.task.execute",
                    ),
                    "run.finalize": (
                        "control_plane.finalize_dynamic_run",
                        "runs",
                        "run.finalize",
                    ),
                }[message.topic]
                await asyncio.to_thread(
                    celery_app.send_task,
                    task_name,
                    kwargs=message.payload,
                    task_id=str(message.id),
                    queue=queue,
                    routing_key=routing_key,
                )
            except KeyError:
                message.attempts += 1
                message.last_error = f"Unsupported outbox topic: {message.topic}"
                message.available_at = now + timedelta(minutes=5)
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
        if run.execution_mode != "legacy":
            return await _prepare_dynamic_run(
                run=run,
                project=project,
                workspace=workspace,
                config=config,
                bridge=bridge,
            )
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
        if _should_attempt_github_delivery(
            final_state,
            publish_on_quality_failure=settings.publish_on_quality_failure,
        ):
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


async def _prepare_dynamic_run(
    *,
    run: Run,
    project: Project,
    workspace: Path,
    config: dict[str, Any],
    bridge: AsyncRunEventBridge,
) -> str:
    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(RunTask.id).where(RunTask.run_id == run.id).limit(1)
        )
        if existing is not None:
            locked_run = await session.scalar(
                select(Run).where(Run.id == run.id).with_for_update()
            )
            if locked_run is None:
                return "ignored"
            locked_run.status = "running"
            locked_run.phase = "task_execution"
            locked_run.lease_expires_at = None
            locked_run.worker_id = None
            await schedule_ready_tasks(session, locked_run)
            await session.commit()
            return "task_execution"

    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpoint_database_url
    ) as checkpointer:
        graph = create_workflow(
            checkpointer=checkpointer,
            interrupt_after=["planning"],
        )
        checkpoint = await checkpointer.aget(config)
        state: dict[str, Any] | None = None
        if checkpoint is None:
            with use_event_sink(bridge.emit):
                state = await asyncio.to_thread(
                    create_initial_state,
                    run.request,
                    project.slug,
                    clarification_gate_enabled=run.clarification_gate_enabled,
                    workspace_root=workspace,
                    job_id=f"job-{run.id}",
                    run_id=str(run.id),
                )
            state["queue_job_id"] = run.queue_task_id or ""
        with (
            use_event_sink(bridge.emit),
            use_cancellation_checker(bridge.cancellation_requested),
        ):
            planned_state = await graph.ainvoke(state, config=config)

    plan = planned_state.get("execution_plan") or {}
    validation_errors = list(plan.get("validation_errors") or [])
    if validation_errors:
        raise ValueError("Invalid dynamic task plan: " + "; ".join(validation_errors))
    python_tasks = list(plan.get("python_tasks") or [])
    async with AsyncSessionFactory() as session:
        locked_run = await session.scalar(
            select(Run).where(Run.id == run.id).with_for_update()
        )
        if locked_run is None:
            return "ignored"
        await persist_task_plan(session, locked_run, python_tasks)
        await schedule_ready_tasks(session, locked_run)
        locked_run.status = "running"
        locked_run.phase = "task_execution"
        locked_run.lease_expires_at = None
        locked_run.worker_id = None
        await session.commit()
    return "task_execution"


@celery_app.task(name="control_plane.execute_run_task", bind=True)
def execute_run_task(self: Task, run_id: str, task_id: str) -> str:
    load_dotenv()
    return _run_async(
        _execute_run_task(UUID(run_id), UUID(task_id), str(self.request.id))
    )


async def _claim_run_task(
    run_id: UUID, run_task_id: UUID, queue_task_id: str
) -> tuple[Run, Project, RunTask, RunTaskAttempt] | None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update()
        )
        task = await session.scalar(
            select(RunTask)
            .where(RunTask.id == run_task_id, RunTask.run_id == run_id)
            .options(selectinload(RunTask.dependencies))
            .with_for_update()
        )
        if task is None or run is None or task.status != "queued":
            return None
        if run.cancel_requested_at is not None:
            task.status = "cancelled"
            task.finished_at = now
            await session.commit()
            return None
        project = await session.get(Project, run.project_id)
        if project is None:
            raise RuntimeError(f"Project for run {run_id} does not exist")
        task.status = "running"
        task.attempt_count += 1
        task.queue_task_id = queue_task_id
        task.worker_id = socket.gethostname()
        task.started_at = task.started_at or now
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(minutes=5)
        run.status = "running"
        run.phase = "task_execution"
        run.current_step_id = task.task_key
        run.worker_id = task.worker_id
        run.heartbeat_at = now
        attempt = RunTaskAttempt(
            task_id=task.id,
            attempt=task.attempt_count,
            status="running",
            queue_task_id=queue_task_id,
            worker_id=task.worker_id,
            started_at=now,
        )
        session.add(attempt)
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="run_task_started",
                status="running",
                message=f"Started task {task.task_key}",
                payload={
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "attempt": task.attempt_count,
                    "worker_id": task.worker_id,
                },
            )
        )
        await session.commit()
        return run, project, task, attempt


async def _execute_run_task(run_id: UUID, run_task_id: UUID, queue_task_id: str) -> str:
    claimed = await _claim_run_task(run_id, run_task_id, queue_task_id)
    if claimed is None:
        return "ignored"
    run, project, task, attempt = claimed
    loop = asyncio.get_running_loop()
    bridge = AsyncRunEventBridge(
        loop=loop,
        session_factory=AsyncSessionFactory,
        redis_url=settings.redis_url,
        run_id=run.id,
    )
    heartbeat = asyncio.create_task(_run_task_heartbeat(run.id, task.id, queue_task_id))
    started = time.perf_counter()
    try:
        config = {"configurable": {"thread_id": str(run.id)}}
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            graph = create_workflow(checkpointer=checkpointer)
            snapshot = await graph.aget_state(config)
            state = dict(snapshot.values)
        plan = dict(state.get("execution_plan") or {})
        plan["python_tasks"] = [task_spec(task)]
        state["execution_plan"] = plan
        state["queue_job_id"] = queue_task_id
        with (
            use_event_sink(bridge.emit),
            use_cancellation_checker(bridge.cancellation_requested),
        ):
            result = await asyncio.to_thread(build_python_task, state)
        output = dict(result.get("python_output") or {})
        if output.get("status") != "success":
            raise RuntimeError(
                str(
                    output.get("error")
                    or output.get("message")
                    or "Task generation failed"
                )
            )
        output["task_verification"] = await asyncio.to_thread(
            verify_python_task,
            output["output_dir"],
            list(output.get("patches") or []),
        )
        _refresh_task_patch_hashes(output)
        result["python_output"] = output
        await _complete_run_task(
            run.id,
            task.id,
            attempt.id,
            result,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return "succeeded"
    except RunCancellationRequested:
        await _fail_run_task(
            run.id,
            task.id,
            attempt.id,
            RunCancellationRequested("Run cancellation requested"),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            cancelled=True,
        )
        return "cancelled"
    except Exception as error:
        await _fail_run_task(
            run.id,
            task.id,
            attempt.id,
            error,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


def _refresh_task_patch_hashes(output: dict[str, Any]) -> None:
    """Refresh hashes after task-level formatters have changed generated files."""
    output_dir = Path(str(output["output_dir"])).resolve()
    patches_by_path: dict[str, dict[str, Any]] = {}
    for patch in output.get("patches") or []:
        relative_path = str(patch.get("path") or "")
        candidate = (output_dir / relative_path).resolve()
        if (
            not relative_path
            or output_dir not in candidate.parents
            or not candidate.is_file()
        ):
            continue
        patch["sha256_after"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        patches_by_path[relative_path] = patch

    for task_run in output.get("task_runs") or []:
        for patch in task_run.get("patches") or []:
            refreshed = patches_by_path.get(str(patch.get("path") or ""))
            if refreshed is not None:
                patch["sha256_after"] = refreshed["sha256_after"]


def _add_run_usage(run: Run, observability: dict[str, Any]) -> None:
    """Roll one dynamic task attempt's model usage into its parent run."""
    run.input_tokens = int(run.input_tokens or 0) + int(
        observability.get("input_tokens") or 0
    )
    run.output_tokens = int(run.output_tokens or 0) + int(
        observability.get("output_tokens") or 0
    )
    run.cached_tokens = int(run.cached_tokens or 0) + int(
        observability.get("cached_tokens") or 0
    )
    run.estimated_cost = float(run.estimated_cost or 0) + float(
        observability.get("estimated_cost") or 0
    )


async def _complete_run_task(
    run_id: UUID,
    task_id: UUID,
    attempt_id: UUID,
    result: dict[str, Any],
    *,
    duration_ms: float,
) -> None:
    output = dict(result.get("python_output") or {})
    observability = dict(output.get("observability") or {})
    patch_payload = json.dumps(output.get("patches") or [], sort_keys=True)
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update()
        )
        task = await session.scalar(
            select(RunTask).where(RunTask.id == task_id).with_for_update()
        )
        attempt = await session.get(RunTaskAttempt, attempt_id)
        if run is None or task is None or attempt is None:
            return
        task.status = "succeeded"
        task.finished_at = now
        task.heartbeat_at = now
        task.lease_expires_at = None
        task.output_patch_hash = hashlib.sha256(patch_payload.encode()).hexdigest()
        task.output = result
        task.error_type = None
        task.error_message = None
        attempt.status = "succeeded"
        attempt.ended_at = now
        attempt.duration_ms = duration_ms
        attempt.model = observability.get("model")
        attempt.prompt_version = observability.get("prompt_version")
        attempt.prompt_hash = observability.get("prompt_hash")
        attempt.input_tokens = int(observability.get("input_tokens") or 0)
        attempt.output_tokens = int(observability.get("output_tokens") or 0)
        attempt.cached_tokens = int(observability.get("cached_tokens") or 0)
        attempt.estimated_cost = float(observability.get("estimated_cost") or 0)
        attempt.output = output
        _add_run_usage(run, observability)
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="run_task_succeeded",
                status="succeeded",
                message=f"Completed task {task.task_key}",
                payload={
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "attempt": task.attempt_count,
                    "patch_hash": task.output_patch_hash,
                    "files": output.get("files_created") or [],
                },
            )
        )
        await schedule_ready_tasks(session, run)
        await session.commit()


def _non_retryable_task_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "credit_balance_exhausted",
            "insufficient_quota",
            "invalid api key",
        )
    )


async def _fail_run_task(
    run_id: UUID,
    task_id: UUID,
    attempt_id: UUID,
    error: Exception,
    *,
    duration_ms: float,
    cancelled: bool = False,
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update()
        )
        task = await session.scalar(
            select(RunTask).where(RunTask.id == task_id).with_for_update()
        )
        attempt = await session.get(RunTaskAttempt, attempt_id)
        if run is None or task is None or attempt is None:
            return
        error_type = type(error).__name__
        error_message = str(error)
        attempt.status = "cancelled" if cancelled else "failed"
        attempt.ended_at = now
        attempt.duration_ms = duration_ms
        attempt.error_type = error_type
        attempt.error_message = error_message
        terminal = (
            cancelled
            or _non_retryable_task_error(error)
            or task.attempt_count >= task.max_attempts
        )
        if terminal:
            task.status = "cancelled" if cancelled else "failed"
            task.finished_at = now
            task.error_type = (
                "ModelQuotaExceeded" if _non_retryable_task_error(error) else error_type
            )
            task.error_message = error_message
            task.lease_expires_at = None
            run.status = "cancelled" if cancelled else "failed"
            run.phase = run.status
            run.finished_at = now
            run.error_type = task.error_type
            run.error_message = f"Task {task.task_key} failed: {error_message}"
            run.delivery_status = "not_attempted"
        else:
            task.error_type = error_type
            task.error_message = error_message
            await requeue_task(
                session,
                run,
                task,
                delay_seconds=min(300, 2**task.attempt_count),
            )
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="run_task_failed",
                level="error",
                status=task.status,
                message=f"Task {task.task_key} failed: {error_message}",
                payload={
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "attempt": task.attempt_count,
                    "terminal": terminal,
                    "error_type": task.error_type or error_type,
                },
            )
        )
        await session.commit()


async def _run_task_heartbeat(run_id: UUID, task_id: UUID, queue_task_id: str) -> None:
    while True:
        await asyncio.sleep(30)
        now = datetime.now(timezone.utc)
        async with AsyncSessionFactory() as session:
            task = await session.get(RunTask, task_id)
            run = await session.get(Run, run_id)
            if (
                task is None
                or run is None
                or task.queue_task_id != queue_task_id
                or task.status != "running"
            ):
                return
            task.heartbeat_at = now
            task.lease_expires_at = now + timedelta(minutes=5)
            run.heartbeat_at = now
            await session.commit()


@celery_app.task(name="control_plane.finalize_dynamic_run", bind=True)
def finalize_dynamic_run(self: Task, run_id: str) -> str:
    load_dotenv()
    return _run_async(_finalize_dynamic_run(UUID(run_id), str(self.request.id)))


async def _finalize_dynamic_run(run_id: UUID, queue_task_id: str) -> str:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        run = await session.scalar(
            select(Run).where(Run.id == run_id).with_for_update()
        )
        if run is None or run.status not in {"running", "queued"}:
            return "ignored"
        tasks = list(
            (
                await session.scalars(
                    select(RunTask)
                    .where(RunTask.run_id == run.id)
                    .order_by(RunTask.sequence)
                )
            ).all()
        )
        if not tasks or any(task.status != "succeeded" for task in tasks):
            return "not_ready"
        project = await session.get(Project, run.project_id)
        if project is None:
            raise RuntimeError(f"Project for run {run_id} does not exist")
        run.status = "running"
        run.phase = "integration"
        run.current_step_id = "quality_gate"
        run.queue_task_id = queue_task_id
        run.worker_id = socket.gethostname()
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(minutes=5)
        await session.commit()

    heartbeat = asyncio.create_task(_heartbeat(run_id, queue_task_id))
    workspace = artifact_store.run_root(project.id, run_id)
    config = {"configurable": {"thread_id": str(run_id)}}
    bridge = AsyncRunEventBridge(
        loop=asyncio.get_running_loop(),
        session_factory=AsyncSessionFactory,
        redis_url=settings.redis_url,
        run_id=run_id,
    )
    try:
        python_output = _aggregate_dynamic_python_output(tasks, workspace)
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            graph = create_workflow(checkpointer=checkpointer)
            await graph.aupdate_state(
                config,
                {
                    "python_output": python_output,
                    "python_build_time": sum(
                        float((task.output or {}).get("python_build_time") or 0)
                        for task in tasks
                    ),
                    "current_phase": "generation",
                    "job_status": "running",
                    "queue_job_id": queue_task_id,
                },
                as_node="python_builder",
            )
            with (
                use_event_sink(bridge.emit),
                use_cancellation_checker(bridge.cancellation_requested),
            ):
                final_state = await graph.ainvoke(None, config=config)
        try:
            await _index_artifacts(run_id, workspace)
        except Exception as error:
            await _record_postprocessing_failure(run_id, "artifact_index_failed", error)
            if final_state.get("job_status") == "completed":
                raise
        if _should_attempt_github_delivery(
            final_state,
            publish_on_quality_failure=settings.publish_on_quality_failure,
        ):
            published = await github_delivery.deliver(
                run_id=run_id,
                project=project,
                state=final_state,
                workspace=workspace,
            )
            if published and not settings.retain_local_builds:
                await build_retention.remove_published_builds(run_id, workspace)
        await _finalize_from_state(run_id, final_state)
        return str(final_state.get("job_status", "completed"))
    except RunCancellationRequested:
        await _mark_terminal(run_id, "cancelled", None)
        return "cancelled"
    except Exception as error:
        await _mark_terminal(run_id, "failed", error)
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


def _aggregate_dynamic_python_output(
    tasks: list[RunTask], workspace: Path
) -> dict[str, Any]:
    output_dir = workspace / "builds" / "python"
    files: set[str] = set()
    task_runs: list[dict[str, Any]] = []
    patches: list[dict[str, Any]] = []
    usage_items: list[dict[str, Any]] = []
    for task in tasks:
        result = dict(task.output or {})
        output = dict(result.get("python_output") or {})
        files.update(str(item) for item in output.get("files_created") or [])
        task_runs.extend(output.get("task_runs") or [])
        patches.extend(output.get("patches") or [])
        usage_items.append(dict(output.get("observability") or {}))
    observability: dict[str, Any] = {
        "model_calls": sum(int(item.get("model_calls") or 1) for item in usage_items),
    }
    for field in (
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "total_tokens",
        "estimated_cost",
    ):
        observability[field] = sum(float(item.get(field) or 0) for item in usage_items)
    if usage_items:
        observability["model"] = usage_items[-1].get("model")
        observability["prompt_version"] = usage_items[-1].get("prompt_version")
    return {
        "status": "success",
        "output_dir": str(output_dir),
        "files_created": sorted(files),
        "artifact_paths": [str(output_dir / path) for path in sorted(files)],
        "framework": "FastAPI",
        "file_count": len(files),
        "task_runs": task_runs,
        "patches": patches,
        "observability": observability,
    }


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
        run.phase = (
            str(state.get("current_phase") or status)
            if status == "completed"
            else status
        )
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


def _should_attempt_github_delivery(
    state: dict[str, Any], *, publish_on_quality_failure: bool
) -> bool:
    """Allow opted-in delivery of generated code that failed quality checks."""
    if state.get("job_status") == "completed":
        return True
    if not publish_on_quality_failure or state.get("job_status") != "failed":
        return False

    quality = state.get("quality_results") or {}
    if quality.get("passed") is not False:
        return False

    return (state.get("python_output") or {}).get("status") == "success"


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

    incomplete = state.get("python_output") or {}
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


@celery_app.task(name="control_plane.recover_stale_run_tasks")
def recover_stale_run_tasks() -> int:
    return _run_async(_recover_stale_run_tasks())


async def _recover_stale_run_tasks() -> int:
    now = datetime.now(timezone.utc)
    recovered = 0
    async with AsyncSessionFactory() as session:
        stale = list(
            (
                await session.execute(
                    select(RunTask.id, RunTask.run_id).where(
                        RunTask.status == "running",
                        RunTask.lease_expires_at.is_not(None),
                        RunTask.lease_expires_at < now,
                    )
                )
            ).all()
        )
        for task_id, run_id in stale:
            run = await session.scalar(
                select(Run).where(Run.id == run_id).with_for_update(skip_locked=True)
            )
            if run is None or run.status not in {"running", "queued"}:
                continue
            task = await session.scalar(
                select(RunTask)
                .where(
                    RunTask.id == task_id,
                    RunTask.status == "running",
                    RunTask.lease_expires_at < now,
                )
                .with_for_update(skip_locked=True)
            )
            if task is None:
                continue
            attempt = await session.scalar(
                select(RunTaskAttempt).where(
                    RunTaskAttempt.task_id == task.id,
                    RunTaskAttempt.attempt == task.attempt_count,
                )
            )
            if attempt is not None and attempt.status == "running":
                attempt.status = "failed"
                attempt.ended_at = now
                attempt.error_type = "WorkerLeaseExpired"
                attempt.error_message = (
                    "Worker lease expired before task acknowledgement"
                )
            await requeue_task(session, run, task)
            session.add(
                RunEvent(
                    run_id=run.id,
                    event_type="stale_run_task_recovered",
                    status="queued",
                    message=f"Recovered expired task {task.task_key}",
                    payload={
                        "task_id": str(task.id),
                        "task_key": task.task_key,
                        "attempt": task.attempt_count,
                    },
                )
            )
            recovered += 1
        await session.commit()
    return recovered


def run_worker() -> None:
    celery_app.worker_main(
        ["worker", "-Q", "runs,run_tasks,maintenance", "--loglevel=INFO"]
    )
