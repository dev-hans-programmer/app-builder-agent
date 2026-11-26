from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.control_plane.infrastructure.database.base import Base, utc_now

if TYPE_CHECKING:
    from src.control_plane.infrastructure.database.models.run import Run


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_run_created", "run_id", "created_at"),
        Index("ix_artifacts_run_storage", "run_id", "storage_key", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(80), default="file")
    storage_key: Mapped[str] = mapped_column(String(1024))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(160))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    local_available: Mapped[bool] = mapped_column(Boolean, default=True)
    local_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    run: Mapped[Run] = relationship(back_populates="artifacts")
