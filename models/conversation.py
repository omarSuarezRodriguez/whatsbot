"""Conversation thread per customer WhatsApp line (MVP Fase 4)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("business_id", "customer_wa_id", name="uq_conversation_business_customer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    customer_wa_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.created_at",
    )
