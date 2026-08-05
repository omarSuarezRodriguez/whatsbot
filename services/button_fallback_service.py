"""Durable delivery fallback state for interactive WhatsApp messages."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.pending_button_fallback import PendingButtonFallback


_FINAL_STATUSES = {
    "delivered",
    "read",
    "failed",
    "undelivered",
    "canceled",
}
_FAILED_STATUSES = {"failed", "undelivered", "canceled"}


def register_pending(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
    recipient: str,
    fallback_body: str,
) -> PendingButtonFallback:
    pending = db.get(PendingButtonFallback, message_sid)
    if pending is None:
        pending = PendingButtonFallback(
            message_sid=message_sid,
            business_id=business_id,
            recipient=recipient,
            fallback_body=fallback_body,
        )
        db.add(pending)
    else:
        pending.business_id = business_id
        pending.recipient = recipient
        pending.fallback_body = fallback_body
        pending.consumed_at = None
    db.flush()
    return pending


def consume_status(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
    status: str,
) -> tuple[str, str] | None:
    normalized = (status or "").strip().lower()
    if normalized not in _FINAL_STATUSES:
        return None

    pending = (
        db.query(PendingButtonFallback)
        .filter(
            PendingButtonFallback.message_sid == message_sid,
            PendingButtonFallback.business_id == business_id,
            PendingButtonFallback.consumed_at.is_(None),
        )
        .one_or_none()
    )
    if pending is None:
        return None

    if normalized not in _FAILED_STATUSES:
        db.query(PendingButtonFallback).filter(
            PendingButtonFallback.message_sid == message_sid,
            PendingButtonFallback.business_id == business_id,
            PendingButtonFallback.consumed_at.is_(None),
        ).delete(synchronize_session=False)
        db.flush()
        return None

    now = datetime.now(timezone.utc)
    claimed = (
        db.query(PendingButtonFallback)
        .filter(
            PendingButtonFallback.message_sid == message_sid,
            PendingButtonFallback.business_id == business_id,
            PendingButtonFallback.consumed_at.is_(None),
        )
        .update(
            {PendingButtonFallback.consumed_at: now},
            synchronize_session=False,
        )
    )
    if claimed != 1:
        return None

    db.flush()
    return pending.recipient, pending.fallback_body


def delete_pending(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
) -> None:
    db.query(PendingButtonFallback).filter(
        PendingButtonFallback.message_sid == message_sid,
        PendingButtonFallback.business_id == business_id,
    ).delete(synchronize_session=False)
    db.flush()


def release_claim(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
) -> None:
    db.query(PendingButtonFallback).filter(
        PendingButtonFallback.message_sid == message_sid,
        PendingButtonFallback.business_id == business_id,
    ).update(
        {PendingButtonFallback.consumed_at: None},
        synchronize_session=False,
    )
    db.flush()
