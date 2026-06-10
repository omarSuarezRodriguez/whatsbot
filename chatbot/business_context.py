"""
Contexto por negocio para un mensaje del gateway (Fase 7).

Entrada: business_id al procesar webhook.
Salida: prompts/intents/menú activos vía contextvars (+ índice parser temporal).
"""

from __future__ import annotations

import contextvars
import copy
import logging
import threading
from contextlib import contextmanager
from typing import Any, Generator

from services.business_config_loader import (
    intents_json_to_parser_format,
    load_intents_json,
    load_menu_items,
    load_prompts,
)

logger = logging.getLogger(__name__)

_active_business_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "business_id", default=None
)
_active_prompts: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "prompts", default=None
)
_active_menu: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "menu", default=None
)

_intent_lock = threading.Lock()

from config.intents import GLOBAL_COMMAND_INTENTS as _ORIGINAL_INTENTS  # noqa: E402

_DEFAULT_INTENTS_SNAPSHOT = copy.deepcopy(_ORIGINAL_INTENTS)


def get_active_business_id() -> str | None:
    return _active_business_id.get()


def get_active_prompts() -> dict[str, str] | None:
    return _active_prompts.get()


def get_active_menu() -> list[dict[str, Any]] | None:
    return _active_menu.get()


def get_prompt(key: str, fallback: str = "") -> str:
    prompts = _active_prompts.get()
    if prompts is not None:
        return prompts.get(key, fallback)
    from config.prompts import get_prompt as default_get

    return default_get(key, fallback)


def _apply_intents_to_parser(business_id: str | None) -> None:
    global _saved_intent_index
    import config.intents as intents_mod
    from app.core import parser as parser_mod

    config_json = load_intents_json(business_id)
    parsed = intents_json_to_parser_format(config_json)
    with _intent_lock:
        intents_mod.GLOBAL_COMMAND_INTENTS.clear()
        intents_mod.GLOBAL_COMMAND_INTENTS.update(parsed)
        (
            parser_mod._INTENT_PHRASES_BY_LEN,
            parser_mod._INTENT_TOKEN_TO_COMMAND,
            parser_mod._INTENT_ALL_TOKENS,
        ) = parser_mod._build_intent_phrase_index()
        import re

        parser_mod._INTENT_HINT_RE = re.compile(
            r"\b(?:"
            + "|".join(
                re.escape(t)
                for t in sorted(parser_mod._INTENT_ALL_TOKENS, key=len, reverse=True)
            )
            + r")\b",
            re.IGNORECASE,
        )


def _restore_default_intents() -> None:
    import config.intents as intents_mod
    from app.core import parser as parser_mod

    with _intent_lock:
        intents_mod.GLOBAL_COMMAND_INTENTS.clear()
        intents_mod.GLOBAL_COMMAND_INTENTS.update(copy.deepcopy(_DEFAULT_INTENTS_SNAPSHOT))
        (
            parser_mod._INTENT_PHRASES_BY_LEN,
            parser_mod._INTENT_TOKEN_TO_COMMAND,
            parser_mod._INTENT_ALL_TOKENS,
        ) = parser_mod._build_intent_phrase_index()
        import re

        parser_mod._INTENT_HINT_RE = re.compile(
            r"\b(?:"
            + "|".join(
                re.escape(t)
                for t in sorted(parser_mod._INTENT_ALL_TOKENS, key=len, reverse=True)
            )
            + r")\b",
            re.IGNORECASE,
        )


@contextmanager
def business_scope(business_id: str | None) -> Generator[None, None, None]:
    """Activa menú/intents/prompts de BD para el procesamiento de un mensaje."""
    bid = (business_id or "").strip() or None
    tok_b = _active_business_id.set(bid)
    tok_p = _active_prompts.set(load_prompts(bid) if bid else None)
    menu = load_menu_items(bid) if bid else None
    tok_m = _active_menu.set(menu)
    try:
        if bid:
            _apply_intents_to_parser(bid)
        yield
    finally:
        if bid:
            _restore_default_intents()
        _active_menu.reset(tok_m)
        _active_prompts.reset(tok_p)
        _active_business_id.reset(tok_b)
