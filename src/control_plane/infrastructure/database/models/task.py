from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.control_plane.infrastructure.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.control_plane.infrastructure.database.models.run import Run


class RunTask(TimestampMixin, Base):
    """Mutable scheduling projection for one generated-code task."""

    __tablename__ = "run_tasks"
    __table_args__ = (
        UniqueConstraint("run_id", "task_key", name="uq_run_tasks_key"),
        Index("ix_run_tasks_run_status", "run_id", "status"),
        Index("ix_run_tasks_ready", "status", "priority", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    task_key: Mapped[str] = mapped_column(String(160))
    plan_task_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    acceptance_criteria_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    contract_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_rule_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    verification: Mapped[list[str]] = mapped_column(JSON, default=list)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    queue_task_id: Mapped[str | None] = mapped_column(String(160))
    worker_id: Mapped[str | None] = mapped_column(String(160))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_context_hash: Mapped[str | None] = mapped_column(String(64))
    output_patch_hash: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)

    run: Mapped[Run] = relationship(back_populates="tasks")
    attempts: Mapped[list[RunTaskAttempt]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    dependencies: Mapped[list[RunTaskDependency]] = relationship(
        foreign_keys="RunTaskDependency.task_id",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    dependents: Mapped[list[RunTaskDependency]] = relationship(
        foreign_keys="RunTaskDependency.depends_on_task_id",
        back_populates="depends_on_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def depends_on_task_ids(self) -> list[UUID]:
        return [dependency.depends_on_task_id for dependency in self.dependencies]


class RunTaskDependency(Base):
    """Directed task dependency edge within a run."""

    __tablename__ = "run_task_dependencies"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_tasks.id", ondelete="CASCADE"), primary_key=True
    )

    task: Mapped[RunTask] = relationship(
        foreign_keys=[task_id], back_populates="dependencies"
    )
    depends_on_task: Mapped[RunTask] = relationship(
        foreign_keys=[depends_on_task_id], back_populates="dependents"
    )


class RunTaskAttempt(Base):
    """Append-only execution evidence for a task attempt."""

    __tablename__ = "run_task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt", name="uq_run_task_attempt"),
        Index("ix_run_task_attempts_task_started", "task_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_tasks.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    queue_task_id: Mapped[str | None] = mapped_column(String(160))
    worker_id: Mapped[str | None] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(160))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    prompt_hash: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)

    task: Mapped[RunTask] = relationship(back_populates="attempts")
