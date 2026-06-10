"""Google Sheets optional sync — env vars only (secrets in .env)."""

from __future__ import annotations

import os

from config.settings import BASE_DIR

GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON_PATH",
    os.getenv(
        "GOOGLE_SHEETS_CREDENTIALS_PATH",
        str(BASE_DIR / "credentials" / "google-service-account.json"),
    ),
)
GOOGLE_SHEETS_CREDENTIALS_PATH = GOOGLE_SERVICE_ACCOUNT_JSON_PATH

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_SHEET_ID_MENU = os.getenv("GOOGLE_SHEET_ID_MENU", GOOGLE_SPREADSHEET_ID)
GOOGLE_SHEET_ID_ORDERS = os.getenv("GOOGLE_SHEET_ID_ORDERS", GOOGLE_SPREADSHEET_ID)

MENU_CACHE_TTL_SECONDS = int(os.getenv("MENU_CACHE_TTL_SECONDS", "60"))
ORDERS_CACHE_TTL_SECONDS = int(os.getenv("ORDERS_CACHE_TTL_SECONDS", "30"))
BLOCKED_USERS_CACHE_TTL_SECONDS = int(
    os.getenv("BLOCKED_USERS_CACHE_TTL_SECONDS", "15")
)
SHEETS_INCREMENTAL_THRESHOLD = int(os.getenv("SHEETS_INCREMENTAL_THRESHOLD", "500"))
SHEETS_FULL_REFRESH_INTERVAL_SECONDS = int(
    os.getenv("SHEETS_FULL_REFRESH_INTERVAL_SECONDS", "3600")
)
SHEETS_INCREMENTAL_BATCH_SIZE = int(os.getenv("SHEETS_INCREMENTAL_BATCH_SIZE", "100"))

# -----------------------------------------------------------------------------
# GUÍA RÁPIDA
# - Entrada: .env + credentials/google-service-account.json.
# - Salida: TTL y IDs para google_sheets.py vía app.config shim.
# - GOOGLE_SHEETS_CREDENTIALS_PATH alias del nombre legacy.
# -----------------------------------------------------------------------------
