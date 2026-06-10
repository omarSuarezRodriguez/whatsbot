"""
Carga menú, intents y prompts por business_id (Fase 7).

Entrada: business_id.
Salida: dicts desde BD; si vacío → fallback config/* y Sheets (menú).
"""

from __future__ import annotations

import logging
from typing import Any

from config import intents as default_intents
from config import prompts as default_prompts
from config.settings import DEFAULT_BUSINESS_ID
from infrastructure.database import session_scope
from services import business_service as biz_svc
from services import menu_service as menu_svc

logger = logging.getLogger(__name__)


def _normalize_business_id(business_id: str | None) -> str | None:
    if not business_id:
        return None
    bid = business_id.strip()
    return bid or None


def load_prompts(business_id: str | None) -> dict[str, str]:
    bid = _normalize_business_id(business_id)
    if not bid:
        return dict(default_prompts.DEFAULT_PROMPTS)
    try:
        with session_scope() as db:
            return biz_svc.get_business_prompts(db, bid)
    except Exception:
        logger.exception("load_prompts failed for %s; using defaults", bid)
        return dict(default_prompts.DEFAULT_PROMPTS)


def load_intents_json(business_id: str | None) -> dict[str, Any]:
    bid = _normalize_business_id(business_id)
    if not bid:
        return biz_svc.serialize_global_command_intents()
    try:
        with session_scope() as db:
            return biz_svc.get_business_intents(db, bid)
    except Exception:
        logger.exception("load_intents failed for %s; using defaults", bid)
        return biz_svc.serialize_global_command_intents()


def intents_json_to_parser_format(config_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convierte JSON de BD al formato GLOBAL_COMMAND_INTENTS del parser."""
    routes = config_json.get("_routes") or default_intents.GLOBAL_COMMAND_ROUTES
    out: dict[str, dict[str, Any]] = {}
    for command in default_intents.GLOBAL_COMMAND_ROUTES:
        spec = config_json.get(command)
        if not isinstance(spec, dict):
            continue
        phrases = spec.get("phrases", ())
        tokens = spec.get("tokens", frozenset())
        out[command] = {
            "phrases": tuple(phrases) if isinstance(phrases, list) else phrases,
            "tokens": frozenset(tokens) if isinstance(tokens, list) else tokens,
        }
    if not out:
        return dict(default_intents.GLOBAL_COMMAND_INTENTS)
    return out


def load_menu_items(business_id: str | None) -> list[dict[str, Any]] | None:
    """
    Menú desde BD si hay filas; None = usar Sheets/cache legacy.
    """
    bid = _normalize_business_id(business_id) or DEFAULT_BUSINESS_ID
    try:
        with session_scope() as db:
            rows = menu_svc.list_menu_items(db, bid, available_only=False)
            if not rows:
                return None
            return [
                {
                    "id": item.external_id or str(item.id),
                    "nombre": item.nombre,
                    "precio": float(item.precio),
                    "categoria": item.categoria,
                    "disponible": item.disponible,
                }
                for item in rows
            ]
    except Exception:
        logger.exception("load_menu_items failed for %s", bid)
        return None


def get_prompt(business_id: str | None, key: str, fallback: str = "") -> str:
    prompts = load_prompts(business_id)
    return prompts.get(key, default_prompts.DEFAULT_PROMPTS.get(key, fallback))
