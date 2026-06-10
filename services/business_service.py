"""
Business (tenant) operations — Fase 5.

Entrada: .env legacy, config/intents.py, config/prompts.py.
Salida: filas en businesses + business_intents + business_prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from config import intents as default_intents
from config import prompts as default_prompts
from config.settings import (
    ADMIN_WHATSAPP_NUMBER,
    DEFAULT_BUSINESS_ID,
    DEFAULT_BUSINESS_NAME,
    TWILIO_WHATSAPP_FROM,
)
from config.sheets_config import GOOGLE_SHEETS_ENABLED, GOOGLE_SPREADSHEET_ID
from models.business import Business, BusinessIntentConfig, BusinessPromptConfig

logger = logging.getLogger(__name__)


def _normalize_whatsapp(value: str) -> str:
    return "".join(ch for ch in (value or "").strip() if ch.isdigit())


def serialize_global_command_intents() -> dict[str, Any]:
    """Copy legacy GLOBAL_COMMAND_INTENTS to JSON-safe dict."""
    out: dict[str, Any] = {}
    for command, spec in default_intents.GLOBAL_COMMAND_INTENTS.items():
        phrases = spec.get("phrases", ())
        tokens = spec.get("tokens", frozenset())
        out[command] = {
            "phrases": list(phrases) if not isinstance(phrases, list) else phrases,
            "tokens": list(tokens),
            "route": default_intents.GLOBAL_COMMAND_ROUTES.get(command, ""),
        }
    out["_routes"] = dict(default_intents.GLOBAL_COMMAND_ROUTES)
    out["_greeting_phrases"] = list(default_intents.GREETING_PHRASES)
    return out


def serialize_default_prompts() -> dict[str, str]:
    return dict(default_prompts.DEFAULT_PROMPTS)


def get_business(db: Session, business_id: str) -> Business | None:
    return db.query(Business).filter(Business.id == business_id).one_or_none()


def get_default_business(db: Session) -> Business | None:
    biz = db.query(Business).filter(Business.is_default.is_(True)).one_or_none()
    if biz:
        return biz
    return get_business(db, DEFAULT_BUSINESS_ID)


def list_businesses(db: Session) -> list[Business]:
    return db.query(Business).order_by(Business.name).all()


def resolve_business_id_for_webhook(
    db: Session,
    *,
    to_number: str = "",
    from_number: str = "",
) -> str:
    """
    Map Twilio webhook To (bot line) → business.id.
    Fallback: default business (legacy single-tenant).
    """
    candidates = [to_number, from_number]
    for raw in candidates:
        if not raw:
            continue
        digits = _normalize_whatsapp(raw)
        if not digits:
            continue
        for biz in list_businesses(db):
            bot_digits = _normalize_whatsapp(biz.twilio_whatsapp_from)
            if bot_digits and (
                digits == bot_digits
                or digits.endswith(bot_digits[-10:])
                or bot_digits.endswith(digits[-10:])
            ):
                return biz.id
    default = get_default_business(db)
    if default:
        return default.id
    return DEFAULT_BUSINESS_ID


def _seed_config_rows(db: Session, business: Business) -> None:
    intents_data = serialize_global_command_intents()
    prompts_data = serialize_default_prompts()

    intents_row = (
        db.query(BusinessIntentConfig)
        .filter(BusinessIntentConfig.business_id == business.id)
        .one_or_none()
    )
    if intents_row is None:
        db.add(
            BusinessIntentConfig(
                business_id=business.id,
                config_json=intents_data,
            )
        )
    else:
        intents_row.config_json = intents_data

    prompts_row = (
        db.query(BusinessPromptConfig)
        .filter(BusinessPromptConfig.business_id == business.id)
        .one_or_none()
    )
    if prompts_row is None:
        db.add(
            BusinessPromptConfig(
                business_id=business.id,
                config_json=prompts_data,
            )
        )
    else:
        prompts_row.config_json = prompts_data


def create_business(
    db: Session,
    *,
    business_id: str,
    name: str,
    twilio_whatsapp_from: str,
    admin_whatsapp_number: str = "",
    google_spreadsheet_id: str | None = None,
    sheets_enabled: bool = False,
    is_default: bool = False,
    seed_from_config: bool = True,
) -> Business:
    if is_default:
        db.query(Business).filter(Business.is_default.is_(True)).update(
            {"is_default": False}
        )
    biz = Business(
        id=business_id,
        name=name,
        twilio_whatsapp_from=twilio_whatsapp_from.strip(),
        admin_whatsapp_number=admin_whatsapp_number.strip(),
        google_spreadsheet_id=google_spreadsheet_id,
        sheets_enabled=sheets_enabled,
        is_default=is_default,
    )
    db.add(biz)
    db.flush()
    if seed_from_config:
        _seed_config_rows(db, biz)
    logger.info("Created business %s (%s)", biz.id, biz.name)
    return biz


def ensure_default_business(db: Session) -> Business:
    """
    Negocio default = comportamiento legacy (.env + config/* semilla).
    Idempotente: actualiza Twilio/admin si ya existe.
    """
    biz = get_business(db, DEFAULT_BUSINESS_ID)
    if biz is None:
        biz = create_business(
            db,
            business_id=DEFAULT_BUSINESS_ID,
            name=DEFAULT_BUSINESS_NAME,
            twilio_whatsapp_from=TWILIO_WHATSAPP_FROM,
            admin_whatsapp_number=ADMIN_WHATSAPP_NUMBER,
            google_spreadsheet_id=GOOGLE_SPREADSHEET_ID or None,
            sheets_enabled=GOOGLE_SHEETS_ENABLED,
            is_default=True,
            seed_from_config=True,
        )
    else:
        biz.name = DEFAULT_BUSINESS_NAME
        biz.twilio_whatsapp_from = TWILIO_WHATSAPP_FROM
        biz.admin_whatsapp_number = ADMIN_WHATSAPP_NUMBER
        biz.google_spreadsheet_id = GOOGLE_SPREADSHEET_ID or None
        biz.sheets_enabled = GOOGLE_SHEETS_ENABLED
        biz.is_default = True
        _seed_config_rows(db, biz)
        logger.info("Updated default business %s from legacy .env", biz.id)
    return biz


def get_business_intents(db: Session, business_id: str) -> dict[str, Any]:
    row = (
        db.query(BusinessIntentConfig)
        .filter(BusinessIntentConfig.business_id == business_id)
        .one_or_none()
    )
    if row and row.config_json:
        return row.config_json
    return serialize_global_command_intents()


def get_business_prompts(db: Session, business_id: str) -> dict[str, str]:
    row = (
        db.query(BusinessPromptConfig)
        .filter(BusinessPromptConfig.business_id == business_id)
        .one_or_none()
    )
    if row and row.config_json:
        return {k: str(v) for k, v in row.config_json.items()}
    return serialize_default_prompts()


def set_business_intents(
    db: Session,
    business_id: str,
    config_json: dict[str, Any],
) -> dict[str, Any]:
    """Persist intents editados desde app Flutter."""
    row = (
        db.query(BusinessIntentConfig)
        .filter(BusinessIntentConfig.business_id == business_id)
        .one_or_none()
    )
    if row is None:
        row = BusinessIntentConfig(business_id=business_id, config_json=config_json)
        db.add(row)
    else:
        row.config_json = config_json
    db.flush()
    return row.config_json


def set_business_prompts(
    db: Session,
    business_id: str,
    config_json: dict[str, str],
) -> dict[str, str]:
    """Persist textos del bot editados desde app Flutter."""
    row = (
        db.query(BusinessPromptConfig)
        .filter(BusinessPromptConfig.business_id == business_id)
        .one_or_none()
    )
    if row is None:
        row = BusinessPromptConfig(business_id=business_id, config_json=config_json)
        db.add(row)
    else:
        row.config_json = config_json
    db.flush()
    return {k: str(v) for k, v in row.config_json.items()}
