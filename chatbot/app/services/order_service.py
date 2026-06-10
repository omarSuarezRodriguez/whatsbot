from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import DATA_DIR
from app.core.parser import OrderParser
from app.integrations.google_sheets import GoogleSheetsClient
from app.services.menu_service import MenuService

_MENU_CACHE_PATH = DATA_DIR / "menu_cache.json"


class OrderService:
    def __init__(self, sheets: GoogleSheetsClient, menu_service: MenuService) -> None:
        self.sheets = sheets
        self.menu_service = menu_service
        self._cached_parser: Optional[OrderParser] = None
        self._parser_menu_mtime: float = -1.0

    @staticmethod
    def _menu_cache_mtime() -> float:
        if not _MENU_CACHE_PATH.exists():
            return 0.0
        return _MENU_CACHE_PATH.stat().st_mtime

    def _parser(self) -> OrderParser:
        mtime = self._menu_cache_mtime()
        if self._cached_parser is not None and self._parser_menu_mtime == mtime:
            return self._cached_parser
        menu = self.menu_service.get_available_menu()
        self._cached_parser = OrderParser(menu)
        self._parser_menu_mtime = mtime
        return self._cached_parser

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
        return order_id, total

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self.sheets.get_order(order_id)

    def confirm_order(self, order_id: str) -> bool:
        return self.sheets.update_order_status(order_id, "confirmed")
