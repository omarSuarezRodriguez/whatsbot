from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR
from app.integrations.google_sheets import GoogleSheetsClient

_MENU_CACHE_PATH = DATA_DIR / "menu_cache.json"


class MenuService:
    def __init__(self, sheets: GoogleSheetsClient) -> None:
        self.sheets = sheets
        self._formatted_menu_cache: Optional[str] = None
        self._formatted_menu_mtime: float = -1.0
        self._available_menu_cache: Optional[List[Dict[str, Any]]] = None
        self._available_menu_mtime: float = -1.0
        self._literal_tokens_cache: Optional[frozenset[str]] = None
        self._literal_tokens_mtime: float = -1.0

    @staticmethod
    def _menu_cache_mtime() -> float:
        if not _MENU_CACHE_PATH.exists():
            return 0.0
        return _MENU_CACHE_PATH.stat().st_mtime

    @staticmethod
    def _context_menu_override() -> Optional[List[Dict[str, Any]]]:
        try:
            from chatbot.business_context import get_active_menu

            override = get_active_menu()
            if override is not None:
                return [item for item in override if item.get("disponible", True)]
        except ImportError:
            pass
        return None

    def _fetch_available_menu(self) -> List[Dict[str, Any]]:
        override = self._context_menu_override()
        if override is not None:
            return override
        return [
            item for item in self.sheets.get_menu() if item.get("disponible", True)
        ]

    def _refresh_available_menu_if_stale(self) -> List[Dict[str, Any]]:
        override = self._context_menu_override()
        if override is not None:
            return override

        mtime = self._menu_cache_mtime()
        if (
            self._available_menu_cache is not None
            and self._available_menu_mtime == mtime
        ):
            return self._available_menu_cache

        menu = self._fetch_available_menu()
        self._available_menu_cache = menu
        self._available_menu_mtime = mtime
        self._literal_tokens_cache = None
        self._literal_tokens_mtime = -1.0
        return menu

    def get_available_menu(self) -> List[Dict[str, Any]]:
        try:
            from flask import g, has_request_context
        except ImportError:
            return self._refresh_available_menu_if_stale()

        if not has_request_context():
            return self._refresh_available_menu_if_stale()

        cached = getattr(g, "_available_menu_cache", None)
        if cached is not None:
            return cached

        menu = self._refresh_available_menu_if_stale()
        g._available_menu_cache = menu
        return menu

    def menu_literal_tokens(self) -> frozenset[str]:
        """Cached product-name tokens for intent detection (hot path)."""
        mtime = self._menu_cache_mtime()
        if (
            self._literal_tokens_cache is not None
            and self._literal_tokens_mtime == mtime
        ):
            return self._literal_tokens_cache

        from app.core.parser import TextNormalizer

        tokens: set[str] = set()
        for item in self.get_available_menu():
            name = str(item.get("nombre", "")).strip()
            if name:
                tokens.update(TextNormalizer.basic(name).split())
        self._literal_tokens_cache = frozenset(tokens)
        self._literal_tokens_mtime = mtime
        return self._literal_tokens_cache

    def format_menu(self) -> str:
        override = self._context_menu_override()
        if override is None:
            mtime = self._menu_cache_mtime()
            if (
                self._formatted_menu_cache is not None
                and self._formatted_menu_mtime == mtime
            ):
                return self._formatted_menu_cache
            menu = self.get_available_menu()
        else:
            menu = override
        if not menu:
            formatted = (
                "Por el momento no tenemos platos disponibles. Intenta más tarde."
            )
        else:
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

            formatted = "\n".join(lines).strip()

        if override is None:
            self._formatted_menu_cache = formatted
            self._formatted_menu_mtime = self._menu_cache_mtime()
        return formatted
