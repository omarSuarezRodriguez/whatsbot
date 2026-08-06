"""
Notificaciones admin + confirmación/rechazo de pedidos (100% BD).

Flujo:
  Cliente pide → bot guarda pedido → ADMIN_WHATSAPP_NUMBER recibe alerta
  → dueño confirma (WhatsApp o app) → cliente recibe aviso.
"""

from __future__ import annotations

import logging
from typing import Any

from chatbot.runtime import get_bot_context
from config.settings import DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)


def _admin_service():
    return get_bot_context(start_background=False).admin_service


def is_admin_sender(wa_id: str) -> bool:
    from app.services.admin_service import AdminService

    return AdminService.is_admin(wa_id)


def notify_admin_new_order(order: dict[str, Any]) -> None:
    _admin_service().notify_new_order(order)


def handle_admin_confirmation(
    body: str,
    *,
    business_id: str | None = None,
) -> str:
    from app.utils.validators import extract_admin_order_id, is_admin_confirm

    reply = _admin_service().handle_admin_message(body)
    if is_admin_confirm(body):
        order_id = extract_admin_order_id(body)
        if order_id and "confirmado" in reply.lower():
            _update_order_status_db(order_id, business_id=business_id, status="confirmed")
    return reply


def on_order_pending(
    order_payload: dict[str, Any],
    *,
    business_id: str | None = None,
) -> None:
    """Tras guardar pedido pendiente: alerta admin + persiste en BD."""
    notify_admin_new_order(order_payload)
    _persist_order_to_db(order_payload, business_id=business_id)


def _persist_order_to_db(
    order_payload: dict[str, Any],
    *,
    business_id: str | None = None,
) -> None:
    """Persiste pedido nuevo en tabla orders (fuente de verdad)."""
    order_id = str(order_payload.get("order_id", "")).strip()
    if not order_id:
        return
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()
    try:
        from infrastructure.database import session_scope
        from services import order_service as db_orders

        with session_scope() as db:
            if db_orders.get_order(db, bid, order_id):
                return
            items = order_payload.get("items") or []
            row = db_orders.create_order(
                db,
                bid,
                order_id=order_id,
                wa_id=str(order_payload.get("wa_id", "")),
                items=items if isinstance(items, list) else [],
                total=float(order_payload.get("total") or 0),
                status=str(order_payload.get("status", "pending")),
                customer_name=str(order_payload.get("customer_name", "")),
                address=str(order_payload.get("address", "")),
                delivery_type=str(order_payload.get("delivery_type", "")),
            )
            logger.debug("Order %s persisted to DB for business %s", order_id, bid)
            try:
                from services.realtime_service import schedule_order_pending
                schedule_order_pending(bid, row)
            except Exception:
                logger.debug("order.pending emit skipped", exc_info=True)
    except Exception:
        logger.exception("_persist_order_to_db failed for %s (non-fatal)", order_id)


def _update_order_status_db(
    order_id: str,
    *,
    business_id: str | None = None,
    status: str = "confirmed",
) -> None:
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()
    try:
        from infrastructure.database import session_scope
        from services import order_service as db_orders

        with session_scope() as db:
            row = db_orders.get_order(db, bid, order_id.upper())
            if row:
                db_orders.update_order_status(db, row, status)
    except Exception:
        logger.exception("_update_order_status_db failed for %s", order_id)


def _order_dict_from_db_row(row: Any) -> dict[str, Any]:
    return {
        "order_id": row.order_id,
        "wa_id": row.wa_id,
        "status": row.status,
        "items": row.items or [],
        "total": float(row.total or 0),
        "customer_name": row.customer_name or "",
        "address": row.address or "",
        "delivery_type": row.delivery_type or "",
    }


def approve_order_from_app(
    order_id: str,
    *,
    business_id: str | None = None,
    db: Any | None = None,
) -> dict[str, Any]:
    """Dueño aprueba desde Flutter: confirma en BD + notifica cliente por Twilio."""
    oid = order_id.upper().strip()
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()

    # Load order from DB (single source of truth)
    order: dict[str, Any] | None = None
    if db is not None:
        from services import order_service as db_orders

        row = db_orders.get_order(db, bid, oid)
        if row:
            if row.business_id != bid:
                return {"ok": False, "message": "Pedido no pertenece a este negocio."}
            order = _order_dict_from_db_row(row)

    if not order:
        return {"ok": False, "message": f"No encontré el pedido {oid}."}

    if order.get("status") == "confirmed":
        return {"ok": True, "message": f"El pedido {oid} ya estaba confirmado."}

    # Update status in DB
    _update_order_status_db(oid, business_id=bid, status="confirmed")

    # Notify customer via Twilio
    admin = _admin_service()
    customer = admin._customer_wa_id(order)
    if not customer:
        return {
            "ok": True,
            "message": f"Pedido {oid} confirmado. No hay teléfono del cliente para avisarle.",
        }

    body_text = f"✅ ¡Tu pedido *{order_id}* fue confirmado!\n\n🚚Estamos preparando tu pedido para llevártelo a casa."
    if not admin._send_whatsapp(customer, body_text, business_id=bid):
        return {
            "ok": False,
            "message": f"Pedido {oid} confirmado en BD, pero no se pudo enviar WhatsApp al cliente.",
        }

    saved_msg = None
    if db is not None:
        from services import conversation_service as conv_svc

        saved = conv_svc.save_outgoing_message(
            db,
            customer_wa_id=customer,
            body=body_text,
            business_id=bid,
            is_admin=False,
        )
        if saved:
            saved_msg = saved[-1]

    return {"ok": True, "message": f"Pedido {oid} confirmado.", "saved_message": saved_msg}


def reject_order_from_app(
    order_id: str,
    *,
    business_id: str | None = None,
    reason: str = "",
    db: Any | None = None,
) -> dict[str, Any]:
    """Dueño rechaza desde Flutter: BD + mensaje al cliente."""
    oid = order_id.upper().strip()
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()

    order: dict[str, Any] | None = None
    if db is not None:
        from services import order_service as db_orders

        row = db_orders.get_order(db, bid, oid)
        if row:
            if row.business_id != bid:
                return {"ok": False, "message": "Pedido no pertenece a este negocio."}
            order = _order_dict_from_db_row(row)

    _update_order_status_db(oid, business_id=bid, status="rejected")

    admin = _admin_service()
    customer = admin._customer_wa_id(order) if order else ""
    if customer:
        extra = f" Motivo: {reason}" if reason else ""
        admin._send_whatsapp(
            customer,
            f"Lo sentimos, tu pedido *{oid}* no pudo ser confirmado.{extra}",
            business_id=bid,
        )
    return {"ok": True, "message": f"Pedido {oid} rechazado."}
