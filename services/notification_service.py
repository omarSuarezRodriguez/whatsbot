"""
Notificaciones admin + confirmación legacy (Fase 6).

Flujo preservado (sin cambiar lógica de AdminService):
  Cliente pide → bot guarda pedido → ADMIN_WHATSAPP_NUMBER recibe alerta
  → dueño responde CONFIRMAR ORD-XXX → bot avisa al cliente por WhatsApp.

Entrada: payloads de pedido, mensajes admin.
Salida: Twilio REST (admin + cliente) vía chatbot AdminService.
"""

from __future__ import annotations

import logging
from typing import Any

from chatbot.runtime import get_bot_context
from config.settings import DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)


def _admin_service():
    """AdminService legacy (única implementación de confirmación)."""
    return get_bot_context(start_background=False).admin_service


def is_admin_sender(wa_id: str) -> bool:
    """True si el remitente es ADMIN_WHATSAPP_NUMBER (no la línea del bot)."""
    from app.services.admin_service import AdminService

    return AdminService.is_admin(wa_id)


def notify_admin_new_order(order: dict[str, Any]) -> None:
    """
    Notifica al dueño por WhatsApp personal (legacy).
    Misma implementación que flow_engine → admin_service.notify_new_order.
    """
    _admin_service().notify_new_order(order)


def handle_admin_confirmation(
    body: str,
    *,
    business_id: str | None = None,
) -> str:
    """
    Procesa CONFIRMAR ORD-XXX / blockon / blockoff desde ADMIN_WHATSAPP_NUMBER.
    Devuelve texto de respuesta para el admin.
    """
    from app.utils.validators import extract_admin_order_id, is_admin_confirm

    reply = _admin_service().handle_admin_message(body)
    if is_admin_confirm(body):
        order_id = extract_admin_order_id(body)
        if order_id and "confirmado" in reply.lower():
            confirm_order_updates_database(order_id, business_id=business_id)
    return reply


def on_order_pending(
    order_payload: dict[str, Any],
    *,
    business_id: str | None = None,
) -> None:
    """
    Tras guardar pedido pendiente: alerta admin (legacy) + espejo opcional en BD SaaS.
    """
    notify_admin_new_order(order_payload)
    mirror_order_to_database(order_payload, business_id=business_id)


def mirror_order_to_database(
    order_payload: dict[str, Any],
    *,
    business_id: str | None = None,
) -> None:
    """Copia pedido pendiente a tabla orders (Flutter / API); no sustituye Sheets."""
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
            total = float(order_payload.get("total") or 0)
            row = db_orders.create_order(
                db,
                bid,
                order_id=order_id,
                wa_id=str(order_payload.get("wa_id", "")),
                items=items if isinstance(items, list) else [],
                total=total,
                status=str(order_payload.get("status", "pending")),
                customer_name=str(order_payload.get("customer_name", "")),
                address=str(order_payload.get("address", "")),
                delivery_type=str(order_payload.get("delivery_type", "")),
            )
            logger.debug("Order %s mirrored to DB for business %s", order_id, bid)
            try:
                from services.realtime_service import schedule_order_pending

                schedule_order_pending(bid, row)
            except Exception:
                logger.debug("order.pending emit skipped (non-fatal)", exc_info=True)
            try:
                from infrastructure.database import session_scope
                from services import sheets_sync_service as sheets_svc

                with session_scope() as sync_db:
                    sheets_svc.maybe_sync_order_after_update(sync_db, bid, order_payload)
            except Exception:
                logger.debug("Sheets order mirror skipped (non-fatal)", exc_info=True)
    except Exception:
        logger.exception("mirror_order_to_database failed for %s (non-fatal)", order_id)


def confirm_order_updates_database(
    order_id: str,
    *,
    business_id: str | None = None,
    status: str = "confirmed",
) -> None:
    """Tras confirmación legacy en Sheets, actualizar fila en BD si existe."""
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()
    try:
        from infrastructure.database import session_scope
        from services import order_service as db_orders

        with session_scope() as db:
            row = db_orders.get_order(db, bid, order_id.upper())
            if row:
                db_orders.update_order_status(db, row, status)
    except Exception:
        logger.exception("confirm_order_updates_database failed for %s", order_id)


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
    """
    Dueño aprueba desde Flutter: confirma en Sheets (legacy) + BD + avisa cliente.
    """
    oid = order_id.upper().strip()
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()
    admin = _admin_service()
    order = admin.order_service.get_order(oid)
    if not order and db is not None:
        from services import order_service as db_orders

        row = db_orders.get_order(db, bid, oid)
        if row:
            order = _order_dict_from_db_row(row)
    if not order:
        return {"ok": False, "message": f"No encontré el pedido {oid}."}
    if order.get("status") == "confirmed":
        confirm_order_updates_database(oid, business_id=bid, status="confirmed")
        return {"ok": True, "message": f"El pedido {oid} ya estaba confirmado."}
    if not admin.order_service.confirm_order(oid):
        return {"ok": False, "message": f"No pude confirmar el pedido {oid}."}
    confirm_order_updates_database(oid, business_id=bid, status="confirmed")
    customer = admin._customer_wa_id(order)
    if not customer:
        return {
            "ok": True,
            "message": (
                f"Pedido {oid} confirmado en sistema, "
                "pero no hay teléfono del cliente para avisarle."
            ),
        }
    body = (
        f"Tu pedido *{oid}* fue confirmado por el restaurante. "
        "¡Gracias por tu compra!"
    )
    if not admin._send_whatsapp(customer, body):
        return {
            "ok": False,
            "message": (
                f"Pedido {oid} confirmado en sistema, "
                "pero no se pudo enviar WhatsApp al cliente."
            ),
        }
    saved_msg = None
    if db is not None:
        from services import conversation_service as conv_svc

        saved = conv_svc.save_outgoing_message(
            db,
            customer_wa_id=customer,
            body=body,
            business_id=bid,
            is_admin=False,
        )
        if saved:
            saved_msg = saved[-1]
    return {
        "ok": True,
        "message": f"Pedido {oid} confirmado.",
        "saved_message": saved_msg,
    }


def reject_order_from_app(
    order_id: str,
    *,
    business_id: str | None = None,
    reason: str = "",
) -> dict[str, str]:
    """Dueño rechaza desde Flutter: BD + mensaje al cliente."""
    oid = order_id.upper().strip()
    bid = (business_id or DEFAULT_BUSINESS_ID or "default").strip()
    admin = _admin_service()
    order = admin.order_service.get_order(oid)
    try:
        from infrastructure.database import session_scope
        from services import order_service as db_orders

        with session_scope() as db:
            row = db_orders.get_order(db, bid, oid)
            if row:
                db_orders.update_order_status(db, row, "rejected")
    except Exception:
        logger.exception("reject_order_from_app BD update failed for %s", oid)
    customer = admin._customer_wa_id(order) if order else ""
    if customer:
        extra = f" Motivo: {reason}" if reason else ""
        admin._send_whatsapp(
            customer,
            f"Lo sentimos, tu pedido *{oid}* no pudo ser confirmado.{extra}",
        )
    return {"ok": True, "message": f"Pedido {oid} rechazado."}
