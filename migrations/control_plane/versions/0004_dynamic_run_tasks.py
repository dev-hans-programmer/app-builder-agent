"""Add dynamic task scheduling tables.

Revision ID: 0004_dynamic_run_tasks
Revises: 0003_local_artifact_retention
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_dynamic_run_tasks"
down_revision = "0003_local_artifact_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "execution_mode",
            sa.String(length=32),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.create_table(
        "run_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_key", sa.String(length=160), nullable=False),
        sa.Column("plan_task_id", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("acceptance_criteria_ids", sa.JSON(), nullable=False),
        sa.Column("contract_ids", sa.JSON(), nullable=False),
        sa.Column("policy_rule_ids", sa.JSON(), nullable=False),
        sa.Column("allowed_paths", sa.JSON(), nullable=False),
        sa.Column("verification", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("queue_task_id", sa.String(length=160)),
        sa.Column("worker_id", sa.String(length=160)),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("input_context_hash", sa.String(length=64)),
        sa.Column("output_patch_hash", sa.String(length=64)),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error_type", sa.String(length=160)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "task_key", name="uq_run_tasks_key"),
    )
    op.create_index("ix_run_tasks_run_id", "run_tasks", ["run_id"])
    op.create_index("ix_run_tasks_status", "run_tasks", ["status"])
    op.create_index("ix_run_tasks_run_status", "run_tasks", ["run_id", "status"])
    op.create_index(
        "ix_run_tasks_ready", "run_tasks", ["status", "priority", "sequence"]
    )

    op.create_table(
        "run_task_dependencies",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_task_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["run_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"], ["run_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", "depends_on_task_id"),
    )

    op.create_table(
        "run_task_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("queue_task_id", sa.String(length=160)),
        sa.Column("worker_id", sa.String(length=160)),
        sa.Column("model", sa.String(length=160)),
        sa.Column("prompt_version", sa.String(length=80)),
        sa.Column("prompt_hash", sa.String(length=128)),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error_type", sa.String(length=160)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(["task_id"], ["run_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt", name="uq_run_task_attempt"),
    )
    op.create_index("ix_run_task_attempts_task_id", "run_task_attempts", ["task_id"])
    op.create_index(
        "ix_run_task_attempts_task_started",
        "run_task_attempts",
        ["task_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("run_task_attempts")
    op.drop_table("run_task_dependencies")
    op.drop_table("run_tasks")
    op.drop_column("runs", "execution_mode")
