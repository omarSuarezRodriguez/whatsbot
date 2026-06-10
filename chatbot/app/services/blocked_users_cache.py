"""In-memory cache of blocked users with periodic refresh from Google Sheets."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Optional, Set

from app.config import BLOCKED_USERS_CACHE_TTL_SECONDS
from app.integrations.google_sheets import GoogleSheetsClient

if TYPE_CHECKING:
    from app.services.admin_service import AdminService

logger = logging.getLogger(__name__)


class BlockedUsersCache:
    def __init__(
        self,
        sheets: GoogleSheetsClient,
        admin_service: AdminService,
        ttl_seconds: int = BLOCKED_USERS_CACHE_TTL_SECONDS,
    ) -> None:
        self.sheets = sheets
        self.admin_service = admin_service
        self.ttl_seconds = max(5, ttl_seconds)
        self._blocked: Set[str] = set()
        self._lock = threading.Lock()
        self._started = False

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
            len(self._blocked),
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
        with self._lock:
            self._blocked = blocked
        logger.debug("Blocked users cache refreshed: %d user(s)", len(blocked))

    def is_blocked(self, wa_id: str) -> bool:
        normalized = self.admin_service._resolve_e164_digits(wa_id) or wa_id
        with self._lock:
            for blocked_id in self._blocked:
                if self.admin_service._phones_match(normalized, blocked_id):
                    return True
        return False

    def apply_local(self, wa_id: str, blocked: bool) -> None:
        normalized = self.admin_service._resolve_e164_digits(wa_id) or wa_id
        with self._lock:
            if blocked:
                self._blocked.add(normalized)
                return
            self._blocked = {
                bid
                for bid in self._blocked
                if not self.admin_service._phones_match(bid, normalized)
            }

    def count(self) -> int:
        with self._lock:
            return len(self._blocked)
