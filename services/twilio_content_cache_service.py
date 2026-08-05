"""Durable ContentSid lookup/store — reuse Twilio Content Templates by
content hash instead of creating a new one per outbound message."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from models.twilio_content_cache import TwilioContentSid


def get_cached_sid(db: Session, cache_key: str) -> str | None:
    row = db.get(TwilioContentSid, cache_key)
    return row.content_sid if row else None


def upsert_cached_sid(
    db: Session,
    *,
    cache_key: str,
    content_type: str,
    content_sid: str,
) -> None:
    row = db.get(TwilioContentSid, cache_key)
    if row is None:
        db.add(
            TwilioContentSid(
                cache_key=cache_key,
                content_type=content_type,
                content_sid=content_sid,
            )
        )
    else:
        row.content_type = content_type
        row.content_sid = content_sid
    db.flush()


def invalidate_cached_sid(db: Session, cache_key: str) -> None:
    db.execute(delete(TwilioContentSid).where(TwilioContentSid.cache_key == cache_key))
    db.flush()
