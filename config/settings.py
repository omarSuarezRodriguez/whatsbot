"""Global settings loaded from final_system/.env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Raíz autocontenida de final_system (logs, flows por defecto, etc.)
REPO_ROOT = BASE_DIR
load_dotenv(BASE_DIR / ".env")

# API / server
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
FLASK_ENV = os.getenv("FLASK_ENV", "production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0")

# Database
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/whatsbot",
)

# Redis (optional)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# JWT (Flutter WhatsBot)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", ""))
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
SECRET_KEY = os.getenv("SECRET_KEY", JWT_SECRET_KEY)
# PIN para login app Flutter (dueño); en prod usar valor fuerte en .env
WHATSBOT_OWNER_PIN = os.getenv("WHATSBOT_OWNER_PIN", "changeme")

# Branding (legacy RESTAURANT_NAME → DEFAULT_BUSINESS_NAME)
RESTAURANT_NAME = os.getenv(
    "RESTAURANT_NAME",
    os.getenv("DEFAULT_BUSINESS_NAME", "La Casa del Sabor"),
)
DEFAULT_BUSINESS_NAME = os.getenv("DEFAULT_BUSINESS_NAME", RESTAURANT_NAME)
DEFAULT_BUSINESS_ID = os.getenv("DEFAULT_BUSINESS_ID", "default").strip() or "default"

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
TWILIO_REST_WEBHOOK_REPLIES = os.getenv("TWILIO_REST_WEBHOOK_REPLIES", "0").strip()
TWILIO_WHATSAPP_SANDBOX_NUMBER = "+14155238886"

# Admin legacy
ADMIN_WHATSAPP_NUMBER = os.getenv("ADMIN_WHATSAPP_NUMBER", "").strip()
ADMIN_REMINDER_INTERVAL_SECONDS = int(
    os.getenv("ADMIN_REMINDER_INTERVAL_SECONDS", "300")
)
ADMIN_REMINDER_MAX_SECONDS = int(os.getenv("ADMIN_REMINDER_MAX_SECONDS", "3600"))

# Paths
DATA_DIR = BASE_DIR / "data"
STATE_PERSIST_PATH = os.getenv(
    "STATE_PERSIST_PATH",
    str(DATA_DIR / "user_states.json"),
)
PARSER_ERROR_LOG_PATH = os.getenv(
    "PARSER_ERROR_LOG_PATH",
    str(DATA_DIR / "parser_errors.jsonl"),
)

# Scripts
DEPLOY_URL = os.getenv("DEPLOY_URL", API_PUBLIC_URL).rstrip("/")
DEPLOY_TIMEOUT = int(os.getenv("DEPLOY_TIMEOUT", "60"))

# Realtime (Fase 11 — WebSocket + push)
REALTIME_ENABLED = os.getenv("REALTIME_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WS_HEARTBEAT_SECONDS = int(os.getenv("WS_HEARTBEAT_SECONDS", "30"))
FCM_ENABLED = os.getenv("FCM_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FCM_SERVICE_ACCOUNT_JSON_PATH = os.getenv("FCM_SERVICE_ACCOUNT_JSON_PATH", "").strip()
FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip()


def is_twilio_whatsapp_sandbox() -> bool:
    from_digits = "".join(ch for ch in TWILIO_WHATSAPP_FROM if ch.isdigit())
    sandbox_digits = TWILIO_WHATSAPP_SANDBOX_NUMBER.lstrip("+")
    return sandbox_digits in from_digits or from_digits.endswith(sandbox_digits)


def twilio_status_callback_url() -> str | None:
    """URL pública para status callbacks de Twilio (MessageSid → sent/delivered/read)."""
    base = API_PUBLIC_URL.rstrip("/")
    if not base or base.startswith("http://127.0.0.1"):
        return None
    return f"{base}/webhook/status"


def use_rest_webhook_replies() -> bool:
    explicit = TWILIO_REST_WEBHOOK_REPLIES.lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return not is_twilio_whatsapp_sandbox()


# -----------------------------------------------------------------------------
# GUÍA RÁPIDA
# - Entrada: variables en final_system/.env.
# - Salida: constantes usadas por api/, services/, infrastructure/, chatbot shim.
# - Solo secrets y URLs en .env; no hardcodear tokens aquí.
# - Fase 3: única fuente para Twilio, admin, JWT, paths y servidor.
# -----------------------------------------------------------------------------
