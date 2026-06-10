"""Menu items per business."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (
        UniqueConstraint("business_id", "external_id", name="uq_menu_business_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    nombre: Mapped[str] = mapped_column(String(128), nullable=False)
    precio: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    categoria: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
