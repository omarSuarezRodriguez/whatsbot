"""
Shim hacia config centralizada.

El chatbot importa `app.config` sin cambios; los valores viven en config/.
Google Sheets eliminado — toda la persistencia va a la BD.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_FS_ROOT) not in sys.path:
    sys.path.insert(0, str(_FS_ROOT))

from config import bot_config, settings  # noqa: E402
from config.intents import GLOBAL_COMMANDS  # noqa: E402

BASE_DIR = settings.BASE_DIR
REPO_ROOT = settings.REPO_ROOT
DATA_DIR = settings.DATA_DIR

RESTAURANT_NAME = settings.RESTAURANT_NAME
FLOWS_PATH = bot_config.FLOWS_PATH
NAV_HINT = bot_config.NAV_HINT

STATE_PERSIST_PATH = settings.STATE_PERSIST_PATH
PARSER_ERROR_LOG_PATH = settings.PARSER_ERROR_LOG_PATH

ADMIN_WHATSAPP_NUMBER = settings.ADMIN_WHATSAPP_NUMBER
TWILIO_ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
TWILIO_WHATSAPP_FROM = settings.TWILIO_WHATSAPP_FROM
TWILIO_WHATSAPP_SANDBOX_NUMBER = settings.TWILIO_WHATSAPP_SANDBOX_NUMBER

ADMIN_REMINDER_INTERVAL_SECONDS = settings.ADMIN_REMINDER_INTERVAL_SECONDS
ADMIN_REMINDER_MAX_SECONDS = settings.ADMIN_REMINDER_MAX_SECONDS
BLOCKED_USERS_CACHE_TTL_SECONDS = settings.BLOCKED_USERS_CACHE_TTL_SECONDS

is_twilio_whatsapp_sandbox = settings.is_twilio_whatsapp_sandbox
use_rest_webhook_replies = settings.use_rest_webhook_replies

__all__ = [
    "BASE_DIR",
    "REPO_ROOT",
    "DATA_DIR",
    "RESTAURANT_NAME",
    "FLOWS_PATH",
    "NAV_HINT",
    "GLOBAL_COMMANDS",
    "STATE_PERSIST_PATH",
    "PARSER_ERROR_LOG_PATH",
    "ADMIN_WHATSAPP_NUMBER",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "TWILIO_WHATSAPP_SANDBOX_NUMBER",
    "ADMIN_REMINDER_INTERVAL_SECONDS",
    "ADMIN_REMINDER_MAX_SECONDS",
    "BLOCKED_USERS_CACHE_TTL_SECONDS",
    "is_twilio_whatsapp_sandbox",
    "use_rest_webhook_replies",
]
