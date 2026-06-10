"""FCM/APNs device tokens per business (Fase 11.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (
        UniqueConstraint("business_id", "token", name="uq_device_token_business_token"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), default="android", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
