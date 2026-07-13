"""In-memory cache of blocked users with periodic refresh from the DB."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, FrozenSet, Optional, Set

from app.config import BLOCKED_USERS_CACHE_TTL_SECONDS

if TYPE_CHECKING:
    from app.integrations.db_store import DBStore
    from app.services.admin_service import AdminService

logger = logging.getLogger(__name__)


class BlockedUsersCache:
    def __init__(
        self,
        store: "DBStore",
        admin_service: "AdminService",
        ttl_seconds: int = BLOCKED_USERS_CACHE_TTL_SECONDS,
    ) -> None:
        self.sheets = store  # attr name kept for internal compatibility
        self.admin_service = admin_service
        self.ttl_seconds = max(5, ttl_seconds)
        # ponytail: frozenset of E.164-normalized wa_ids; O(1) lookup.
        # ceiling: normalize_wa_id_e164 must be deterministic (same input → same output).
        # upgrade: if normalization becomes context-dependent, key by (business_id, wa_id).
        self._blocked_normalized: FrozenSet[str] = frozenset()
        self._lock = threading.Lock()
        self._started = False

    def _normalize_set(self, raw: Set[str]) -> FrozenSet[str]:
        norm = self.admin_service.normalize_wa_id_e164
        return frozenset(norm(bid) or bid for bid in raw)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.refresh()
        thread = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
            name="blocked-users-cache",
        )
        thread.start()
        logger.info(
            "Blocked users cache started (TTL=%ds, %d blocked)",
            self.ttl_seconds,
            len(self._blocked_normalized),
        )

    def _refresh_loop(self) -> None:
        while True:
            time.sleep(self.ttl_seconds)
            try:
                self.refresh()
            except Exception:
                logger.exception("Blocked users cache refresh failed (non-fatal)")

    def refresh(self) -> None:
        self.sheets.refresh_users_cache()
        blocked = self.sheets.get_blocked_wa_ids()
        normalized = self._normalize_set(blocked)
        with self._lock:
            self._blocked_normalized = normalized
        logger.debug("Blocked users cache refreshed: %d user(s)", len(normalized))

    def is_blocked(self, wa_id: str) -> bool:
        normalized = self.admin_service.normalize_wa_id_e164(wa_id) or wa_id
        with self._lock:
            blocked = self._blocked_normalized
        return normalized in blocked

    def apply_local(self, wa_id: str, blocked: bool) -> None:
        normalized = self.admin_service.normalize_wa_id_e164(wa_id) or wa_id
        with self._lock:
            current = self._blocked_normalized
            if blocked:
                self._blocked_normalized = current | {normalized}
            else:
                self._blocked_normalized = current - {normalized}

    def count(self) -> int:
        with self._lock:
            return len(self._blocked_normalized)
