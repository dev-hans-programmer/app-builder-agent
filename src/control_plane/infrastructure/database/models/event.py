from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.control_plane.infrastructure.database.base import Base, utc_now

if TYPE_CHECKING:
    from src.control_plane.infrastructure.database.models.run import Run


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "source_event_id", name="uq_run_source_event"),
        Index("ix_run_events_run_id_id", "run_id", "id"),
        Index("ix_run_events_run_type", "run_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(160))
    source_event_id: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(80))
    level: Mapped[str] = mapped_column(String(16), default="info")
    status: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    run: Mapped[Run] = relationship(back_populates="events")
