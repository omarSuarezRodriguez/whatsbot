"""ProductosService — catálogo conversacional, DB-backed multi-tenant (via DBStore)."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore

# ponytail: wall-clock TTL bucket cache for get_menu(); single (business_id, bucket) entry.
# ceiling: stale menu visible for up to _MENU_TTL_SECONDS after a catalog change.
# upgrade: invalidate via signal from PUT /menu endpoint in the API layer.
_MENU_TTL_SECONDS = 30
_menu_cache: Optional[Tuple[str, int, List[Dict[str, Any]]]] = None  # (bid, bucket, items)


class ProductosService:
    def __init__(self, store: "DBStore") -> None:
        self.sheets = store  # attr name kept for internal compatibility
        self._context_productos_override_fn = self._default_context_override

    @staticmethod
    def _default_context_override() -> Optional[List[Dict[str, Any]]]:
        try:
            from chatbot.business_context import get_active_menu

            override = get_active_menu()
            if override is not None:
                return [item for item in override if item.get("disponible", True)]
        except ImportError:
            pass
        return None

    @staticmethod
    def _active_bid() -> str:
        try:
            from chatbot.business_context import get_active_business_id

            bid = get_active_business_id()
            if bid:
                return bid
        except Exception:
            pass
        return ""

    def get_available_productos(self) -> List[Dict[str, Any]]:
        global _menu_cache
        override = self._default_context_override()
        if override is not None:
            return override
        bid = self._active_bid()
        bucket = math.floor(time.monotonic() / _MENU_TTL_SECONDS)
        cached = _menu_cache
        if cached is not None and cached[0] == bid and cached[1] == bucket:
            return cached[2]
        fresh = [item for item in self.sheets.get_menu() if item.get("disponible", True)]
        _menu_cache = (bid, bucket, fresh)
        return fresh

    def productos_literal_tokens(self) -> frozenset[str]:
        from app.core.parser import TextNormalizer

        tokens: set[str] = set()
        for item in self.get_available_productos():
            name = str(item.get("nombre", "")).strip()
            if name:
                tokens.update(TextNormalizer.basic(name).split())
        return frozenset(tokens)

    def format_productos(self, templates: Dict[str, str] | None = None) -> str:
        from app.core.parser import OrderParser  # lazy: evita ciclos al arrancar FlowEngine

        tpl = templates or {}
        empty = tpl.get("productos_empty", "")
        category_header = tpl.get("productos_category_header", "*{{category}}*")
        item_line = tpl.get("productos_item_line", "• {{name}} — ${{price}}")
        category_end = tpl.get("productos_category_end", "")

        productos = self.get_available_productos()
        if not productos:
            return empty

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in productos:
            category = item.get("categoria") or "General"
            grouped.setdefault(category, []).append(item)

        chunks: List[str] = []
        for category, items in grouped.items():
            chunks.append(
                category_header.replace("{{category}}", str(category))
            )
            for item in items:
                line = item_line.replace("{{name}}", str(item["nombre"]))
                precio = float(item.get("precio") or 0)
                line = line.replace("{{price}}", OrderParser._fmt_cop(precio))
                chunks.append(line)
            chunks.append(category_end)
        return "".join(chunks).rstrip("\n")


    
    def get_producto_by_id(
        self,
        producto_id: str,
    ) -> dict | None:

        for item in self.get_available_productos():

            if str(item["id"]) == str(producto_id):
                return item

        return None

    def get_categories(self) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for item in self.get_available_productos():
            cat = item.get("categoria") or "General"
            if cat not in seen:
                seen.add(cat)
                result.append(cat)
        return result

    def get_products_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [
            item for item in self.get_available_productos()
            if (item.get("categoria") or "General") == category
        ]

    def format_category_products(
        self, category: str, templates: Dict[str, str] | None = None
    ) -> str:
        from app.core.parser import OrderParser

        tpl = templates or {}
        empty = tpl.get("productos_empty", "")
        item_line = tpl.get("productos_item_line", "• {{name}} — ${{price}}")

        productos = self.get_products_by_category(category)
        if not productos:
            return empty

        chunks: List[str] = []
        for item in productos:
            line = item_line.replace("{{name}}", str(item["nombre"]))
            precio = float(item.get("precio") or 0)
            line = line.replace("{{price}}", OrderParser._fmt_cop(precio))
            chunks.append(line)
        return "".join(chunks).rstrip("\n")