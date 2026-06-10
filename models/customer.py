"""Customers (WhatsApp users) per business."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "wa_id", name="uq_customer_business_wa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    wa_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
