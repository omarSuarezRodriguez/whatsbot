"""Durable fallback payloads for failed interactive WhatsApp messages."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PendingButtonFallback(Base):
    __tablename__ = "pending_button_fallbacks"

    message_sid: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recipient: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        index=True,
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Retry scheduling (services/button_fallback_service.py). attempts counts
    # completed tries (0, 1, 2 — capped at 2 by config); next_retry_at is when
    # the background loop should try again. NULL next_retry_at = not scheduled
    # (either never failed yet, or retries exhausted and row is about to be dropped).
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
