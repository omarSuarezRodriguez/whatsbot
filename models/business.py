"""Business (tenant) — maps TWILIO_WHATSAPP_FROM to business_id."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    twilio_whatsapp_from: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    admin_whatsapp_number: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    google_spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sheets_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    intents_config: Mapped["BusinessIntentConfig | None"] = relationship(
        "BusinessIntentConfig",
        back_populates="business",
        uselist=False,
        cascade="all, delete-orphan",
    )
    prompts_config: Mapped["BusinessPromptConfig | None"] = relationship(
        "BusinessPromptConfig",
        back_populates="business",
        uselist=False,
        cascade="all, delete-orphan",
    )


class BusinessIntentConfig(Base):
    __tablename__ = "business_intents"

    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    business: Mapped["Business"] = relationship("Business", back_populates="intents_config")


class BusinessPromptConfig(Base):
    __tablename__ = "business_prompts"

    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    business: Mapped["Business"] = relationship("Business", back_populates="prompts_config")
