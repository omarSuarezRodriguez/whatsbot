"""
Per-business request context (Fase 7+, OLA 2).

Activates menu/intents/prompts for the current message via contextvars.
Intent index is stored in a contextvar — no global mutation, safe under concurrency.
"""

from __future__ import annotations

import contextvars
import functools
import logging
import re
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


# ---------------------------------------------------------------------------
# Per-business intent index (LRU cache, NOT globals — safe under concurrency)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=64)
def _build_intent_index_for_business(business_id: str) -> tuple:
    """Build and cache the intent index for a given business_id."""
    from app.core.parser import _build_intent_phrase_index, _strip_accents
    from config.intents import GLOBAL_COMMAND_INTENTS as DEFAULT_INTENTS

    config_json = load_intents_json(business_id)
    parsed = intents_json_to_parser_format(config_json)

    # Temporarily swap GLOBAL_COMMAND_INTENTS in a local scope to build the index
    import copy
    import config.intents as intents_mod
    original = copy.deepcopy(intents_mod.GLOBAL_COMMAND_INTENTS)
    intents_mod.GLOBAL_COMMAND_INTENTS.clear()
    intents_mod.GLOBAL_COMMAND_INTENTS.update(parsed)
    try:
        phrases, tok2cmd, all_tokens = _build_intent_phrase_index()
    finally:
        intents_mod.GLOBAL_COMMAND_INTENTS.clear()
        intents_mod.GLOBAL_COMMAND_INTENTS.update(original)

    hint_re = re.compile(
        r"\b(?:"
        + "|".join(re.escape(t) for t in sorted(all_tokens, key=len, reverse=True))
        + r")\b",
        re.IGNORECASE,
    ) if all_tokens else re.compile(r"(?!)")

    return (phrases, tok2cmd, all_tokens, hint_re)


@contextmanager
def business_scope(business_id: str | None) -> Generator[None, None, None]:
    """Activate per-business prompts/menu/intents for one message."""
    bid = (business_id or "").strip() or None

    tok_b = _active_business_id.set(bid)
    tok_p = _active_prompts.set(load_prompts(bid) if bid else None)
    menu = load_menu_items(bid) if bid else None
    tok_m = _active_menu.set(menu)

    # Set per-request intent index via contextvar (no global mutation)
    from app.core.parser import _active_intent_index

    if bid:
        try:
            idx = _build_intent_index_for_business(bid)
        except Exception:
            logger.warning("Intent index build failed for %s — using defaults", bid, exc_info=True)
            idx = None
    else:
        idx = None
    tok_i = _active_intent_index.set(idx)

    try:
        yield
    finally:
        _active_intent_index.reset(tok_i)
        _active_menu.reset(tok_m)
        _active_prompts.reset(tok_p)
        _active_business_id.reset(tok_b)
