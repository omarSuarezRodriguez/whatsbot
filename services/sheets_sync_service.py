"""
Optional Google Sheets mirror — Fase 8.

PostgreSQL = fuente de verdad. Sheets = espejo editable opcional.
Con GOOGLE_SHEETS_ENABLED=false (default) todas las funciones son no-op seguro.

Entrada: business.sheets_enabled + config global + filas BD (menú/pedidos).
Salida: push a legacy GoogleSheetsClient; errores logueados, nunca bloquean webhook/API.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from config.sheets_config import GOOGLE_SHEETS_ENABLED, GOOGLE_SPREADSHEET_ID
from models.business import Business
from services import menu_service as menu_svc
from services import order_service as order_svc

logger = logging.getLogger(__name__)


def is_globally_enabled() -> bool:
    return GOOGLE_SHEETS_ENABLED


def is_enabled_for_business(business: Business | None) -> bool:
    """Global flag AND per-business toggle."""
    if not GOOGLE_SHEETS_ENABLED:
        return False
    if business is None:
        return False
    return bool(business.sheets_enabled)


def _legacy_sheets_client():
    """Reuse chatbot singleton (same wiring as runtime.py)."""
    from chatbot.runtime import get_bot_context

    return get_bot_context(start_background=False).admin_service.sheets


def get_status(db: Session, business_id: str) -> dict[str, Any]:
    """
    Estado Sheets para Ajustes en Flutter.
    No lanza excepciones si Sheets está apagado o sin credenciales.
    """
    from services.business_service import get_business

    biz = get_business(db, business_id)
    global_on = GOOGLE_SHEETS_ENABLED
    business_on = bool(biz and biz.sheets_enabled)
    spreadsheet_id = (biz.google_spreadsheet_id if biz else None) or GOOGLE_SPREADSHEET_ID

    connected = False
    cache: dict[str, Any] = {}
    if global_on and business_on:
        try:
            client = _legacy_sheets_client()
            connected = bool(client.cache_status().get("sheets_connected"))
            cache = client.cache_status()
        except Exception as exc:
            logger.debug("Sheets status probe failed: %s", exc)

    return {
        "global_enabled": global_on,
        "business_enabled": business_on,
        "active": global_on and business_on,
        "spreadsheet_id": spreadsheet_id or None,
        "sheets_connected": connected,
        "cache": cache,
    }


def set_business_sheets_settings(
    db: Session,
    business_id: str,
    *,
    sheets_enabled: bool,
    google_spreadsheet_id: str | None = None,
) -> Business:
    """Toggle mirror por negocio (desde app Ajustes o API)."""
    from services.business_service import get_business

    biz = get_business(db, business_id)
    if not biz:
        raise ValueError(f"Negocio no encontrado: {business_id}")
    if not GOOGLE_SHEETS_ENABLED and sheets_enabled:
        raise ValueError(
            "Google Sheets está deshabilitado globalmente (GOOGLE_SHEETS_ENABLED=false)"
        )
    biz.sheets_enabled = sheets_enabled
    if google_spreadsheet_id is not None:
        biz.google_spreadsheet_id = google_spreadsheet_id.strip() or None
    db.flush()
    logger.info(
        "Business %s sheets_enabled=%s spreadsheet=%s",
        business_id,
        sheets_enabled,
        biz.google_spreadsheet_id,
    )
    return biz


def sync_menu(db: Session, business_id: str) -> dict[str, Any]:
    """BD menu_items → hoja MENU. No-op si Sheets inactivo."""
    from services.business_service import get_business

    biz = get_business(db, business_id)
    if not is_enabled_for_business(biz):
        return {
            "ok": True,
            "skipped": True,
            "message": "Sheets deshabilitado (global o negocio)",
            "items_synced": 0,
        }
    items = menu_svc.list_menu_items(db, business_id)
    rows = [
        {
            "id": item.external_id or str(item.id),
            "external_id": item.external_id,
            "nombre": item.nombre,
            "precio": item.precio,
            "categoria": item.categoria,
            "disponible": item.disponible,
        }
        for item in items
    ]
    try:
        client = _legacy_sheets_client()
        ok = client.replace_menu_mirror(rows)
    except Exception as exc:
        logger.exception("sync_menu failed for %s", business_id)
        return {"ok": False, "skipped": False, "message": str(exc), "items_synced": 0}
    if not ok:
        return {
            "ok": False,
            "skipped": False,
            "message": "No se pudo escribir en Google Sheets (sin conexión)",
            "items_synced": 0,
        }
    return {
        "ok": True,
        "skipped": False,
        "message": f"Menú sincronizado ({len(rows)} ítems)",
        "items_synced": len(rows),
    }


def sync_orders(
    db: Session,
    business_id: str,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """BD orders → hoja ORDERS. No-op si Sheets inactivo."""
    from services.business_service import get_business

    biz = get_business(db, business_id)
    if not is_enabled_for_business(biz):
        return {
            "ok": True,
            "skipped": True,
            "message": "Sheets deshabilitado (global o negocio)",
            "orders_synced": 0,
        }
    orders = order_svc.list_orders(db, business_id, limit=limit)
    synced = 0
    errors = 0
    try:
        client = _legacy_sheets_client()
        for order in orders:
            payload = {
                "order_id": order.order_id,
                "wa_id": order.wa_id,
                "items": order.items,
                "total": order.total,
                "status": order.status,
                "created_at": order.created_at,
                "customer_name": order.customer_name,
                "address": order.address,
                "delivery_type": order.delivery_type,
            }
            if client.upsert_order_mirror(payload):
                synced += 1
            else:
                errors += 1
    except Exception as exc:
        logger.exception("sync_orders failed for %s", business_id)
        return {"ok": False, "skipped": False, "message": str(exc), "orders_synced": synced}
    ok = errors == 0 or synced > 0
    return {
        "ok": ok,
        "skipped": False,
        "message": f"Pedidos sincronizados: {synced}" + (f", {errors} fallos" if errors else ""),
        "orders_synced": synced,
        "errors": errors,
    }


def sync_all(db: Session, business_id: str) -> dict[str, Any]:
    """Menú + pedidos en una llamada."""
    menu_result = sync_menu(db, business_id)
    orders_result = sync_orders(db, business_id)
    skipped = menu_result.get("skipped") and orders_result.get("skipped")
    ok = menu_result.get("ok", False) and orders_result.get("ok", False)
    return {
        "ok": ok,
        "skipped": skipped,
        "menu": menu_result,
        "orders": orders_result,
    }


def maybe_sync_menu_after_update(db: Session, business_id: str) -> None:
    """Hook post-PUT menú: fire-and-forget, nunca propaga error."""
    try:
        sync_menu(db, business_id)
    except Exception:
        logger.exception("maybe_sync_menu_after_update failed (non-fatal)")


def maybe_sync_order_after_update(
    db: Session,
    business_id: str,
    order_payload: dict[str, Any],
) -> None:
    """Hook tras pedido en BD: espejo opcional a Sheets."""
    from services.business_service import get_business

    biz = get_business(db, business_id)
    if not is_enabled_for_business(biz):
        return
    try:
        client = _legacy_sheets_client()
        client.upsert_order_mirror(order_payload)
    except Exception:
        logger.exception("maybe_sync_order_after_update failed (non-fatal)")


def order_payload_from_row(order: Any) -> dict[str, Any]:
    """Serializa modelo Order o dict legacy a payload mirror."""
    if isinstance(order, dict):
        return order
    return {
        "order_id": order.order_id,
        "wa_id": order.wa_id,
        "items": order.items,
        "total": order.total,
        "status": order.status,
        "created_at": getattr(order, "created_at", datetime.utcnow()),
        "customer_name": order.customer_name,
        "address": order.address,
        "delivery_type": order.delivery_type,
    }
