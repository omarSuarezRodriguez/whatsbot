"""WhatsApp Flows — dynamic product picker backed by ProductosService."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config.settings import DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)

_MAX_TITLE = 30


def parse_business_id_from_flow_token(flow_token: str) -> str:
    """flow_token format: `{business_id}:{opaque}` — fallback to default."""
    token = (flow_token or "").strip()
    if ":" in token:
        bid = token.split(":", 1)[0].strip()
        if bid:
            return bid
    return DEFAULT_BUSINESS_ID


def _productos_service():
    from chatbot.runtime import get_bot_context

    return get_bot_context(start_background=False).flow_engine.productos_service


def _category_options() -> List[Dict[str, str]]:
    svc = _productos_service()
    options: List[Dict[str, str]] = []
    for cat in svc.get_categories():
        title = str(cat)[:_MAX_TITLE]
        options.append({"id": title, "title": title})
    return options


def _product_options(category: str) -> List[Dict[str, str]]:
    svc = _productos_service()
    options: List[Dict[str, str]] = []
    for item in svc.get_products_by_category(category):
        pid = str(item.get("id", "")).strip()
        name = str(item.get("nombre", "")).strip()
        if not pid or not name:
            continue
        options.append({"id": pid, "title": name[:_MAX_TITLE]})
    return options


def _resolve_product_name(product_id: str) -> Optional[str]:
    svc = _productos_service()
    producto = svc.get_producto_by_id(product_id)
    if not producto:
        return None
    return str(producto.get("nombre", "")).strip() or None


def handle_decrypted_flow_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process decrypted Meta Flow data-exchange payload.
    Returns the JSON object that must be encrypted for Meta.
    """
    from chatbot.business_context import business_scope, get_active_business_id

    action = str(payload.get("action") or "")
    version = str(payload.get("version") or "3.0")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    flow_token = str(payload.get("flow_token") or "")
    screen = str(payload.get("screen") or "")

    if action == "ping":
        return {"data": {"status": "active"}}

    business_id = parse_business_id_from_flow_token(flow_token)

    with business_scope(business_id):
        if data.get("error"):
            logger.warning(
                "WhatsApp Flow client error business=%s screen=%s error=%s msg=%s",
                get_active_business_id() or business_id,
                screen,
                data.get("error"),
                data.get("error_message"),
            )
            return {"data": {"acknowledged": True}}

        if action == "INIT":
            categories = _category_options()
            if not categories:
                return {
                    "screen": "CATEGORIES",
                    "data": {
                        "categories": [{"id": "_empty", "title": "Sin productos"}],
                        "error_message": "No hay categorías disponibles ahora.",
                    },
                }
            return {"screen": "CATEGORIES", "data": {"categories": categories}}

        if action == "BACK":
            return {
                "screen": "CATEGORIES",
                "data": {"categories": _category_options()},
            }

        if action == "data_exchange":
            product_id = str(data.get("product") or data.get("product_id") or "").strip()
            category = str(data.get("category") or "").strip()

            if product_id:
                name = _resolve_product_name(product_id)
                if not name:
                    return {
                        "screen": "PRODUCTS",
                        "data": {
                            "products": _product_options(category) if category else [],
                            "error_message": "Producto no encontrado. Elige otro.",
                        },
                    }
                return {
                    "screen": "SUCCESS",
                    "data": {
                        "extension_message_response": {
                            "params": {
                                "flow_token": flow_token,
                                "product_id": product_id,
                                "product_name": name,
                            }
                        }
                    },
                }

            if category and category != "_empty":
                products = _product_options(category)
                if not products:
                    return {
                        "screen": "CATEGORIES",
                        "data": {
                            "categories": _category_options(),
                            "error_message": "Esa categoría no tiene productos.",
                        },
                    }
                return {"screen": "PRODUCTS", "data": {"products": products}}

            return {
                "screen": "CATEGORIES",
                "data": {
                    "categories": _category_options(),
                    "error_message": "Selecciona una categoría.",
                },
            }

    logger.warning("Unhandled WhatsApp Flow action=%s version=%s", action, version)
    return {"data": {"status": "active"}}
