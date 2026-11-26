from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.control_plane.infrastructure.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.control_plane.infrastructure.database.models.artifact import Artifact
    from src.control_plane.infrastructure.database.models.event import RunEvent
    from src.control_plane.infrastructure.database.models.project import Project
    from src.control_plane.infrastructure.database.models.step import RunStep


class Run(TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_run_idempotency"),
        Index("ix_runs_project_created", "project_id", "created_at"),
        Index("ix_runs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    retry_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id"))
    request: Mapped[str] = mapped_column(Text)
    target_stack: Mapped[str] = mapped_column(String(16), default="python")
    clarification_gate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(64), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_step_id: Mapped[str | None] = mapped_column(String(160))
    queue_task_id: Mapped[str | None] = mapped_column(String(160))
    worker_id: Mapped[str | None] = mapped_column(String(160))
    policy_version: Mapped[str | None] = mapped_column(String(80))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    delivery_status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )
    delivery_error: Mapped[str | None] = mapped_column(Text)
    repository_owner: Mapped[str | None] = mapped_column(String(160))
    repository_name: Mapped[str | None] = mapped_column(String(160))
    repository_url: Mapped[str | None] = mapped_column(String(1024))
    repository_branch: Mapped[str | None] = mapped_column(String(160))
    repository_commit_sha: Mapped[str | None] = mapped_column(String(64))
    repository_commit_url: Mapped[str | None] = mapped_column(String(1024))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped[Project] = relationship(back_populates="runs")
    steps: Mapped[list[RunStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
