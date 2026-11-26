from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.control_plane.app import create_app
from src.control_plane.config import ControlPlaneSettings
from src.control_plane.infrastructure.artifacts import LocalArtifactStore
from src.control_plane.infrastructure.database import Base, build_session_factory
from src.control_plane.infrastructure.database import models  # noqa: F401
from src.control_plane.infrastructure.database.models import (
    OutboxMessage,
    Run,
    RunEvent,
    RunTask,
    RunTaskAttempt,
)
from src.control_plane.queue import celery_app
from src.control_plane.tasks import (
    _failure_from_state,
    _should_attempt_github_delivery,
)


def _test_app(tmp_path: Path):
    database_path = tmp_path / "control-plane.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = build_session_factory(engine)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    settings = ControlPlaneSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        artifact_root=tmp_path / "artifacts",
        retain_local_builds=True,
    )
    assert settings.retain_local_builds is True
    store = LocalArtifactStore(settings.artifact_root)
    return (
        create_app(
            settings=settings,
            session_factory=session_factory,
            artifact_store=store,
            engine=engine,
        ),
        session_factory,
        store,
    )


def test_quality_failure_delivery_is_explicit_and_requires_generated_code() -> None:
    failed_quality_state = {
        "job_status": "failed",
        "python_output": {"status": "success"},
        "quality_results": {"passed": False},
    }

    assert not _should_attempt_github_delivery(
        failed_quality_state, publish_on_quality_failure=False
    )
    assert _should_attempt_github_delivery(
        failed_quality_state, publish_on_quality_failure=True
    )
    assert not _should_attempt_github_delivery(
        {**failed_quality_state, "python_output": {"status": "failed"}},
        publish_on_quality_failure=True,
    )


def test_non_quality_failures_are_not_published_by_escape_hatch() -> None:
    state = {
        "job_status": "failed",
        "python_output": {"status": "success"},
        "quality_results": {"passed": True},
        "traceability_result": {"passed": False},
    }

    assert not _should_attempt_github_delivery(state, publish_on_quality_failure=True)


def test_project_run_lifecycle_and_durable_outbox(tmp_path: Path) -> None:
    app, session_factory, _ = _test_app(tmp_path)
    with TestClient(app) as client:
        project_response = client.post(
            "/api/v1/projects",
            json={"name": "Todo Control Plane", "description": "test"},
        )
        assert project_response.status_code == 201
        project = project_response.json()

        run_payload = {
            "request": "Build a production todo API",
            "idempotency_key": "request-1",
        }
        first = client.post(f"/api/v1/projects/{project['id']}/runs", json=run_payload)
        assert first.status_code == 202
        run = first.json()
        assert run["status"] == "queued"
        assert run["delivery_status"] == "pending"
        assert run["repository_url"] is None

        duplicate = client.post(
            f"/api/v1/projects/{project['id']}/runs", json=run_payload
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == run["id"]

        details = client.get(f"/api/v1/runs/{run['id']}")
        assert details.status_code == 200
        events = client.get(f"/api/v1/runs/{run['id']}/events").json()
        assert [event["event_type"] for event in events] == ["run_queued"]

        cancelled = client.post(f"/api/v1/runs/{run['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert (
            client.get(f"/api/v1/runs/{run['id']}").json()["delivery_status"]
            == "not_attempted"
        )

        resumed = client.post(f"/api/v1/runs/{run['id']}/resume")
        assert resumed.status_code == 202
        assert resumed.json()["status"] == "queued"

        retried = client.post(f"/api/v1/runs/{run['id']}/retry")
        assert retried.status_code == 202
        assert retried.json()["retry_of_id"] == run["id"]

    async def assert_outbox() -> None:
        async with session_factory() as session:
            from sqlalchemy import func, select

            outbox_count = await session.scalar(
                select(func.count()).select_from(OutboxMessage)
            )
            event_count = await session.scalar(
                select(func.count()).select_from(RunEvent)
            )
            assert outbox_count == 3
            assert event_count >= 4

    asyncio.run(assert_outbox())


def test_run_creation_rejects_language_selection(tmp_path: Path) -> None:
    app, _, _ = _test_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "Python Only"}).json()

        response = client.post(
            f"/api/v1/projects/{project['id']}/runs",
            json={"request": "Build an API", "target_stack": "python"},
        )

    assert response.status_code == 422


def test_api_surface_includes_run_task_operations(tmp_path: Path) -> None:
    app, _, _ = _test_app(tmp_path)
    operations = [
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in {"get", "post", "patch", "delete"}
    ]
    assert len(operations) == 23
    assert ("GET", "/api/v1/runs/{run_id}/tasks") in operations
    assert ("POST", "/api/v1/runs/{run_id}/tasks/{task_id}/retry") in operations


def test_run_task_projection_attempts_and_manual_retry(tmp_path: Path) -> None:
    app, session_factory, _ = _test_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "Tasks"}).json()
        run = client.post(
            f"/api/v1/projects/{project['id']}/runs",
            json={"request": "Build task API", "execution_mode": "dynamic_serial"},
        ).json()

        async def add_failed_task() -> str:
            from uuid import UUID

            async with session_factory() as session:
                task = RunTask(
                    run_id=UUID(run["id"]),
                    task_key="feature-posts-01",
                    plan_task_id="PY-TASK-003",
                    kind="feature",
                    title="Posts",
                    objective="Implement posts",
                    status="failed",
                    sequence=3,
                    attempt_count=1,
                    max_attempts=1,
                    acceptance_criteria_ids=["AC-001"],
                )
                session.add(task)
                await session.flush()
                session.add(
                    RunTaskAttempt(
                        task_id=task.id,
                        attempt=1,
                        status="failed",
                        error_type="TaskVerificationError",
                        error_message="lint failed",
                    )
                )
                persisted_run = await session.get(Run, task.run_id)
                assert persisted_run is not None
                persisted_run.status = "failed"
                persisted_run.phase = "failed"
                await session.commit()
                return str(task.id)

        task_id = asyncio.run(add_failed_task())
        tasks = client.get(f"/api/v1/runs/{run['id']}/tasks")
        assert tasks.status_code == 200
        assert tasks.json()[0]["task_key"] == "feature-posts-01"
        attempts = client.get(f"/api/v1/runs/{run['id']}/tasks/{task_id}/attempts")
        assert attempts.status_code == 200
        assert attempts.json()[0]["error_type"] == "TaskVerificationError"
        resumed = client.post(f"/api/v1/runs/{run['id']}/resume")
        assert resumed.status_code == 409
        assert "failed feature task" in resumed.json()["error"]["message"]
        retried = client.post(f"/api/v1/runs/{run['id']}/tasks/{task_id}/retry")
        assert retried.status_code == 202
        assert retried.json()["status"] == "queued"


def test_dynamic_parallel_is_rejected_until_workspace_isolation_exists(
    tmp_path: Path,
) -> None:
    app, _, _ = _test_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/v1/projects", json={"name": "Parallel"}).json()
        response = client.post(
            f"/api/v1/projects/{project['id']}/runs",
            json={
                "request": "Build an API",
                "execution_mode": "dynamic_parallel",
            },
        )

    assert response.status_code == 409
    assert "conflict-safe merges" in response.json()["error"]["message"]


def test_local_artifact_store_is_run_isolated_and_traversal_safe(
    tmp_path: Path,
) -> None:
    from uuid import uuid4

    store = LocalArtifactStore(tmp_path / "artifacts")
    run_root = store.run_root(uuid4(), uuid4())
    artifact = run_root / "report.md"
    artifact.write_text("result", encoding="utf-8")
    inspected = store.inspect(artifact)

    assert store.resolve(inspected.storage_key) == artifact.resolve()
    assert inspected.sha256
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        store.resolve("../outside.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("Traversal outside artifact root was accepted")

    build_file = run_root / "builds" / "python" / "main.py"
    build_file.parent.mkdir(parents=True)
    build_file.write_text("pass\n", encoding="utf-8")
    external_interpreter = tmp_path / "external-python"
    external_interpreter.write_text("binary", encoding="utf-8")
    environment_link = run_root / ".venv" / "bin" / "python"
    environment_link.parent.mkdir(parents=True)
    environment_link.symlink_to(external_interpreter)
    direct_link = run_root / "python-link"
    direct_link.symlink_to(external_interpreter)
    indexed = set(store.iter_files(run_root))
    assert artifact in indexed
    assert build_file in indexed
    assert environment_link not in indexed
    assert direct_link not in indexed

    storage_prefix = store.remove_tree(run_root / "builds")
    assert storage_prefix is not None and storage_prefix.endswith("/builds")
    assert not build_file.exists()
    try:
        store.remove_tree(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("Cleanup outside artifact root was accepted")


def test_failed_run_prefers_quality_error_over_secondary_traceability() -> None:
    error_type, message = _failure_from_state(
        {
            "python_output": {"status": "success"},
            "quality_results": {
                "passed": False,
                "stacks": [
                    {
                        "stack": "python",
                        "checks": [
                            {"category": "format", "status": "failed"},
                            {"category": "test", "status": "passed"},
                        ],
                    }
                ],
            },
            "traceability_result": {
                "passed": False,
                "criteria": [
                    {
                        "id": "AC-001",
                        "status": "missing_evidence",
                        "missing": ["passing quality gates"],
                    }
                ],
            },
        }
    )

    assert error_type == "QualityGateFailed"
    assert message == "Failed checks: python:format"


def test_run_queue_uses_late_ack_and_quorum_delivery() -> None:
    run_queue = next(
        queue for queue in celery_app.conf.task_queues if queue.name == "runs"
    )
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert run_queue.queue_arguments == {"x-queue-type": "quorum"}
