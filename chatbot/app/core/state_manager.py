"""Thread-safe per-user state with optional disk persistence."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_STATE = {
    "flow": "idle",
    "step": "start",
    "data": {},
}

STATE_PERSIST_DEBOUNCE_SECONDS = 2.0


class StateManager:
    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._states: Dict[str, Dict[str, Any]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        self._save_timer: Optional[threading.Timer] = None
        self._load()

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with self._persist_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                self._states = payload
        except (json.JSONDecodeError, OSError):
            self._states = {}

    def _save(self) -> None:
        if not self._persist_path:
            return
        with self._lock:
            snapshot = deepcopy(self._states)
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self._persist_path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))

    def _cancel_save_timer(self) -> None:
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None

    def _schedule_save(self) -> None:
        self._cancel_save_timer()
        timer = threading.Timer(STATE_PERSIST_DEBOUNCE_SECONDS, self._flush_save)
        timer.daemon = True
        self._save_timer = timer
        timer.start()

    def _flush_save(self) -> None:
        with self._lock:
            self._save_timer = None
        self._save()

    @staticmethod
    def _critical_state_changed(
        previous: Optional[Dict[str, Any]],
        current: Dict[str, Any],
    ) -> bool:
        if previous is None:
            return True
        if previous.get("step") != current.get("step"):
            return True
        if previous.get("flow") != current.get("flow"):
            return True
        prev_cart = (previous.get("data") or {}).get("cart", [])
        curr_cart = (current.get("data") or {}).get("cart", [])
        return prev_cart != curr_cart

    def _persist_if_changed(
        self,
        wa_id: str,
        previous: Optional[Dict[str, Any]],
        current: Dict[str, Any],
    ) -> None:
        if previous == current:
            return
        if self._critical_state_changed(previous, current):
            self._cancel_save_timer()
            self._save()
        else:
            self._schedule_save()

    @staticmethod
    def _snapshot_state(state: Dict[str, Any]) -> Dict[str, Any]:
        """Lightweight read copy: deep-copy cart/reservation only when present."""
        data = state.get("data") or {}
        data_copy = dict(data)
        cart = data.get("cart")
        if cart is not None:
            data_copy["cart"] = [dict(item) for item in cart]
        reservation = data.get("reservation")
        if reservation:
            data_copy["reservation"] = dict(reservation)
        last_items = data.get("last_order_items")
        if last_items is not None:
            data_copy["last_order_items"] = [dict(item) for item in last_items]
        return {
            "flow": state.get("flow", "idle"),
            "step": state.get("step", "start"),
            "data": data_copy,
        }

    def get(self, wa_id: str) -> Dict[str, Any]:
        with self._lock:
            if wa_id not in self._states:
                self._states[wa_id] = deepcopy(DEFAULT_STATE)
            return self._snapshot_state(self._states[wa_id])

    def update(self, wa_id: str, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            if wa_id not in self._states:
                self._states[wa_id] = deepcopy(DEFAULT_STATE)
            previous = self._snapshot_state(self._states[wa_id])
            self._states[wa_id].update(kwargs)
            current = self._states[wa_id]
            self._persist_if_changed(wa_id, previous, current)
            return self._snapshot_state(current)

    def set_step(self, wa_id: str, step: str, flow: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"step": step}
        if flow is not None:
            payload["flow"] = flow
        return self.update(wa_id, **payload)

    def set_data(self, wa_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.update(wa_id, data=data)

    def patch_data(self, wa_id: str, **fields: Any) -> Dict[str, Any]:
        with self._lock:
            if wa_id not in self._states:
                self._states[wa_id] = deepcopy(DEFAULT_STATE)
            previous = self._snapshot_state(self._states[wa_id])
            merged = {**self._states[wa_id].get("data", {}), **fields}
            self._states[wa_id]["data"] = merged
            current = self._states[wa_id]
            self._persist_if_changed(wa_id, previous, current)
            return self._snapshot_state(current)

    def reset(self, wa_id: str) -> Dict[str, Any]:
        with self._lock:
            raw_previous = self._states.get(wa_id)
            previous = (
                self._snapshot_state(raw_previous) if raw_previous is not None else None
            )
            new_state = deepcopy(DEFAULT_STATE)
            self._states[wa_id] = new_state
            self._persist_if_changed(wa_id, previous, new_state)
            return self._snapshot_state(new_state)

    def cancel(self, wa_id: str) -> Dict[str, Any]:
        return self.reset(wa_id)
