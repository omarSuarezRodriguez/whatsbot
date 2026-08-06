"""Lazy singleton wiring for chatbot services (DB-backed, no Sheets)."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# final_system root (services/, config/) + chatbot/app as package `app`
_FS_ROOT = Path(__file__).resolve().parent.parent
_CHATBOT_ROOT = Path(__file__).resolve().parent
for _path in (_FS_ROOT, _CHATBOT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import STATE_PERSIST_PATH  # noqa: E402
from app.core.flow_engine import FlowEngine  # noqa: E402
from app.core.state_manager import StateManager  # noqa: E402
from app.integrations.db_store import get_db_store  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402
from app.services.ayuda_service import AyudaService  # noqa: E402
from app.services.blocked_users_cache import BlockedUsersCache  # noqa: E402
from app.services.order_service import OrderService  # noqa: E402
from app.services.productos_service import ProductosService  # noqa: E402
from app.services.user_service import UserService  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class BotContext:
    flow_engine: FlowEngine
    user_service: UserService
    admin_service: AdminService
    blocked_cache: BlockedUsersCache


_context: Optional[BotContext] = None


def get_bot_context(*, start_background: bool = True) -> BotContext:
    """Build or return cached bot services (all DB-backed)."""
    global _context
    if _context is not None:
        return _context

    store = get_db_store()
    state_manager = StateManager(persist_path=STATE_PERSIST_PATH)
    productos_service = ProductosService(store)
    order_service = OrderService(store, productos_service)
    ayuda_service = AyudaService(store)
    user_service = UserService(store)
    admin_service = AdminService(store, order_service)
    blocked_cache = BlockedUsersCache(store, admin_service)
    admin_service.blocked_cache = blocked_cache

    if start_background:
        blocked_cache.start()
        admin_service.start_reminder_scheduler()
        from services.button_fallback_service import start_retry_scheduler

        start_retry_scheduler()

    flow_engine = FlowEngine(
        state_manager=state_manager,
        productos_service=productos_service,
        order_service=order_service,
        ayuda_service=ayuda_service,
        user_service=user_service,
        admin_service=admin_service,
    )

    try:
        productos_service.get_available_productos()
        productos_service.productos_literal_tokens()
        productos_service.format_productos()
    except Exception:
        logger.debug("Productos warm-up skipped", exc_info=True)

    _context = BotContext(
        flow_engine=flow_engine,
        user_service=user_service,
        admin_service=admin_service,
        blocked_cache=blocked_cache,
    )
    return _context


def reset_bot_context() -> None:
    """Clear singleton (tests only)."""
    global _context
    _context = None
