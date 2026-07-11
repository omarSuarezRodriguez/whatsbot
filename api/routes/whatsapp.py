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

    business_id = resolve_business_id_for_webhook(
        db,
        to_number=to_number,
        from_number=from_number,
    )

    # --- Persist incoming message ---
    incoming_wa = wa_id or from_number.replace("whatsapp:", "").strip()
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
    reply_wa_id = result.get("wa_id") or incoming_wa
    is_admin = bool(result.get("is_admin"))
    blocked = bool(result.get("blocked"))
    use_rest = bool(result.get("deliver_via_rest", use_rest_webhook_replies()))

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

    # --- Deliver to Twilio ---
    twiml = build_twiml_response("")
    if response_text and reply_wa_id:
        admin = get_bot_context(start_background=False).admin_service
        recipient = admin._format_whatsapp_address(reply_wa_id) or from_number or reply_wa_id
        twiml = deliver_reply(
            recipient,
            response_text,
            use_rest=use_rest,
            actions=actions,
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
