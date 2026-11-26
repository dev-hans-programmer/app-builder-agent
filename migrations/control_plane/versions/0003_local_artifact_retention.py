"""Track whether artifact bytes remain in local storage.

Revision ID: 0003_local_artifact_retention
Revises: 0002_github_delivery
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_local_artifact_retention"
down_revision = "0002_github_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column(
            "local_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "artifacts",
        sa.Column("local_deleted_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("artifacts", "local_deleted_at")
    op.drop_column("artifacts", "local_available")
