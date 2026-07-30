"""OrderService — DB-backed, multi-tenant (via DBStore)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.core.parser import OrderParser
from app.services.productos_service import ProductosService

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


class OrderService:
    def __init__(self, store: "DBStore", productos_service: ProductosService) -> None:
        self.sheets = store  # attr name kept for internal compatibility
        self.productos_service = productos_service

    def _parser(self) -> OrderParser:
        """Build or reuse engine keyed by (business_id, catalog fingerprint)."""
        productos = self.productos_service.get_available_productos()
        try:
            from chatbot.business_context import get_active_business_id  # lazy import
            bid: str = get_active_business_id() or ""
        except Exception:  # noqa: BLE001
            bid = ""
        return OrderParser(productos, business_id=bid)

    def parse_order_text(
        self,
        text: str,
        current_cart: List[Dict[str, Any]] | None = None,
        wa_id: str = "",
    ) -> Dict[str, Any]:
        return self._parser().apply_message(text, current_cart, wa_id=wa_id)

    def format_cart(self, items: List[Dict[str, Any]]) -> str:
        return OrderParser.format_cart(items)

    def cart_total(self, items: List[Dict[str, Any]]) -> float:
        return OrderParser.cart_total(items)

    def get_cart_item(
        self,
        items: List[Dict[str, Any]],
        product_id: str,
    ) -> Optional[Dict[str, Any]]:
        for item in items:
            if str(item.get("product_id") or "") == str(product_id):
                return dict(item)
        return None

    def update_cart_quantity(
        self,
        items: List[Dict[str, Any]],
        product_id: str,
        quantity: int,
    ) -> Optional[List[Dict[str, Any]]]:
        if quantity < 1 or quantity > 20:
            return None

        updated = [dict(item) for item in items]

        for item in updated:
            if str(item.get("product_id") or "") != str(product_id):
                continue

            item["qty"] = quantity
            item["subtotal"] = round(
                quantity * float(item.get("unit_price") or 0),
                2,
            )
            return updated

        return None

    def remove_cart_product(
        self,
        items: List[Dict[str, Any]],
        product_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        updated = [
            dict(item)
            for item in items
            if str(item.get("product_id") or "") != str(product_id)
        ]

        if len(updated) == len(items):
            return None

        return updated

    def save_order(
        self,
        wa_id: str,
        items: List[Dict[str, Any]],
        customer_name: str = "",
        address: str = "",
        delivery_type: str = "",
    ) -> Tuple[str, float]:
        """Persist order. wa_id is expected canonical E.164 (gateway canonical_wa_id)."""
        total = self.cart_total(items)
        order_id = self.sheets.create_order(
            wa_id=wa_id,
            items=items,
            total=total,
            status="pending",
            customer_name=customer_name,
            address=address,
            delivery_type=delivery_type,
        )
        order = self.get_order(order_id)
        if order:
            from services.notification_service import notify_admin_new_order

            notify_admin_new_order(order)
        return order_id, total

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self.sheets.get_order(order_id)

    def confirm_order(self, order_id: str) -> bool:
        return self.sheets.update_order_status(order_id, "confirmed")
