"""Bot session defaults — flows, navigation, branding."""

from __future__ import annotations

import os
from pathlib import Path

from config.prompts import get_prompt
from config.settings import BASE_DIR, RESTAURANT_NAME

GLOBAL_COMMANDS = frozenset({"menu", "pedido", "reservar", "inicio", "cancelar"})

NAV_HINT = (
    "\n\n---\n"
    "Escribe *inicio* para volver al inicio\n"
)

NAVIGATION_HINT_ENABLED = True
CANCEL_MESSAGE_DEFAULT = get_prompt(
    "cancel_message",
    "Entendido, cancelé el proceso actual. Estoy aquí cuando quieras continuar.",
)


def resolve_flows_path() -> Path:
    flows_env = os.getenv("FLOWS_PATH", "").strip()
    if flows_env:
        path = Path(flows_env)
        if not flows_env.startswith(("/", "\\")) and ":" not in flows_env[:3]:
            return (BASE_DIR / flows_env).resolve()
        return path.resolve()
    return BASE_DIR / "flows" / "restaurant_flow.json"


FLOWS_PATH = resolve_flows_path()

# -----------------------------------------------------------------------------
# GUÍA RÁPIDA
# - Entrada: FLOWS_PATH en .env o flows/restaurant_flow.json bajo final_system/.
# - Salida: FLOWS_PATH, NAV_HINT, RESTAURANT_NAME para flow_engine.
# - El dueño edita textos en Flutter; flujo JSON/BD en fases posteriores.
# -----------------------------------------------------------------------------
