"""Reservations per business (DB-backed, replaces legacy Sheets)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("business_id", "reservation_id", name="uq_reservation_business_rid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reservation_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    wa_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    personas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fecha: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    hora: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
