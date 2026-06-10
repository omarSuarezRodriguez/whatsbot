"""Google Sheets integration with graceful fallback demo data."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import (
    DATA_DIR,
    MENU_CACHE_TTL_SECONDS,
    ORDERS_CACHE_TTL_SECONDS,
    SHEETS_FULL_REFRESH_INTERVAL_SECONDS,
    SHEETS_INCREMENTAL_BATCH_SIZE,
    SHEETS_INCREMENTAL_THRESHOLD,
)

logger = logging.getLogger(__name__)

_SYNC_POLL_SECONDS = max(5, min(MENU_CACHE_TTL_SECONDS, ORDERS_CACHE_TTL_SECONDS))
_MENU_LOCAL_PATH = DATA_DIR / "menu_cache.json"
_USERS_LOCAL_PATH = DATA_DIR / "users_cache.json"
_ORDERS_LOCAL_PATH = DATA_DIR / "orders_cache.json"
_RESERVATIONS_LOCAL_PATH = DATA_DIR / "reservations_cache.json"

DEMO_MENU = [
    {
        "id": "1",
        "nombre": "Pizza Hawaiana",
        "precio": 12.5,
        "categoria": "Pizzas",
        "disponible": True,
    },
    {
        "id": "2",
        "nombre": "Pizza Margarita",
        "precio": 11.0,
        "categoria": "Pizzas",
        "disponible": True,
    },
    {
        "id": "3",
        "nombre": "Hamburguesa Clásica",
        "precio": 9.5,
        "categoria": "Hamburguesas",
        "disponible": True,
    },
    {
        "id": "4",
        "nombre": "Coca Cola",
        "precio": 2.5,
        "categoria": "Bebidas",
        "disponible": True,
    },
    {
        "id": "5",
        "nombre": "Agua Mineral",
        "precio": 1.5,
        "categoria": "Bebidas",
        "disponible": True,
    },
    {
        "id": "6",
        "nombre": "Ensalada César",
        "precio": 8.0,
        "categoria": "Ensaladas",
        "disponible": True,
    },
]

SHEET_HEADERS = {
    "MENU": ["id", "nombre", "precio", "categoria", "disponible"],
    "USERS": [
        "wa_id",
        "name",
        "address",
        "last_order_date",
        "last_order_json",
        "last_seen",
        "blocked",
        "updated_at",
    ],
    "ORDERS": [
        "order_id",
        "wa_id",
        "items",
        "total",
        "status",
        "timestamp",
        "customer_name",
        "address",
        "delivery_type",
    ],
    "RESERVATIONS": [
        "reservation_id",
        "wa_id",
        "personas",
        "fecha",
        "hora",
        "status",
    ],
}


class GoogleSheetsClient:
    def __init__(self, credentials_path: str, spreadsheet_id: str) -> None:
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self._client = None
        self._spreadsheet = None
        self._connected = False
        self._demo_users: Dict[str, Dict[str, Any]] = {}
        self._demo_orders: List[Dict[str, Any]] = []
        self._cache_lock = threading.Lock()
        self._menu_cache: Optional[List[Dict[str, Any]]] = None
        self._menu_refresh_started = False
        self._users_cache: Dict[str, Dict[str, Any]] = {}
        self._user_row_index: Dict[str, int] = {}
        self._dirty_users: set[str] = set()
        self._orders_local: Dict[str, Dict[str, Any]] = {}
        self._order_row_index: Dict[str, int] = {}
        self._dirty_new_orders: set[str] = set()
        self._dirty_order_status: Dict[str, str] = {}
        self._reservations_local: Dict[str, Dict[str, Any]] = {}
        self._reservation_row_index: Dict[str, int] = {}
        self._dirty_reservations: set[str] = set()
        self._worksheets: Dict[str, Any] = {}
        self._cache_warmed = False
        self._last_menu_refresh = 0.0
        self._last_orders_refresh = 0.0
        self._last_full_users_refresh = 0.0
        self._last_full_orders_refresh = 0.0
        self._last_full_reservations_refresh = 0.0
        self._load_local_menu()
        self._load_local_users()
        self._load_local_orders()
        self._load_local_reservations()
        self._connect()
        self.warm_up_cache()
        if self._connected:
            self._start_background_sync_loop()

    def _connect(self) -> None:
        if not self.spreadsheet_id:
            logger.warning("GOOGLE_SPREADSHEET_ID not set. Using demo data.")
            return
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            json_blob = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
            if json_blob:
                credentials = Credentials.from_service_account_info(
                    json.loads(json_blob),
                    scopes=scopes,
                )
            else:
                credentials = Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=scopes,
                )
            self._client = gspread.authorize(credentials)
            self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)
            self._connected = True
            self._ensure_worksheets()
        except Exception as exc:
            logger.warning("Google Sheets unavailable (%s). Using demo data.", exc)
            self._connected = False

    def warm_up_cache(self) -> None:
        started = time.perf_counter()
        try:
            if self._connected:
                if not _MENU_LOCAL_PATH.exists() or not self._menu_cache:
                    self._refresh_menu_from_sheets()
                if not _USERS_LOCAL_PATH.exists() or not self._users_cache:
                    self._refresh_users_from_sheets()
                if not _ORDERS_LOCAL_PATH.exists() or not self._orders_local:
                    self._refresh_orders_from_sheets()
            with self._cache_lock:
                menu_count = len(self._menu_cache or DEMO_MENU)
                user_count = len(self._users_cache)
                order_count = len(self._orders_local)
            self._cache_warmed = True
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Google Sheets cache warm-up: %d menu (local), %d users (local), "
                "%d orders (local) in %.1f ms",
                menu_count,
                user_count,
                order_count,
                elapsed_ms,
            )
        except Exception as exc:
            logger.warning("Google Sheets cache warm-up failed (%s).", exc)

    def cache_status(self) -> Dict[str, Any]:
        with self._cache_lock:
            menu = self._menu_cache
            blocked_count = sum(
                1
                for user in self._users_cache.values()
                if self._parse_bool(user.get("blocked", False))
            )
            return {
                "ready": self._cache_warmed,
                "sheets_connected": self._connected,
                "menu_items": len(menu) if menu else 0,
                "users": len(self._users_cache),
                "blocked_users": blocked_count,
                "orders": len(self._orders_local),
            }

    def _load_local_users(self) -> None:
        if not _USERS_LOCAL_PATH.exists():
            return
        try:
            with _USERS_LOCAL_PATH.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return
            users = payload.get("users", {})
            row_index = payload.get("row_index", {})
            dirty = payload.get("dirty", [])
            if isinstance(users, dict):
                with self._cache_lock:
                    self._users_cache = users
                    self._user_row_index = {
                        str(k): int(v) for k, v in row_index.items()
                    }
                    self._dirty_users = {str(w) for w in dirty}
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            logger.warning("Local users cache unreadable (%s).", exc)

    def _save_local_users(self) -> None:
        with self._cache_lock:
            payload = {
                "users": self._users_cache,
                "row_index": self._user_row_index,
                "dirty": sorted(self._dirty_users),
            }
        _USERS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _USERS_LOCAL_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    def _load_local_menu(self) -> None:
        if not _MENU_LOCAL_PATH.exists():
            with self._cache_lock:
                self._menu_cache = list(DEMO_MENU)
            return
        try:
            with _MENU_LOCAL_PATH.open("r", encoding="utf-8") as handle:
                menu = json.load(handle)
            if isinstance(menu, list) and menu:
                with self._cache_lock:
                    self._menu_cache = menu
                return
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Local menu cache unreadable (%s). Using demo menu.", exc)
        with self._cache_lock:
            self._menu_cache = list(DEMO_MENU)

    def _save_local_menu(self, menu: List[Dict[str, Any]]) -> None:
        _MENU_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _MENU_LOCAL_PATH.open("w", encoding="utf-8") as handle:
            json.dump(menu, handle, ensure_ascii=False, separators=(",", ":"))

    def _refresh_menu_from_sheets(self) -> None:
        if not self._connected:
            return
        try:
            menu = self._fetch_menu_rows()
            if not menu:
                return
            with self._cache_lock:
                self._menu_cache = menu
            self._save_local_menu(menu)
            logger.info("Menu local cache refreshed: %d items", len(menu))
        except Exception as exc:
            logger.warning("Background menu refresh failed (%s).", exc)

    def _start_background_sync_loop(self) -> None:
        if self._menu_refresh_started:
            return
        self._menu_refresh_started = True

        def _loop() -> None:
            while True:
                self._push_dirty_users_to_sheets()
                self._push_dirty_orders_to_sheets()
                self._push_dirty_reservations_to_sheets()
                now = time.monotonic()
                if now - self._last_menu_refresh >= MENU_CACHE_TTL_SECONDS:
                    self._refresh_menu_from_sheets()
                    self._refresh_users_from_sheets()
                    self._last_menu_refresh = now
                if now - self._last_orders_refresh >= ORDERS_CACHE_TTL_SECONDS:
                    self._refresh_orders_from_sheets()
                    self._refresh_reservations_from_sheets()
                    self._last_orders_refresh = now
                time.sleep(_SYNC_POLL_SECONDS)

        thread = threading.Thread(
            target=_loop,
            daemon=True,
            name="sheets-background-sync",
        )
        thread.start()
        logger.info(
            "Background sync poll every %ds (menu/users TTL=%ds, orders TTL=%ds)",
            _SYNC_POLL_SECONDS,
            MENU_CACHE_TTL_SECONDS,
            ORDERS_CACHE_TTL_SECONDS,
        )

    @staticmethod
    def _col_end(num_cols: int) -> str:
        return chr(ord("A") + num_cols - 1)

    @staticmethod
    def _row_tail(row_index: Dict[str, int]) -> int:
        return max(row_index.values(), default=1)

    @staticmethod
    def _should_use_full_refresh(
        row_count: int,
        last_full_refresh: float,
    ) -> bool:
        if row_count < SHEETS_INCREMENTAL_THRESHOLD:
            return True
        if last_full_refresh == 0.0:
            return True
        if time.monotonic() - last_full_refresh >= SHEETS_FULL_REFRESH_INTERVAL_SECONDS:
            return True
        return False

    def _sheet_last_row(self, sheet) -> int:
        try:
            values = sheet.col_values(1)
            return len(values) if values else 1
        except Exception:
            return 1

    def _fetch_rows_range(
        self,
        sheet,
        headers: List[str],
        start_row: int,
        max_rows: int = SHEETS_INCREMENTAL_BATCH_SIZE,
    ) -> List[tuple[int, List[Any]]]:
        end_row = start_row + max_rows - 1
        col_end = self._col_end(len(headers))
        try:
            values = sheet.get(f"A{start_row}:{col_end}{end_row}") or []
        except Exception:
            return []
        rows: List[tuple[int, List[Any]]] = []
        for idx, raw in enumerate(values, start=start_row):
            if not raw or not str(raw[0]).strip():
                continue
            rows.append((idx, raw))
        return rows

    def _has_rows_beyond(self, sheet, tail_row: int) -> bool:
        try:
            value = sheet.acell(f"A{tail_row + 1}").value
            return value is not None and str(value).strip() != ""
        except Exception:
            return True

    def _merge_fetched_users(
        self,
        fetched_users: Dict[str, Dict[str, Any]],
        fetched_rows: Dict[str, int],
    ) -> None:
        if not fetched_users and not fetched_rows:
            return
        with self._cache_lock:
            dirty = set(self._dirty_users)
            for wa_id, user in fetched_users.items():
                if wa_id not in dirty:
                    self._users_cache[wa_id] = user
            for wa_id, idx in fetched_rows.items():
                if wa_id not in dirty:
                    self._user_row_index[wa_id] = idx
        self._save_local_users()

    def _merge_fetched_orders(
        self,
        fetched: Dict[str, Dict[str, Any]],
        fetched_rows: Dict[str, int],
    ) -> None:
        if not fetched and not fetched_rows:
            return
        with self._cache_lock:
            pending = set(self._dirty_new_orders) | set(self._dirty_order_status)
            for order_id, order in fetched.items():
                if order_id not in pending:
                    self._orders_local[order_id] = order
            for order_id, idx in fetched_rows.items():
                if order_id not in pending:
                    self._order_row_index[order_id] = idx
        self._save_local_orders()

    def _merge_fetched_reservations(
        self,
        fetched: Dict[str, Dict[str, Any]],
        fetched_rows: Optional[Dict[str, int]] = None,
    ) -> None:
        if not fetched and not fetched_rows:
            return
        with self._cache_lock:
            dirty = set(self._dirty_reservations)
            for res_id, reservation in fetched.items():
                if res_id not in dirty:
                    self._reservations_local[res_id] = reservation
            if fetched_rows:
                for res_id, idx in fetched_rows.items():
                    if res_id not in dirty:
                        self._reservation_row_index[res_id] = idx
        self._save_local_reservations()

    def _ensure_worksheets(self) -> None:
        if not self._spreadsheet:
            return
        existing = {ws.title.upper(): ws for ws in self._spreadsheet.worksheets()}
        for sheet_name, headers in SHEET_HEADERS.items():
            if sheet_name not in existing:
                worksheet = self._spreadsheet.add_worksheet(
                    title=sheet_name,
                    rows=1000,
                    cols=len(headers),
                )
                worksheet.append_row(headers)
            else:
                worksheet = existing[sheet_name]
                current = worksheet.row_values(1)
                if not current:
                    worksheet.append_row(headers)
                elif len(current) < len(headers):
                    missing = headers[len(current) :]
                    cols_needed = len(headers) - worksheet.col_count
                    if cols_needed > 0:
                        worksheet.add_cols(cols_needed)
                    start_col = self._col_end(len(current) + 1)
                    end_col = self._col_end(len(headers))
                    worksheet.update(f"{start_col}1:{end_col}1", [missing])
            self._worksheets[sheet_name] = worksheet

    def _get_sheet(self, name: str):
        if not self._connected or not self._spreadsheet:
            return None
        if name in self._worksheets:
            return self._worksheets[name]
        worksheet = self._spreadsheet.worksheet(name)
        self._worksheets[name] = worksheet
        return worksheet

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "y"}

    def _order_from_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = json.loads(row.get("items") or "[]")
        except json.JSONDecodeError:
            items = []
        order_id = str(row.get("order_id", "")).upper()
        return {
            "order_id": order_id,
            "wa_id": str(row.get("wa_id", "")),
            "items": items,
            "total": float(row.get("total", 0) or 0),
            "status": str(row.get("status", "pending")),
            "timestamp": str(row.get("timestamp", "")),
            "customer_name": str(row.get("customer_name", "")),
            "address": str(row.get("address", "")),
            "delivery_type": str(row.get("delivery_type", "")),
        }

    def _load_local_orders(self) -> None:
        if not _ORDERS_LOCAL_PATH.exists():
            return
        try:
            with _ORDERS_LOCAL_PATH.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return
            orders = payload.get("orders", {})
            row_index = payload.get("row_index", {})
            dirty_new = payload.get("dirty_new", [])
            dirty_status = payload.get("dirty_status", {})
            if isinstance(orders, dict):
                with self._cache_lock:
                    self._orders_local = {
                        str(k).upper(): v for k, v in orders.items()
                    }
                    self._order_row_index = {
                        str(k).upper(): int(v) for k, v in row_index.items()
                    }
                    self._dirty_new_orders = {str(o).upper() for o in dirty_new}
                    self._dirty_order_status = {
                        str(k).upper(): str(v)
                        for k, v in dirty_status.items()
                    }
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            logger.warning("Local orders cache unreadable (%s).", exc)

    def _save_local_orders(self) -> None:
        with self._cache_lock:
            payload = {
                "orders": self._orders_local,
                "row_index": self._order_row_index,
                "dirty_new": sorted(self._dirty_new_orders),
                "dirty_status": self._dirty_order_status,
            }
        _ORDERS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _ORDERS_LOCAL_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    def _load_local_reservations(self) -> None:
        if not _RESERVATIONS_LOCAL_PATH.exists():
            return
        try:
            with _RESERVATIONS_LOCAL_PATH.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return
            reservations = payload.get("reservations", {})
            dirty = payload.get("dirty", [])
            if isinstance(reservations, dict):
                with self._cache_lock:
                    self._reservations_local = reservations
                    self._dirty_reservations = {str(r) for r in dirty}
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            logger.warning("Local reservations cache unreadable (%s).", exc)

    def _save_local_reservations(self) -> None:
        with self._cache_lock:
            payload = {
                "reservations": self._reservations_local,
                "dirty": sorted(self._dirty_reservations),
            }
        _RESERVATIONS_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _RESERVATIONS_LOCAL_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    def _fetch_orders_from_sheets(
        self,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("ORDERS")
        orders: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet:
            return orders, row_index

        headers = SHEET_HEADERS["ORDERS"]
        for idx, raw in enumerate(sheet.get_all_values()[1:], start=2):
            if not raw or not str(raw[0]).strip():
                continue
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            order_id = str(row.get("order_id", "")).strip().upper()
            if order_id:
                orders[order_id] = self._order_from_row(row)
                row_index[order_id] = idx
        return orders, row_index

    def _fetch_orders_incremental(
        self,
        tail_row: int,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("ORDERS")
        orders: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet or not self._has_rows_beyond(sheet, tail_row):
            return orders, row_index

        headers = SHEET_HEADERS["ORDERS"]
        for idx, raw in self._fetch_rows_range(sheet, headers, tail_row + 1):
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            order_id = str(row.get("order_id", "")).strip().upper()
            if order_id:
                orders[order_id] = self._order_from_row(row)
                row_index[order_id] = idx
        return orders, row_index

    def _refresh_orders_from_sheets(self) -> None:
        if not self._connected:
            return
        try:
            with self._cache_lock:
                row_count = len(self._orders_local)
            use_full = self._should_use_full_refresh(
                row_count,
                self._last_full_orders_refresh,
            )
            if use_full:
                fetched, fetched_rows = self._fetch_orders_from_sheets()
                mode = "full"
                self._last_full_orders_refresh = time.monotonic()
            else:
                with self._cache_lock:
                    tail = self._row_tail(self._order_row_index)
                fetched, fetched_rows = self._fetch_orders_incremental(tail)
                mode = "incremental"
                if not fetched and not fetched_rows:
                    return
            self._merge_fetched_orders(fetched, fetched_rows)
            logger.info(
                "Orders local cache refreshed (%s): %d orders",
                mode,
                len(fetched),
            )
        except Exception as exc:
            logger.warning("Background orders refresh failed (%s).", exc)

    def _create_order_on_sheets(self, order_id: str) -> bool:
        sheet = self._get_sheet("ORDERS")
        if not sheet:
            return False
        with self._cache_lock:
            order = dict(self._orders_local.get(order_id, {}))
        if not order:
            return False

        items = order.get("items", [])
        sheet.append_row(
            [
                order_id,
                order.get("wa_id", ""),
                json.dumps(items, ensure_ascii=False),
                order.get("total", 0),
                order.get("status", "pending"),
                order.get("timestamp", ""),
                order.get("customer_name", ""),
                order.get("address", ""),
                order.get("delivery_type", ""),
            ]
        )
        new_row = self._sheet_last_row(sheet)
        with self._cache_lock:
            self._order_row_index[order_id] = new_row
        return True

    def _update_order_status_on_sheets(self, order_id: str, status: str) -> bool:
        sheet = self._get_sheet("ORDERS")
        if not sheet:
            return False
        with self._cache_lock:
            row_idx = self._order_row_index.get(order_id)
        if not row_idx:
            try:
                cell = sheet.find(order_id, in_column=1)
            except Exception:
                return False
            if not cell:
                return False
            row_idx = cell.row
            with self._cache_lock:
                self._order_row_index[order_id] = row_idx
        sheet.update(f"E{row_idx}", [[status]])
        return True

    def _push_dirty_orders_to_sheets(self) -> None:
        if not self._connected:
            return
        with self._cache_lock:
            new_orders = list(self._dirty_new_orders)
            status_updates = dict(self._dirty_order_status)

        synced_new: List[str] = []
        for order_id in new_orders:
            try:
                if self._create_order_on_sheets(order_id):
                    synced_new.append(order_id)
            except Exception as exc:
                logger.warning("Background order create failed for %s (%s).", order_id, exc)

        synced_status: List[str] = []
        for order_id, status in status_updates.items():
            try:
                if self._update_order_status_on_sheets(order_id, status):
                    synced_status.append(order_id)
            except Exception as exc:
                logger.warning(
                    "Background order status sync failed for %s (%s).", order_id, exc
                )

        if synced_new or synced_status:
            with self._cache_lock:
                for order_id in synced_new:
                    self._dirty_new_orders.discard(order_id)
                for order_id in synced_status:
                    self._dirty_order_status.pop(order_id, None)
            self._save_local_orders()
            logger.info(
                "Orders synced to Sheets: %d new, %d status",
                len(synced_new),
                len(synced_status),
            )

    def _fetch_reservations_from_sheets(
        self,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("RESERVATIONS")
        reservations: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet:
            return reservations, row_index

        headers = SHEET_HEADERS["RESERVATIONS"]
        for idx, raw in enumerate(sheet.get_all_values()[1:], start=2):
            if not raw or not str(raw[0]).strip():
                continue
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            reservation_id = str(row.get("reservation_id", "")).strip()
            if reservation_id:
                reservations[reservation_id] = {
                    "reservation_id": reservation_id,
                    "wa_id": str(row.get("wa_id", "")),
                    "personas": int(row.get("personas", 0) or 0),
                    "fecha": str(row.get("fecha", "")),
                    "hora": str(row.get("hora", "")),
                    "status": str(row.get("status", "confirmed")),
                }
                row_index[reservation_id] = idx
        return reservations, row_index

    def _fetch_reservations_incremental(
        self,
        tail_row: int,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("RESERVATIONS")
        reservations: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet or not self._has_rows_beyond(sheet, tail_row):
            return reservations, row_index

        headers = SHEET_HEADERS["RESERVATIONS"]
        for idx, raw in self._fetch_rows_range(sheet, headers, tail_row + 1):
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            reservation_id = str(row.get("reservation_id", "")).strip()
            if reservation_id:
                reservations[reservation_id] = {
                    "reservation_id": reservation_id,
                    "wa_id": str(row.get("wa_id", "")),
                    "personas": int(row.get("personas", 0) or 0),
                    "fecha": str(row.get("fecha", "")),
                    "hora": str(row.get("hora", "")),
                    "status": str(row.get("status", "confirmed")),
                }
                row_index[reservation_id] = idx
        return reservations, row_index

    def _refresh_reservations_from_sheets(self) -> None:
        if not self._connected:
            return
        try:
            with self._cache_lock:
                row_count = len(self._reservations_local)
            use_full = self._should_use_full_refresh(
                row_count,
                self._last_full_reservations_refresh,
            )
            if use_full:
                fetched, fetched_rows = self._fetch_reservations_from_sheets()
                mode = "full"
                self._last_full_reservations_refresh = time.monotonic()
            else:
                with self._cache_lock:
                    tail = self._row_tail(self._reservation_row_index)
                fetched, fetched_rows = self._fetch_reservations_incremental(tail)
                mode = "incremental"
                if not fetched and not fetched_rows:
                    return
            self._merge_fetched_reservations(fetched, fetched_rows)
            logger.info(
                "Reservations local cache refreshed (%s): %d",
                mode,
                len(fetched),
            )
        except Exception as exc:
            logger.warning("Background reservations refresh failed (%s).", exc)

    def _create_reservation_on_sheets(self, reservation_id: str) -> bool:
        sheet = self._get_sheet("RESERVATIONS")
        if not sheet:
            return False
        with self._cache_lock:
            reservation = dict(self._reservations_local.get(reservation_id, {}))
        if not reservation:
            return False
        sheet.append_row(
            [
                reservation_id,
                reservation.get("wa_id", ""),
                reservation.get("personas", 0),
                reservation.get("fecha", ""),
                reservation.get("hora", ""),
                reservation.get("status", "confirmed"),
            ]
        )
        return True

    def _push_dirty_reservations_to_sheets(self) -> None:
        if not self._connected:
            return
        with self._cache_lock:
            pending = list(self._dirty_reservations)
        if not pending:
            return

        synced: List[str] = []
        for reservation_id in pending:
            try:
                if self._create_reservation_on_sheets(reservation_id):
                    synced.append(reservation_id)
            except Exception as exc:
                logger.warning(
                    "Background reservation sync failed for %s (%s).",
                    reservation_id,
                    exc,
                )

        if synced:
            with self._cache_lock:
                for reservation_id in synced:
                    self._dirty_reservations.discard(reservation_id)
            self._save_local_reservations()
            logger.info("Reservations synced to Sheets: %d", len(synced))

    def _fetch_menu_rows(self) -> List[Dict[str, Any]]:
        sheet = self._get_sheet("MENU")
        if not sheet:
            return []

        menu: List[Dict[str, Any]] = []
        for row in sheet.get_all_records():
            if not row.get("nombre"):
                continue
            menu.append(
                {
                    "id": str(row.get("id", "")),
                    "nombre": str(row.get("nombre", "")).strip(),
                    "precio": float(row.get("precio", 0) or 0),
                    "categoria": str(row.get("categoria", "")).strip(),
                    "disponible": self._parse_bool(row.get("disponible", True)),
                }
            )
        return menu

    def _user_from_row(self, wa_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
        last_order = row.get("last_order_json") or ""
        try:
            last_order_items = json.loads(last_order) if last_order else []
        except json.JSONDecodeError:
            last_order_items = []
        return {
            "wa_id": wa_id,
            "name": str(row.get("name", "")).strip(),
            "address": str(row.get("address", "")).strip(),
            "last_order_date": str(row.get("last_order_date", "")).strip(),
            "last_order_items": last_order_items,
            "last_seen": str(row.get("last_seen", "")).strip(),
            "blocked": self._parse_bool(row.get("blocked", False)),
            "updated_at": str(row.get("updated_at", "")).strip(),
        }

    def _fetch_users_from_sheets(self) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("USERS")
        users: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet:
            return users, row_index

        headers = SHEET_HEADERS["USERS"]
        for idx, raw in enumerate(sheet.get_all_values()[1:], start=2):
            if not raw or not str(raw[0]).strip():
                continue
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            wa_id = str(row.get("wa_id", "")).strip()
            if wa_id:
                users[wa_id] = self._user_from_row(wa_id, row)
                row_index[wa_id] = idx
        return users, row_index

    def _fetch_users_incremental(
        self,
        tail_row: int,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        sheet = self._get_sheet("USERS")
        users: Dict[str, Dict[str, Any]] = {}
        row_index: Dict[str, int] = {}
        if not sheet or not self._has_rows_beyond(sheet, tail_row):
            return users, row_index

        headers = SHEET_HEADERS["USERS"]
        for idx, raw in self._fetch_rows_range(sheet, headers, tail_row + 1):
            padded = raw + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, padded[: len(headers)]))
            wa_id = str(row.get("wa_id", "")).strip()
            if wa_id:
                users[wa_id] = self._user_from_row(wa_id, row)
                row_index[wa_id] = idx
        return users, row_index

    def _refresh_users_from_sheets(self) -> None:
        if not self._connected:
            return
        try:
            with self._cache_lock:
                row_count = len(self._users_cache)
            use_full = self._should_use_full_refresh(
                row_count,
                self._last_full_users_refresh,
            )
            if use_full:
                fetched_users, fetched_rows = self._fetch_users_from_sheets()
                mode = "full"
                self._last_full_users_refresh = time.monotonic()
            else:
                with self._cache_lock:
                    tail = self._row_tail(self._user_row_index)
                fetched_users, fetched_rows = self._fetch_users_incremental(tail)
                mode = "incremental"
                if not fetched_users and not fetched_rows:
                    return
            self._merge_fetched_users(fetched_users, fetched_rows)
            logger.info(
                "Users local cache refreshed (%s): %d users",
                mode,
                len(fetched_users),
            )
        except Exception as exc:
            logger.warning("Background users refresh failed (%s).", exc)

    def _resolve_user_row(self, sheet, wa_id: str) -> Optional[int]:
        with self._cache_lock:
            row_idx = self._user_row_index.get(wa_id)
        if row_idx:
            return row_idx
        try:
            cell = sheet.find(wa_id, in_column=1)
        except Exception:
            return None
        if not cell:
            return None
        with self._cache_lock:
            self._user_row_index[wa_id] = cell.row
        return cell.row

    def _upsert_user_to_sheets(self, wa_id: str) -> bool:
        sheet = self._get_sheet("USERS")
        if not sheet:
            return False

        with self._cache_lock:
            user = dict(self._users_cache.get(wa_id, {}))
        if not user:
            return False

        merged_name = str(user.get("name", ""))
        merged_address = str(user.get("address", ""))
        merged_items = user.get("last_order_items") or []
        last_order_date = str(user.get("last_order_date", ""))
        now = str(user.get("last_seen", "")) or datetime.utcnow().isoformat()
        payload_items = (
            json.dumps(merged_items, ensure_ascii=False) if merged_items else ""
        )

        blocked_val = (
            "true" if self._parse_bool(user.get("blocked", False)) else "false"
        )
        updated_at = str(user.get("updated_at", ""))

        row_idx = self._resolve_user_row(sheet, wa_id)
        if row_idx:
            sheet.update(
                f"B{row_idx}:H{row_idx}",
                [
                    [
                        merged_name,
                        merged_address,
                        last_order_date,
                        payload_items,
                        now,
                        blocked_val,
                        updated_at,
                    ]
                ],
            )
            return True

        sheet.append_row(
            [
                wa_id,
                merged_name,
                merged_address,
                last_order_date,
                payload_items,
                now,
                blocked_val,
                updated_at,
            ]
        )
        new_row = self._sheet_last_row(sheet)
        with self._cache_lock:
            self._user_row_index[wa_id] = new_row
        return True

    def _push_dirty_users_to_sheets(self) -> None:
        if not self._connected:
            return
        with self._cache_lock:
            pending = list(self._dirty_users)
        if not pending:
            return

        synced: List[str] = []
        for wa_id in pending:
            try:
                if self._upsert_user_to_sheets(wa_id):
                    synced.append(wa_id)
            except Exception as exc:
                logger.warning("Background user sync failed for %s (%s).", wa_id, exc)

        if synced:
            with self._cache_lock:
                for wa_id in synced:
                    self._dirty_users.discard(wa_id)
            self._save_local_users()
            logger.info("Users synced to Sheets: %d", len(synced))

    def create_order(
        self,
        wa_id: str,
        items: List[Dict[str, Any]],
        total: float,
        status: str = "pending",
        customer_name: str = "",
        address: str = "",
        delivery_type: str = "",
    ) -> str:
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "order_id": order_id,
            "wa_id": wa_id,
            "items": items,
            "total": total,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "customer_name": customer_name,
            "address": address,
            "delivery_type": delivery_type,
        }

        if not self._connected:
            self._demo_orders.append(payload)
            self.upsert_user(
                wa_id=wa_id,
                name=customer_name,
                address=address,
                last_order_items=items,
            )
            return order_id

        with self._cache_lock:
            self._orders_local[order_id] = payload
            self._dirty_new_orders.add(order_id)
        self._save_local_orders()
        self.upsert_user(
            wa_id=wa_id,
            name=customer_name,
            address=address,
            last_order_items=items,
        )
        return order_id

    def get_menu(self) -> List[Dict[str, Any]]:
        with self._cache_lock:
            if self._menu_cache is not None:
                return list(self._menu_cache)
        return list(DEMO_MENU)

    def get_user(self, wa_id: str) -> Dict[str, Any]:
        with self._cache_lock:
            if wa_id in self._users_cache:
                return dict(self._users_cache[wa_id])
        if not self._connected:
            return dict(self._demo_users.get(wa_id, {}))
        return {}

    def refresh_users_cache(self) -> None:
        self._refresh_users_from_sheets()

    def get_blocked_wa_ids(self) -> set[str]:
        blocked: set[str] = set()
        with self._cache_lock:
            for wa_id, user in self._users_cache.items():
                if self._parse_bool(user.get("blocked", False)):
                    blocked.add(wa_id)
        return blocked

    def set_user_blocked(self, wa_id: str, blocked: bool) -> bool:
        now = datetime.utcnow().isoformat()
        with self._cache_lock:
            existing = dict(self._users_cache.get(wa_id, {}))
            if not existing and wa_id in self._demo_users:
                existing = dict(self._demo_users[wa_id])

        user_payload = {
            "wa_id": wa_id,
            "name": str(existing.get("name", "")),
            "address": str(existing.get("address", "")),
            "last_order_date": str(existing.get("last_order_date", "")),
            "last_order_items": existing.get("last_order_items") or [],
            "last_seen": str(existing.get("last_seen", "")) or now,
            "blocked": blocked,
            "updated_at": now,
        }

        with self._cache_lock:
            self._users_cache[wa_id] = user_payload

        if not self._connected:
            self._demo_users[wa_id] = user_payload
            self._save_local_users()
            return True

        try:
            sheet = self._get_sheet("USERS")
            if not sheet:
                return False
            blocked_val = "true" if blocked else "false"
            row_idx = self._resolve_user_row(sheet, wa_id)
            if row_idx:
                sheet.update(f"G{row_idx}:H{row_idx}", [[blocked_val, now]])
            else:
                sheet.append_row(
                    [
                        wa_id,
                        user_payload["name"],
                        user_payload["address"],
                        user_payload["last_order_date"],
                        "",
                        user_payload["last_seen"],
                        blocked_val,
                        now,
                    ]
                )
                new_row = self._sheet_last_row(sheet)
                with self._cache_lock:
                    self._user_row_index[wa_id] = new_row
            self._save_local_users()
            return True
        except Exception as exc:
            logger.error("Failed to set blocked=%s for %s: %s", blocked, wa_id, exc)
            return False

    def upsert_user(
        self,
        wa_id: str,
        name: str = "",
        address: str = "",
        last_order_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self._cache_lock:
            existing = dict(self._users_cache.get(wa_id, {}))
        merged_name = name or existing.get("name", "")
        merged_address = address or existing.get("address", "")
        merged_items = last_order_items if last_order_items is not None else existing.get(
            "last_order_items", []
        )
        last_order_date = existing.get("last_order_date", "")
        if last_order_items is not None:
            last_order_date = now

        user_payload = {
            "wa_id": wa_id,
            "name": merged_name,
            "address": merged_address,
            "last_order_date": last_order_date,
            "last_order_items": merged_items,
            "last_seen": now,
            "blocked": existing.get("blocked", False),
            "updated_at": existing.get("updated_at", ""),
        }

        if not self._connected:
            self._demo_users[wa_id] = user_payload
            return

        touch_only = bool(existing) and (
            str(existing.get("name", "")) == merged_name
            and str(existing.get("address", "")) == merged_address
            and existing.get("last_order_items", []) == merged_items
            and str(existing.get("last_order_date", "")) == last_order_date
        )

        with self._cache_lock:
            self._users_cache[wa_id] = user_payload
            self._dirty_users.add(wa_id)
        if not touch_only:
            self._save_local_users()

    def get_last_order(self, wa_id: str) -> Optional[Dict[str, Any]]:
        user = self.get_user(wa_id)
        items = user.get("last_order_items") or []
        if not items:
            return None
        return {
            "wa_id": wa_id,
            "items": items,
            "customer_name": user.get("name", ""),
            "address": user.get("address", ""),
            "last_order_date": user.get("last_order_date", ""),
        }

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        order_id = order_id.upper()
        with self._cache_lock:
            if order_id in self._orders_local:
                return dict(self._orders_local[order_id])
        for order in self._demo_orders:
            if str(order.get("order_id", "")).upper() == order_id:
                return dict(order)
        return None

    def update_order_status(self, order_id: str, status: str) -> bool:
        order_id = order_id.upper()
        for order in self._demo_orders:
            if str(order.get("order_id", "")).upper() == order_id:
                order["status"] = status
                return True

        with self._cache_lock:
            if order_id not in self._orders_local:
                return False
            self._orders_local[order_id]["status"] = status
            if order_id not in self._dirty_new_orders:
                self._dirty_order_status[order_id] = status
        self._save_local_orders()
        return True

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        pending: List[Dict[str, Any]] = []
        for order in self._demo_orders:
            if order.get("status") == "pending":
                pending.append(dict(order))

        with self._cache_lock:
            for order in self._orders_local.values():
                if str(order.get("status", "")).lower() == "pending":
                    pending.append(dict(order))
        return pending

    def create_reservation(
        self,
        wa_id: str,
        personas: int,
        fecha: str,
        hora: str,
        status: str = "confirmed",
    ) -> str:
        reservation_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "reservation_id": reservation_id,
            "wa_id": wa_id,
            "personas": personas,
            "fecha": fecha,
            "hora": hora,
            "status": status,
        }

        if not self._connected:
            return reservation_id

        with self._cache_lock:
            self._reservations_local[reservation_id] = payload
            self._dirty_reservations.add(reservation_id)
        self._save_local_reservations()
        return reservation_id

    def replace_menu_mirror(self, items: List[Dict[str, Any]]) -> bool:
        """
        Overwrite MENU worksheet from PostgreSQL mirror (SaaS Fase 8).
        Entrada: filas estilo BD/app. Salida: hoja MENU + caché local actualizada.
        """
        if not self._connected:
            return False
        sheet = self._get_sheet("MENU")
        if not sheet:
            return False
        headers = SHEET_HEADERS["MENU"]
        normalized: List[Dict[str, Any]] = []
        rows: List[List[Any]] = []
        for item in items:
            row_item = {
                "id": str(item.get("id", item.get("external_id", ""))),
                "nombre": str(item.get("nombre", "")).strip(),
                "precio": float(item.get("precio", 0) or 0),
                "categoria": str(item.get("categoria", "")).strip(),
                "disponible": self._parse_bool(item.get("disponible", True)),
            }
            normalized.append(row_item)
            rows.append(
                [
                    row_item["id"],
                    row_item["nombre"],
                    row_item["precio"],
                    row_item["categoria"],
                    "true" if row_item["disponible"] else "false",
                ]
            )
        try:
            sheet.clear()
            sheet.append_row(headers)
            if rows:
                sheet.append_rows(rows, value_input_option="USER_ENTERED")
            with self._cache_lock:
                self._menu_cache = normalized
            self._save_local_menu(normalized)
            logger.info("Menu mirror pushed to Sheets: %d items", len(normalized))
            return True
        except Exception as exc:
            logger.error("replace_menu_mirror failed: %s", exc)
            return False

    def upsert_order_mirror(self, order: Dict[str, Any]) -> bool:
        """
        Push/update one order row from BD to ORDERS sheet (mirror, no-op if offline).
        """
        order_id = str(order.get("order_id", "")).strip().upper()
        if not order_id:
            return False
        if not self._connected:
            return False

        ts = order.get("timestamp") or order.get("created_at")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        payload = {
            "order_id": order_id,
            "wa_id": str(order.get("wa_id", "")),
            "items": order.get("items") or [],
            "total": float(order.get("total") or 0),
            "status": str(order.get("status", "pending")),
            "timestamp": str(ts or datetime.utcnow().isoformat()),
            "customer_name": str(order.get("customer_name", "")),
            "address": str(order.get("address", "")),
            "delivery_type": str(order.get("delivery_type", "")),
        }

        with self._cache_lock:
            had_row = order_id in self._order_row_index
            self._orders_local[order_id] = payload

        if had_row:
            return self._update_order_status_on_sheets(order_id, payload["status"])

        with self._cache_lock:
            self._dirty_new_orders.add(order_id)
        self._save_local_orders()
        try:
            return self._create_order_on_sheets(order_id)
        except Exception as exc:
            logger.warning("upsert_order_mirror failed for %s: %s", order_id, exc)
            return False


_sheets_client_singleton: Optional[GoogleSheetsClient] = None
_sheets_client_lock = threading.Lock()


def get_google_sheets_client(
    credentials_path: str,
    spreadsheet_id: str,
) -> GoogleSheetsClient:
    """Return one GoogleSheetsClient per process (shared by create_app and scripts)."""
    global _sheets_client_singleton
    with _sheets_client_lock:
        if _sheets_client_singleton is None:
            _sheets_client_singleton = GoogleSheetsClient(
                credentials_path,
                spreadsheet_id,
            )
        return _sheets_client_singleton
