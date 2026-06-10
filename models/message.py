"""Individual WhatsApp messages (incoming/outgoing) for Flutter history."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # incoming | outgoing
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)
    twilio_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="delivered", nullable=False
    )  # sending | sent | delivered | read
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )
