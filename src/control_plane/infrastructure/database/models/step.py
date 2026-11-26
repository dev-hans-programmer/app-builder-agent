from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
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

from src.control_plane.infrastructure.database.base import Base

if TYPE_CHECKING:
    from src.control_plane.infrastructure.database.models.run import Run


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_id", "attempt", name="uq_run_step_attempt"),
        Index("ix_run_steps_run_started", "run_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(160))
    parent_step_id: Mapped[str | None] = mapped_column(String(160))
    spec_id: Mapped[str | None] = mapped_column(String(160))
    task_id: Mapped[str | None] = mapped_column(String(160))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="running")
    model: Mapped[str | None] = mapped_column(String(160))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    prompt_hash: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    command: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    retry_reason: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    worker_id: Mapped[str | None] = mapped_column(String(160))
    queue_task_id: Mapped[str | None] = mapped_column(String(160))
    run: Mapped[Run] = relationship(back_populates="steps")
