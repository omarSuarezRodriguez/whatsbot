"""
Twilio WhatsApp webhook.

Flujo:
  1. Twilio POST (form) → validar firma (si TWILIO_VALIDATE_SIGNATURE=true)
  2. conversation_service.save_incoming() → BD
  3. chatbot.gateway.handle_incoming_message() en threadpool (non-blocking)
  4. conversation_service.save_outgoing() → BD
  5. twilio_client.deliver_reply() → TwiML XML o REST

Rutas: POST /webhook (nueva API), POST /bot (alias legacy).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from chatbot.gateway import handle_incoming_message
from chatbot.runtime import get_bot_context
from config.settings import (
    API_PUBLIC_URL,
    REALTIME_ENABLED,
    TWILIO_AUTH_TOKEN,
    TWILIO_VALIDATE_SIGNATURE,
    use_rest_webhook_replies,
)
from infrastructure.database import get_db
from infrastructure.twilio_client import build_twiml_response, deliver_reply
from services.button_fallback_service import (
    consume_status as consume_button_fallback_status,
)
from services.business_service import resolve_business_id_for_webhook
from services.conversation_service import (
    apply_twilio_status,
    save_incoming_message,
    save_outgoing_message,
)
from services.realtime_service import emit_message_saved, emit_message_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


def _form_dict(form: Any) -> dict[str, str]:
    return {k: v for k, v in form.items()}


# Incident 2026-08-05: rapid button taps from one chat fired N webhook requests
# in parallel — each held a DB pool connection through the whole Twilio call,
# and each ran its own delivery flow against Twilio at once. Under enough taps
# this starved the DB pool / Twilio concurrency and the chat went silent with
# no error logged. One lock per (business, wa_id) makes taps from the SAME
# conversation queue and run one at a time; different conversations still run
# fully in parallel.
# ponytail: dict never evicts entries. ceiling: unbounded memory over very
# long uptime with many distinct senders; upgrade path is a bounded LRU/TTL
# if that ever shows up as a real memory issue.
_wa_id_locks: dict[str, asyncio.Lock] = {}


def _get_wa_lock(key: str) -> asyncio.Lock:
    lock = _wa_id_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _wa_id_locks[key] = lock
    return lock


async def _validate_twilio_signature(request: Request) -> None:
    """403 if Twilio signature is missing or invalid (gated by TWILIO_VALIDATE_SIGNATURE)."""
    if not TWILIO_VALIDATE_SIGNATURE:
        return
    if not TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO_VALIDATE_SIGNATURE=true but TWILIO_AUTH_TOKEN empty — skipping")
        return
    try:
        from twilio.request_validator import RequestValidator

        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        # Prefer the public URL base to handle reverse-proxy header differences
        if API_PUBLIC_URL and not url.startswith(API_PUBLIC_URL):
            path = request.url.path
            if request.url.query:
                path += f"?{request.url.query}"
            url = f"{API_PUBLIC_URL.rstrip('/')}{path}"
        form = _form_dict(await request.form())
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(url, form, signature):
            raise HTTPException(403, detail="Twilio signature inválida")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Twilio signature validation error — rejecting request")
        raise HTTPException(403, detail="Error al validar firma Twilio")


@router.post("/webhook")
@router.post("/bot")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """
    Webhook Twilio Messaging.

    Entrada: application/x-www-form-urlencoded (WaId, From, Body, ...).
    Salida: text/xml TwiML (o vacío si respuesta vía REST).
    """
    await _validate_twilio_signature(request)

    started = time.perf_counter()
    form = _form_dict(await request.form())
    wa_id = form.get("WaId") or ""
    from_number = form.get("From", "")
    body = form.get("Body", "")
    profile_name = form.get("ProfileName", "")
    message_sid = form.get("MessageSid") or form.get("SmsMessageSid")
    to_number = form.get("To", "")
    logger.info(
        "Webhook inbound To=%s From=%s wa_id=%s",
        to_number,
        from_number,
        wa_id,
    )

    business_id = resolve_business_id_for_webhook(
        db,
        to_number=to_number,
        from_number=from_number,
    )
    incoming_wa = wa_id or from_number.replace("whatsapp:", "").strip()
    lock_key = f"{business_id}:{incoming_wa}" if incoming_wa else f"__anon:{id(form)}"

    # Serialize processing per-conversation — see _get_wa_lock docstring.
    async with _get_wa_lock(lock_key):
        return await _process_whatsapp_message(
            db=db,
            started=started,
            wa_id=wa_id,
            from_number=from_number,
            body=body,
            profile_name=profile_name,
            message_sid=message_sid,
            to_number=to_number,
            business_id=business_id,
            incoming_wa=incoming_wa,
            form=form,
        )


async def _process_whatsapp_message(
    *,
    db: Session,
    started: float,
    wa_id: str,
    from_number: str,
    body: str,
    profile_name: str,
    message_sid: str | None,
    to_number: str,
    business_id: str,
    incoming_wa: str,
    form: dict[str, str],
) -> Response:
    # --- Persist incoming message ---
    saved_incoming = None
    if incoming_wa:
        try:
            ctx = get_bot_context(start_background=False)
            canonical = ctx.admin_service.canonical_wa_id(wa_id, from_number) or incoming_wa
            is_admin_preview = any(
                ctx.admin_service.is_admin(sender)
                for sender in [canonical, wa_id, from_number]
                if sender
            )
            saved_incoming = save_incoming_message(
                db,
                customer_wa_id=canonical,
                body=body,
                business_id=business_id,
                customer_name=profile_name or None,
                is_admin=is_admin_preview,
                twilio_sid=message_sid,
            )
            db.commit()
            if REALTIME_ENABLED and saved_incoming is not None:
                await emit_message_saved(db, business_id, saved_incoming)
        except Exception:
            db.rollback()
            logger.exception("Failed to save incoming message to DB")

    # --- Run gateway in threadpool (non-blocking — P4) ---
    result = await run_in_threadpool(
        handle_incoming_message,
        {
            "phone": wa_id,
            "from_number": from_number,
            "message": body,
            "profile_name": profile_name,
            "business_id": business_id,
            "channel": "whatsapp",
            "metadata": form,
        },
    )

    response_text = result.get("response_text", "")
    actions = result.get("actions", [])
    buttons_failure_message = result.get("buttons_failure_message", "")
    interactive_list = result.get("list")
    reply_wa_id = result.get("wa_id") or incoming_wa
    is_admin = bool(result.get("is_admin"))
    blocked = bool(result.get("blocked"))
    use_rest = bool(result.get("deliver_via_rest", use_rest_webhook_replies()))
    # Force REST so outbound always uses TWILIO_ACCOUNT_SID + TWILIO_WHATSAPP_FROM
    # (never silent TwiML reply that Twilio stamps outside our From pin).
    use_rest = True

    # --- Persist bot reply ---
    if reply_wa_id and response_text and not blocked:
        try:
            saved_outgoing = save_outgoing_message(
                db,
                customer_wa_id=reply_wa_id,
                body=response_text,
                business_id=business_id,
                is_admin=False,
            )
            db.commit()
            if REALTIME_ENABLED and saved_outgoing:
                for msg in saved_outgoing:
                    await emit_message_saved(db, business_id, msg)
        except Exception:
            db.rollback()
            logger.exception("Failed to save outgoing message to DB")

    # Release the pooled DB connection before the Twilio network call below —
    # nothing past this point touches `db`. Otherwise the connection sits
    # checked out of the pool for the whole Twilio round-trip, and enough
    # concurrent taps exhaust the pool. get_db()'s finally still calls
    # close() again on request teardown; Session.close() is a no-op if
    # already closed.
    db.close()

    # --- Deliver to Twilio ---
    twiml = build_twiml_response("")
    if response_text and reply_wa_id:
        admin = get_bot_context(start_background=False).admin_service
        recipient = admin._format_whatsapp_address(reply_wa_id) or from_number or reply_wa_id
        twiml = deliver_reply(
            recipient,
            response_text,
            use_rest=use_rest,
            business_id=business_id,
            actions=actions,
            buttons_failure_message=buttons_failure_message,
            interactive_list=interactive_list,
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Webhook %.1f ms wa_id=%s admin=%s blocked=%s",
        elapsed_ms, reply_wa_id, is_admin, blocked,
    )

    return Response(content=twiml, media_type="text/xml; charset=utf-8")


@router.post("/webhook/status")
async def twilio_status_callback(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Twilio status callback (sent, delivered, read, failed)."""
    form = _form_dict(await request.form())
    message_sid = form.get("MessageSid") or form.get("SmsMessageSid") or ""
    twilio_status = form.get("MessageStatus") or form.get("SmsStatus") or ""
    to_number = form.get("To", "")
    from_number = form.get("From", "")

    if not message_sid or not twilio_status:
        return Response(status_code=204)

    business_id = resolve_business_id_for_webhook(
        db,
        to_number=to_number,
        from_number=from_number,
    )

    try:
        # Schedules the first retry on failure (services/button_fallback_service
        # .start_retry_scheduler owns actual delivery from here on — never
        # blocks this webhook response waiting on a Twilio round-trip).
        consume_button_fallback_status(
            db,
            business_id=business_id,
            message_sid=message_sid,
            status=twilio_status,
        )
        db.commit()

        msg = apply_twilio_status(
            db,
            business_id=business_id,
            message_sid=message_sid,
            twilio_status=twilio_status,
        )
        if msg is None:
            return Response(status_code=204)
        db.commit()
        if REALTIME_ENABLED:
            await emit_message_status(db, business_id, msg)
    except Exception:
        db.rollback()
        logger.exception("Error applying Twilio status callback")

    return Response(status_code=204)
