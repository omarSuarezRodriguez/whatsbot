"""Orders per business (API/BD — chatbot sigue usando Sheets hasta Fase 6+)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("business_id", "order_id", name="uq_order_business_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    wa_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    total: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    customer_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
