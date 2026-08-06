"""Durable delivery fallback + retry for interactive WhatsApp messages.

Flow: interactive send (buttons/list) fails async (Twilio status callback) →
first retry scheduled → retry loop (start_retry_scheduler) sends the fallback
text via infrastructure.twilio_client.send_whatsapp_message → on failure,
second retry scheduled → on second failure, gives up (row dropped).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from config.settings import (
    TWILIO_FIRST_RETRY_SECONDS_PER_TRY,
    TWILIO_SECOND_RETRY_SECONDS_PER_TRY,
)
from models.pending_button_fallback import PendingButtonFallback

logger = logging.getLogger(__name__)

_FINAL_STATUSES = {
    "delivered",
    "read",
    "failed",
    "undelivered",
    "canceled",
}
_FAILED_STATUSES = {"failed", "undelivered", "canceled"}

# Exactly 2 attempts total, user-configured delay per try (not auto-backoff —
# see config/settings.py comment). ponytail: a short 2-try schedule only
# helps transient/channel-throughput failures (e.g. 63018); it will NOT
# clear an active Meta pair/spam-signal penalty (60s-30min) — that ceiling
# has no code fix, only prevention (pacing) + waiting it out.
_MAX_ATTEMPTS = 2


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
        pending.attempts = 0
        pending.next_retry_at = None
    db.flush()
    return pending


def consume_status(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
    status: str,
) -> None:
    """On a final Twilio status: success drops the pending fallback (never
    needed); failure schedules the first retry (the retry loop below owns
    delivery from here on)."""
    normalized = (status or "").strip().lower()
    if normalized not in _FINAL_STATUSES:
        return

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
        return

    if normalized not in _FAILED_STATUSES:
        db.delete(pending)
        db.flush()
        return

    if pending.next_retry_at is not None:
        return  # already scheduled by an earlier callback for this sid

    pending.next_retry_at = datetime.now(timezone.utc) + timedelta(
        seconds=TWILIO_FIRST_RETRY_SECONDS_PER_TRY
    )
    db.flush()


def due_for_retry(db: Session) -> list[PendingButtonFallback]:
    now = datetime.now(timezone.utc)
    return (
        db.query(PendingButtonFallback)
        .filter(
            PendingButtonFallback.consumed_at.is_(None),
            PendingButtonFallback.next_retry_at.isnot(None),
            PendingButtonFallback.next_retry_at <= now,
        )
        .all()
    )


def record_attempt_result(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
    success: bool,
) -> None:
    pending = db.get(PendingButtonFallback, message_sid)
    if pending is None or pending.business_id != business_id:
        return

    if success:
        db.delete(pending)
        db.flush()
        return

    pending.attempts += 1
    if pending.attempts >= _MAX_ATTEMPTS:
        logger.warning(
            "Button fallback gave up after %d attempts sid=%s recipient=%s",
            pending.attempts, message_sid, pending.recipient,
        )
        db.delete(pending)
    else:
        pending.next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=TWILIO_SECOND_RETRY_SECONDS_PER_TRY
        )
    db.flush()


# ---------------------------------------------------------------------------
# Retry scheduler — same low-tech daemon-thread pattern as
# chatbot/app/services/admin_service.py's reminder loop (proven to work fine
# for this single-process deploy, no new infra needed).
# ---------------------------------------------------------------------------

_RETRY_POLL_SECONDS = 5
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _process_due_retries() -> None:
    from infrastructure.database import session_scope
    from infrastructure.twilio_client import send_whatsapp_message

    with session_scope() as db:
        due = due_for_retry(db)
        items = [(p.message_sid, p.business_id, p.recipient, p.fallback_body) for p in due]

    for message_sid, business_id, recipient, fallback_body in items:
        sid = send_whatsapp_message(recipient, fallback_body)
        with session_scope() as db:
            record_attempt_result(
                db,
                business_id=business_id,
                message_sid=message_sid,
                success=bool(sid),
            )


def _retry_loop() -> None:
    while True:
        try:
            _process_due_retries()
        except Exception:
            logger.exception("Button fallback retry loop error (non-fatal)")
        time.sleep(_RETRY_POLL_SECONDS)


def start_retry_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    thread = threading.Thread(target=_retry_loop, daemon=True, name="button-fallback-retry")
    thread.start()
    logger.info("Button fallback retry scheduler started.")
