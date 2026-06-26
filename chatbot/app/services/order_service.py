"""OrderService — DB-backed, multi-tenant (via DBStore)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.core.parser import OrderParser
from app.services.menu_service import MenuService

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


class OrderService:
    def __init__(self, store: "DBStore", menu_service: MenuService) -> None:
        self.sheets = store  # attr name kept for internal compatibility
        self.menu_service = menu_service

    def _parser(self) -> OrderParser:
        """Always build fresh from current DB menu (multi-tenant, no stale cache)."""
        menu = self.menu_service.get_available_menu()
        return OrderParser(menu)

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
