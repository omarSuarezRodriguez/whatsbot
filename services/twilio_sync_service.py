"""
Recuperación de mensajes desde Twilio API cuando faltan webhooks.

Entrada: business_id, ventana temporal opcional.
Salida: mensajes nuevos persistidos en BD local (dedup por MessageSid).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from chatbot.runtime import get_bot_context
from config.settings import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
from services import conversation_service as conv_svc
from services.business_service import get_business

logger = logging.getLogger(__name__)


def _parse_twilio_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_wa_digits(value: str) -> str:
    ctx = get_bot_context(start_background=False)
    canonical = ctx.admin_service.canonical_wa_id(value, value) or value
    return "".join(ch for ch in canonical if ch.isdigit())


def sync_messages_from_twilio(
    db: Session,
    business_id: str,
    *,
    lookback_hours: int = 48,
    limit: int = 200,
) -> dict[str, int]:
    """
    Backfill missing messages using Twilio Messages.list().

    Returns counters: {imported, skipped, errors}.
    """
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        return {"imported": 0, "skipped": 0, "errors": 0, "reason": "twilio_not_configured"}

    biz = get_business(db, business_id)
    if biz is None:
        return {"imported": 0, "skipped": 0, "errors": 0, "reason": "business_not_found"}

    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, lookback_hours))
    from_number = TWILIO_WHATSAPP_FROM
    if not from_number.startswith("whatsapp:"):
        from_digits = "".join(ch for ch in from_number if ch.isdigit())
        from_number = f"whatsapp:+{from_digits}"

    imported = 0
    skipped = 0
    errors = 0

    try:
        records = client.messages.list(
            date_sent_after=since,
            limit=limit,
        )
    except Exception:
        logger.exception("Twilio messages.list failed business=%s", business_id)
        return {"imported": 0, "skipped": 0, "errors": 1}

    for record in records:
        sid = getattr(record, "sid", None)
        if not sid:
            skipped += 1
            continue

        if conv_svc.get_message_by_twilio_sid(db, business_id, sid) is not None:
            skipped += 1
            continue

        record_from = getattr(record, "from_", "") or ""
        record_to = getattr(record, "to", "") or ""
        body = getattr(record, "body", "") or ""
        if not body.strip():
            skipped += 1
            continue

        is_inbound = record_to == from_number
        is_outbound = record_from == from_number
        if not is_inbound and not is_outbound:
            skipped += 1
            continue

        try:
            if is_inbound:
                customer = _normalize_wa_digits(record_from)
                if not customer:
                    skipped += 1
                    continue
                msg = conv_svc.save_incoming_message(
                    db,
                    customer_wa_id=customer,
                    body=body,
                    business_id=business_id,
                    twilio_sid=sid,
                )
                msg.created_at = _parse_twilio_timestamp(
                    getattr(record, "date_created", None)
                )
            else:
                customer = _normalize_wa_digits(record_to)
                if not customer:
                    skipped += 1
                    continue
                saved = conv_svc.save_outgoing_message(
                    db,
                    customer_wa_id=customer,
                    body=body,
                    business_id=business_id,
                    is_admin=False,
                    twilio_sid=sid,
                )
                if not saved:
                    skipped += 1
                    continue
                msg = saved[-1]
                msg.created_at = _parse_twilio_timestamp(
                    getattr(record, "date_created", None)
                )

            twilio_status = getattr(record, "status", "") or ""
            conv_svc.apply_twilio_status(
                db,
                business_id=business_id,
                message_sid=sid,
                twilio_status=twilio_status,
            )
            imported += 1
        except Exception:
            errors += 1
            logger.exception("Failed to import Twilio message sid=%s", sid)

    if imported:
        db.commit()
        logger.info(
            "Twilio resync business=%s imported=%d skipped=%d errors=%d",
            business_id,
            imported,
            skipped,
            errors,
        )

    return {"imported": imported, "skipped": skipped, "errors": errors}
