from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.control_plane.infrastructure.database.models import (
    OutboxMessage,
    Run,
    RunEvent,
    RunTask,
    RunTaskDependency,
)


ACTIVE_TASK_STATUSES = {"queued", "running", "verifying"}
TERMINAL_TASK_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def persist_task_plan(
    session: AsyncSession, run: Run, python_tasks: list[dict[str, Any]]
) -> list[RunTask]:
    """Persist a validated planner DAG once and queue its first ready task."""
    existing = list(
        (
            await session.scalars(
                select(RunTask)
                .where(RunTask.run_id == run.id)
                .options(selectinload(RunTask.dependencies))
                .order_by(RunTask.sequence)
            )
        ).all()
    )
    if existing:
        return existing
    if not python_tasks:
        raise ValueError("Dynamic execution requires at least one Python task")

    by_plan_id: dict[str, RunTask] = {}
    for index, planned in enumerate(python_tasks, start=1):
        plan_task_id = str(planned.get("id") or f"PY-TASK-{index:03d}")
        task = RunTask(
            run_id=run.id,
            task_key=str(planned.get("task_key") or plan_task_id.lower()),
            plan_task_id=plan_task_id,
            kind=str(planned.get("kind") or "feature"),
            title=str(planned.get("title") or plan_task_id),
            objective=str(planned.get("objective") or ""),
            status="waiting_dependencies" if planned.get("dependencies") else "ready",
            sequence=int(planned.get("order") or index),
            priority=int(planned.get("priority") or 100),
            weight=float(planned.get("weight") or 1.0),
            acceptance_criteria_ids=list(planned.get("acceptance_criteria_ids") or []),
            contract_ids=list(planned.get("contract_ids") or []),
            policy_rule_ids=list(planned.get("policy_rule_ids") or []),
            allowed_paths=list(planned.get("allowed_paths") or []),
            verification=list(planned.get("verification_categories") or []),
            max_attempts=int(planned.get("max_attempts") or 3),
        )
        session.add(task)
        by_plan_id[plan_task_id] = task
    await session.flush()

    for planned in python_tasks:
        task = by_plan_id[str(planned["id"])]
        for dependency_id in planned.get("dependencies", []):
            dependency = by_plan_id.get(str(dependency_id))
            if dependency is None:
                raise ValueError(
                    f"Task {planned['id']} references unknown dependency {dependency_id}"
                )
            session.add(
                RunTaskDependency(
                    task_id=task.id,
                    depends_on_task_id=dependency.id,
                )
            )

    run.phase = "task_execution"
    run.current_step_id = None
    run.finished_at = None
    session.add(
        RunEvent(
            run_id=run.id,
            event_type="task_plan_persisted",
            status="running",
            message=f"Persisted {len(python_tasks)} dynamic Python tasks",
            payload={
                "task_count": len(python_tasks),
                "strategy": "dynamic-v1",
                "execution_mode": run.execution_mode,
            },
        )
    )
    await session.flush()
    return list(by_plan_id.values())


async def schedule_ready_tasks(session: AsyncSession, run: Run) -> int:
    """Queue dependency-satisfied tasks, respecting serial run execution."""
    tasks = list(
        (
            await session.scalars(
                select(RunTask)
                .where(RunTask.run_id == run.id)
                .options(selectinload(RunTask.dependencies))
                .order_by(RunTask.priority, RunTask.sequence)
                .with_for_update()
            )
        ).all()
    )
    if not tasks:
        return 0

    statuses = {task.id: task.status for task in tasks}
    for task in tasks:
        if task.status != "waiting_dependencies":
            continue
        dependency_statuses = [
            statuses.get(edge.depends_on_task_id) for edge in task.dependencies
        ]
        if any(
            status in {"failed", "blocked", "cancelled"}
            for status in dependency_statuses
        ):
            task.status = "blocked"
            task.error_type = "DependencyFailed"
            task.error_message = "A required predecessor did not succeed"
            task.finished_at = utc_now()
        elif dependency_statuses and all(
            status == "succeeded" for status in dependency_statuses
        ):
            task.status = "ready"

    if run.execution_mode == "dynamic_serial" and any(
        task.status in ACTIVE_TASK_STATUSES for task in tasks
    ):
        await _update_run_progress(run, tasks)
        return 0

    ready = [task for task in tasks if task.status == "ready"]
    if run.execution_mode != "dynamic_parallel":
        ready = ready[:1]

    now = utc_now()
    for task in ready:
        task.status = "queued"
        task.queued_at = now
        session.add(
            OutboxMessage(
                topic="run.task.execute",
                aggregate_id=task.id,
                payload={"run_id": str(run.id), "task_id": str(task.id)},
            )
        )
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="run_task_queued",
                status="queued",
                message=f"Queued task {task.task_key}",
                payload={
                    "task_id": str(task.id),
                    "task_key": task.task_key,
                    "plan_task_id": task.plan_task_id,
                },
            )
        )

    await _update_run_progress(run, tasks)
    if tasks and all(task.status == "succeeded" for task in tasks):
        if run.phase != "integration_queued":
            run.phase = "integration_queued"
            session.add(
                OutboxMessage(
                    topic="run.finalize",
                    aggregate_id=run.id,
                    payload={"run_id": str(run.id)},
                )
            )
            session.add(
                RunEvent(
                    run_id=run.id,
                    event_type="run_integration_queued",
                    status="queued",
                    message="All dynamic tasks succeeded; final integration queued",
                    payload={"task_count": len(tasks)},
                )
            )
    return len(ready)


async def requeue_task(
    session: AsyncSession, run: Run, task: RunTask, *, delay_seconds: int = 0
) -> None:
    task.status = "queued"
    task.queued_at = utc_now()
    task.worker_id = None
    task.queue_task_id = None
    task.heartbeat_at = None
    task.lease_expires_at = None
    session.add(
        OutboxMessage(
            topic="run.task.execute",
            aggregate_id=task.id,
            payload={"run_id": str(run.id), "task_id": str(task.id)},
            available_at=utc_now() + timedelta(seconds=delay_seconds),
        )
    )


async def _update_run_progress(run: Run, tasks: list[RunTask]) -> None:
    total = sum(task.weight for task in tasks) or 1.0
    completed = sum(task.weight for task in tasks if task.status == "succeeded")
    run.progress = min(0.9, 0.1 + (completed / total) * 0.8)
    active = next((task for task in tasks if task.status in ACTIVE_TASK_STATUSES), None)
    run.current_step_id = active.task_key if active else None


def task_spec(task: RunTask) -> dict[str, Any]:
    """Reconstruct the immutable generation contract stored in the database."""
    return {
        "id": task.plan_task_id,
        "task_key": task.task_key,
        "order": task.sequence,
        "kind": task.kind,
        "module": task.kind,
        "title": task.title,
        "objective": (
            task.objective
            if not task.error_message
            else f"{task.objective}\n\nPrevious attempt failed; repair this evidence: {task.error_message}"
        ),
        "dependencies": [str(item) for item in task.depends_on_task_ids],
        "acceptance_criteria_ids": list(task.acceptance_criteria_ids),
        "contract_ids": list(task.contract_ids),
        "policy_rule_ids": list(task.policy_rule_ids),
        "allowed_paths": list(task.allowed_paths),
        "verification_categories": list(task.verification),
        "max_attempts": task.max_attempts,
        "status": "ready",
    }
