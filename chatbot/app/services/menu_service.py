"""MenuService — DB-backed, multi-tenant (via DBStore)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore


class MenuService:
    def __init__(self, store: "DBStore") -> None:
        self.sheets = store  # attr name kept for internal compatibility
        # Per-request menu override (set by business_context for testing)
        self._context_menu_override_fn = self._default_context_override

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

    def get_available_menu(self) -> List[Dict[str, Any]]:
        override = self._default_context_override()
        if override is not None:
            return override
        return [item for item in self.sheets.get_menu() if item.get("disponible", True)]

    def menu_literal_tokens(self) -> frozenset[str]:
        from app.core.parser import TextNormalizer

        tokens: set[str] = set()
        for item in self.get_available_menu():
            name = str(item.get("nombre", "")).strip()
            if name:
                tokens.update(TextNormalizer.basic(name).split())
        return frozenset(tokens)

    def format_menu(self) -> str:
        menu = self.get_available_menu()
        if not menu:
            return "Por el momento no tenemos platos disponibles. Intenta más tarde."

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in menu:
            category = item.get("categoria") or "General"
            grouped.setdefault(category, []).append(item)

        lines = ["*Nuestro menú*\n"]
        for category, items in grouped.items():
            lines.append(f"*{category}*")
            for item in items:
                lines.append(f"• {item['nombre']} — ${item['precio']:.2f}")
            lines.append("")

        return "\n".join(lines).strip()
