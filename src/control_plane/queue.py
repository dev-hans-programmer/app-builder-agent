"""Celery topology for durable run delivery and maintenance work."""

from celery import Celery
from celery.signals import worker_init, worker_process_init
from dotenv import load_dotenv
from kombu import Exchange, Queue

from src.control_plane.config import get_settings

settings = get_settings()


def _load_worker_environment(**_: object) -> None:
    """Match the CLI bootstrap without mutating API or test process globals."""
    load_dotenv()


worker_init.connect(_load_worker_environment, weak=False)
worker_process_init.connect(_load_worker_environment, weak=False)

run_exchange = Exchange("runs", type="direct", durable=True)
run_task_exchange = Exchange("run_tasks", type="direct", durable=True)
maintenance_exchange = Exchange("maintenance", type="direct", durable=True)

celery_app = Celery(
    "app_builder_control_plane",
    broker=settings.broker_url,
    include=["src.control_plane.tasks"],
)
celery_app.conf.update(
    result_backend=None,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_transport_options={"confirm_publish": True},
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="runs",
    task_queues=(
        Queue(
            "run_tasks",
            exchange=run_task_exchange,
            routing_key="run.task.execute",
            durable=True,
            queue_arguments={"x-queue-type": "quorum"},
        ),
        Queue(
            "runs",
            exchange=run_exchange,
            routing_key="run.execute",
            durable=True,
            queue_arguments={"x-queue-type": "quorum"},
        ),
        Queue(
            "maintenance",
            exchange=maintenance_exchange,
            routing_key="maintenance.#",
            durable=True,
            queue_arguments={"x-queue-type": "quorum"},
        ),
    ),
    task_routes={
        "control_plane.execute_run": {"queue": "runs", "routing_key": "run.execute"},
        "control_plane.execute_run_task": {
            "queue": "run_tasks",
            "routing_key": "run.task.execute",
        },
        "control_plane.finalize_dynamic_run": {
            "queue": "runs",
            "routing_key": "run.finalize",
        },
        "control_plane.dispatch_outbox": {
            "queue": "maintenance",
            "routing_key": "maintenance.outbox",
        },
        "control_plane.recover_stale_runs": {
            "queue": "maintenance",
            "routing_key": "maintenance.recovery",
        },
        "control_plane.recover_stale_run_tasks": {
            "queue": "maintenance",
            "routing_key": "maintenance.task-recovery",
        },
    },
    beat_schedule={
        "dispatch-control-plane-outbox": {
            "task": "control_plane.dispatch_outbox",
            "schedule": 1.0,
        },
        "recover-stale-runs": {
            "task": "control_plane.recover_stale_runs",
            "schedule": 60.0,
        },
        "recover-stale-run-tasks": {
            "task": "control_plane.recover_stale_run_tasks",
            "schedule": 60.0,
        },
    },
    timezone="UTC",
)
