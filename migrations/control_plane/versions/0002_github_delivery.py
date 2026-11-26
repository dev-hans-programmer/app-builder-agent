"""Track GitHub repository delivery on runs.

Revision ID: 0002_github_delivery
Revises: 0001_control_plane
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_github_delivery"
down_revision = "0001_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "delivery_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("runs", sa.Column("delivery_error", sa.Text()))
    op.add_column("runs", sa.Column("repository_owner", sa.String(length=160)))
    op.add_column("runs", sa.Column("repository_name", sa.String(length=160)))
    op.add_column("runs", sa.Column("repository_url", sa.String(length=1024)))
    op.add_column("runs", sa.Column("repository_branch", sa.String(length=160)))
    op.add_column("runs", sa.Column("repository_commit_sha", sa.String(length=64)))
    op.add_column("runs", sa.Column("repository_commit_url", sa.String(length=1024)))
    op.add_column("runs", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.create_index("ix_runs_delivery_status", "runs", ["delivery_status"])


def downgrade() -> None:
    op.drop_index("ix_runs_delivery_status", table_name="runs")
    op.drop_column("runs", "published_at")
    op.drop_column("runs", "repository_commit_url")
    op.drop_column("runs", "repository_commit_sha")
    op.drop_column("runs", "repository_branch")
    op.drop_column("runs", "repository_url")
    op.drop_column("runs", "repository_name")
    op.drop_column("runs", "repository_owner")
    op.drop_column("runs", "delivery_error")
    op.drop_column("runs", "delivery_status")
