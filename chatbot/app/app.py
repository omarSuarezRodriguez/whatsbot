"""Flask application and Twilio WhatsApp webhook."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Union

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import (  # noqa: E402
    ADMIN_WHATSAPP_NUMBER,
    BLOCKED_USERS_CACHE_TTL_SECONDS,
    GOOGLE_SHEETS_CREDENTIALS_PATH,
    GOOGLE_SPREADSHEET_ID,
    MENU_CACHE_TTL_SECONDS,
    ORDERS_CACHE_TTL_SECONDS,
    RESTAURANT_NAME,
    SHEETS_FULL_REFRESH_INTERVAL_SECONDS,
    SHEETS_INCREMENTAL_BATCH_SIZE,
    SHEETS_INCREMENTAL_THRESHOLD,
    STATE_PERSIST_PATH,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    is_twilio_whatsapp_sandbox,
)
from app.core.flow_engine import FlowEngine  # noqa: E402
from app.core.state_manager import StateManager  # noqa: E402
from app.utils.client_message_log import schedule_client_message_log  # noqa: E402
from app.integrations.google_sheets import get_google_sheets_client  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402
from app.services.blocked_users_cache import BlockedUsersCache  # noqa: E402
from app.services.menu_service import MenuService  # noqa: E402
from app.services.order_service import OrderService  # noqa: E402
from app.services.reservation_service import ReservationService  # noqa: E402
from app.services.user_service import UserService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

Reply = Union[str, List[str]]

LATENCY_STATS_EVERY = 100
_latency_by_body: Dict[str, List[float]] = defaultdict(list)
_latency_lock = threading.Lock()
_latency_request_count = 0

_app_instance: Flask | None = None


def _body_latency_key(body: str) -> str:
    normalized = (body or "").strip().lower()
    return normalized[:40] if normalized else "(empty)"


def _latency_percentile(samples: List[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(len(ordered) * pct / 100))
    return ordered[index]


def _record_bot_latency(body: str, elapsed_ms: float) -> None:
    global _latency_request_count
    key = _body_latency_key(body)
    with _latency_lock:
        bucket = _latency_by_body[key]
        bucket.append(elapsed_ms)
        if len(bucket) > 500:
            bucket.pop(0)
        _latency_request_count += 1
        should_log = _latency_request_count % LATENCY_STATS_EVERY == 0

    if should_log:
        _log_bot_latency_stats()


def _log_bot_latency_stats() -> None:
    with _latency_lock:
        snapshot = {
            key: list(samples)
            for key, samples in _latency_by_body.items()
            if samples
        }

    parts: List[str] = []
    for key in sorted(snapshot):
        samples = snapshot[key]
        if len(samples) < 2:
            continue
        parts.append(
            f"{key}: p50={_latency_percentile(samples, 50):.0f}ms "
            f"p95={_latency_percentile(samples, 95):.0f}ms n={len(samples)}"
        )
    if parts:
        logger.info("POST /bot latency stats | %s", " | ".join(parts))


def _log_bot_completion(
    elapsed_ms: float,
    wa_id: str,
    is_admin: bool,
    body: str,
) -> None:
    logger.info(
        "POST /bot completed in %.1f ms wa_id=%s admin=%s body=%r",
        elapsed_ms,
        wa_id,
        is_admin,
        body[:80],
    )
    _record_bot_latency(body, elapsed_ms)


def create_app() -> Flask:
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    flask_app = Flask(__name__)

    sheets_client = get_google_sheets_client(
        GOOGLE_SHEETS_CREDENTIALS_PATH,
        GOOGLE_SPREADSHEET_ID,
    )
    state_manager = StateManager(persist_path=STATE_PERSIST_PATH)
    menu_service = MenuService(sheets_client)
    order_service = OrderService(sheets_client, menu_service)
    reservation_service = ReservationService(sheets_client)
    user_service = UserService(sheets_client)
    admin_service = AdminService(sheets_client, order_service)
    blocked_cache = BlockedUsersCache(sheets_client, admin_service)
    admin_service.blocked_cache = blocked_cache
    blocked_cache.start()
    flow_engine = FlowEngine(
        state_manager=state_manager,
        menu_service=menu_service,
        order_service=order_service,
        reservation_service=reservation_service,
        user_service=user_service,
        admin_service=admin_service,
    )

    try:
        menu_service.get_available_menu()
        menu_service.menu_literal_tokens()
        menu_service.format_menu()
    except Exception:
        logger.debug("Menu intent cache warm-up skipped", exc_info=True)

    admin_service.start_reminder_scheduler()

    flask_app.config["flow_engine"] = flow_engine
    flask_app.config["user_service"] = user_service
    flask_app.config["admin_service"] = admin_service
    flask_app.config["blocked_cache"] = blocked_cache

    @flask_app.get("/health")
    def health():
        twilio_ready = bool(
            TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and ADMIN_WHATSAPP_NUMBER
        )
        return {
            "status": "ok",
            "service": "restaurant-chatbot",
            "restaurant": RESTAURANT_NAME,
            "admin_configured": bool(ADMIN_WHATSAPP_NUMBER),
            "twilio_configured": twilio_ready,
            "whatsapp_sandbox_mode": is_twilio_whatsapp_sandbox(),
            "caches": sheets_client.cache_status(),
            "cache_ttl_seconds": {
                "menu_and_users": MENU_CACHE_TTL_SECONDS,
                "orders_and_reservations": ORDERS_CACHE_TTL_SECONDS,
                "blocked_users": BLOCKED_USERS_CACHE_TTL_SECONDS,
                "sheets_full_refresh": SHEETS_FULL_REFRESH_INTERVAL_SECONDS,
                "sheets_incremental_threshold": SHEETS_INCREMENTAL_THRESHOLD,
                "sheets_incremental_batch_size": SHEETS_INCREMENTAL_BATCH_SIZE,
            },
        }

    @flask_app.post("/bot")
    def bot_webhook():
        started = time.perf_counter()
        response = MessagingResponse()
        wa_id = request.form.get("WaId") or ""
        from_number = request.form.get("From", "")
        profile_name = request.form.get("ProfileName", "")
        body = request.form.get("Body", "")

        if not wa_id and from_number:
            wa_id = from_number.replace("whatsapp:", "").strip()

        if wa_id:
            canonical = admin_service.canonical_wa_id(wa_id, from_number)
            if canonical and canonical != wa_id:
                logger.info(
                    "wa_id normalizado %s -> %s (From=%r)",
                    wa_id,
                    canonical,
                    from_number[:40] if from_number else "",
                )
            wa_id = canonical or wa_id

        if not wa_id:
            response.message(
                "No pude identificar tu número. Intenta escribirnos de nuevo."
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            _log_bot_completion(elapsed_ms, "missing", False, body)
            return str(response), 200, {"Content-Type": "application/xml"}

        is_admin = False
        try:
            sender_ids = [wa_id]
            if from_number and from_number != wa_id:
                sender_ids.append(from_number)
            if any(admin_service.is_admin(sender) for sender in sender_ids):
                is_admin = True
                reply = admin_service.handle_admin_message(body)
            elif blocked_cache.is_blocked(wa_id):
                schedule_client_message_log(
                    wa_id=wa_id,
                    client_message=(body or "").strip(),
                    bot_message="(usuario bloqueado — sin respuesta)",
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "Blocked user ignored wa_id=%s body=%r",
                    wa_id,
                    body[:80],
                )
                _log_bot_completion(elapsed_ms, wa_id, False, body)
                return str(response), 200, {"Content-Type": "text/xml; charset=utf-8"}
            else:
                user_service.touch(wa_id=wa_id, name=profile_name)
                reply = flow_engine.process_message(wa_id=wa_id, body=body)
        except Exception:
            logger.exception("Error processing message for wa_id=%s", wa_id)
            reply = (
                "Disculpa, tuve un inconveniente momentáneo. "
                "Por favor intenta de nuevo en unos segundos.\n\n"
                "Escribe *inicio* para reiniciar."
            )

        if not reply or (isinstance(reply, str) and not reply.strip()):
            reply = (
                "Estoy aquí para ayudarte. Escribe *menu*, *pedido* o *reservar*."
            )

        if not is_admin and wa_id:
            schedule_client_message_log(
                wa_id=wa_id,
                client_message=(body or "").strip(),
                bot_message=reply,
            )

        recipient = admin_service._format_whatsapp_address(wa_id) or from_number or wa_id
        _deliver_bot_reply(
            admin_service,
            recipient,
            reply,
            response,
            use_rest=_use_rest_webhook_replies(),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        _log_bot_completion(elapsed_ms, wa_id, is_admin, body)
        return str(response), 200, {"Content-Type": "text/xml; charset=utf-8"}

    @flask_app.post("/bot/reload-flow")
    def reload_flow():
        flow_engine.reload_flow()
        return {"status": "flow reloaded"}

    _app_instance = flask_app
    return flask_app


def _use_rest_webhook_replies() -> bool:
    explicit = os.getenv("TWILIO_REST_WEBHOOK_REPLIES", "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return not is_twilio_whatsapp_sandbox()


def _attach_replies(response: MessagingResponse, reply: Reply) -> None:
    if isinstance(reply, list):
        for part in reply:
            if part and str(part).strip():
                response.message(str(part).strip())
    elif reply and str(reply).strip():
        response.message(str(reply).strip())


def _reply_parts(reply: Reply) -> List[str]:
    if isinstance(reply, list):
        return [str(part).strip() for part in reply if part and str(part).strip()]
    if reply and str(reply).strip():
        return [str(reply).strip()]
    return []


def _deliver_bot_reply(
    admin_service: AdminService,
    recipient: str,
    reply: Reply,
    twiml_response: MessagingResponse,
    *,
    use_rest: bool,
) -> None:
    parts = _reply_parts(reply)
    if not parts:
        return

    if not use_rest:
        _attach_replies(twiml_response, reply)
        return

    delivered = False
    for part in parts:
        if admin_service._send_whatsapp(recipient, part):
            delivered = True

    if delivered:
        logger.info(
            "Webhook reply sent via Twilio REST to %s (%d part(s))",
            recipient,
            len(parts),
        )
        return

    if admin_service.last_twilio_error_code == 63038:
        logger.error(
            "REST WhatsApp bloqueado (63038 límite diario) para %s; "
            "no se reintenta TwiML (también fallaría). Espere ventana 24 h o "
            "solicite más cupo en Twilio Console.",
            recipient,
        )
        return

    logger.warning(
        "REST WhatsApp delivery failed for %s; falling back to TwiML",
        recipient,
    )
    _attach_replies(twiml_response, reply)


app = create_app()


if __name__ == "__main__":
    from waitress import serve

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    serve(app, host=host, port=port)
