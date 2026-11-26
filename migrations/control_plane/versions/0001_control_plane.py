"""Create durable control-plane tables.

Revision ID: 0001_control_plane
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_control_plane"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_projects_slug"),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("retry_of_id", sa.Uuid()),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("target_stack", sa.String(16), nullable=False),
        sa.Column("clarification_gate_enabled", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(160)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("current_step_id", sa.String(160)),
        sa.Column("queue_task_id", sa.String(160)),
        sa.Column("worker_id", sa.String(160)),
        sa.Column("policy_version", sa.String(80)),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("error_type", sa.String(160)),
        sa.Column("error_message", sa.Text()),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retry_of_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_run_idempotency"),
    )
    op.create_index("ix_runs_project_id", "runs", ["project_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_project_created", "runs", ["project_id", "created_at"])
    op.create_index("ix_runs_status_created", "runs", ["status", "created_at"])

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(160), nullable=False),
        sa.Column("parent_step_id", sa.String(160)),
        sa.Column("spec_id", sa.String(160)),
        sa.Column("task_id", sa.String(160)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model", sa.String(160)),
        sa.Column("prompt_version", sa.String(80)),
        sa.Column("prompt_hash", sa.String(128)),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("command", sa.Text()),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("retry_reason", sa.Text()),
        sa.Column("error_type", sa.String(160)),
        sa.Column("error_message", sa.Text()),
        sa.Column("stack_trace", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("worker_id", sa.String(160)),
        sa.Column("queue_task_id", sa.String(160)),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "step_id", "attempt", name="uq_run_step_attempt"),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_run_steps_run_started", "run_steps", ["run_id", "started_at"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(160)),
        sa.Column("source_event_id", sa.String(80)),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32)),
        sa.Column("message", sa.Text()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "source_event_id", name="uq_run_source_event"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_run_id_id", "run_events", ["run_id", "id"])
    op.create_index("ix_run_events_run_type", "run_events", ["run_id", "event_type"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(160)),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(160)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_run_created", "artifacts", ["run_id", "created_at"])
    op.create_index(
        "ix_artifacts_run_storage", "artifacts", ["run_id", "storage_key"], unique=True
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"]
    )
    op.create_index(
        "ix_outbox_pending", "outbox_messages", ["published_at", "available_at"]
    )


def downgrade() -> None:
    op.drop_table("outbox_messages")
    op.drop_table("artifacts")
    op.drop_table("run_events")
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("projects")
