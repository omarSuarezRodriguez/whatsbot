"""Central configuration package (4 modules + .env secrets)."""

from config import bot_config, intents, prompts, settings

__all__ = [
    "bot_config",
    "intents",
    "prompts",
    "settings",
]
