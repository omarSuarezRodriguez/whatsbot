"""ProductosService — catálogo conversacional, DB-backed multi-tenant (via DBStore)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


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

    def get_available_productos(self) -> List[Dict[str, Any]]:
        override = self._default_context_override()
        if override is not None:
            return override
        return [item for item in self.sheets.get_menu() if item.get("disponible", True)]

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
