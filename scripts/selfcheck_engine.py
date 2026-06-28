"""Self-checks for Fase 6 infrastructure optimizations (no pytest, only assert + print).

Usage:
    python scripts/selfcheck_engine.py

Each check verifies one Fase-6 subpoint. On pass: ✅ DONE [<id>]. On fail: ❌ FAIL [<id>] - <reason>.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "chatbot", SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _make_store_stub(blocked_ids=None, menu_items=None, call_counter=None):
    store = types.SimpleNamespace()
    store.refresh_users_cache = lambda: None
    _blocked = set(blocked_ids or [])
    store.get_blocked_wa_ids = lambda: set(_blocked)
    _menu = list(menu_items or [])
    def _get_menu():
        if call_counter is not None:
            call_counter["n"] += 1
        return list(_menu)
    store.get_menu = _get_menu
    store.upsert_user = lambda **kw: None
    store.get_user = lambda wa_id: {"wa_id": wa_id, "name": "", "address": "", "blocked": False}
    store.create_order = lambda *a, **kw: "ORD-TEST"
    store.get_order = lambda *a, **kw: None
    store.update_order_status = lambda *a, **kw: True
    store.get_pending_orders = lambda: []
    store.create_reservation = lambda *a, **kw: "RES-TEST"
    store.get_last_order = lambda *a, **kw: None
    return store


def _make_admin_stub(phones_match_counter=None):
    admin = types.SimpleNamespace()
    admin.normalize_wa_id_e164 = lambda wa_id: wa_id  # identity: already normalized in test
    def _phones_match(a, b):
        if phones_match_counter is not None:
            phones_match_counter["n"] += 1
        return a == b
    admin.phones_match = _phones_match
    return admin


def _make_flow_engine(flow_path=None):
    from app.core.state_manager import StateManager
    from app.services.productos_service import ProductosService
    from app.services.order_service import OrderService
    from app.services.ayuda_service import AyudaService
    from app.services.user_service import UserService
    from app.core.flow_engine import FlowEngine

    store = _make_store_stub(menu_items=[
        {"id": "p1", "nombre": "Hamburguesa", "precio": 15000.0, "categoria": "Comida", "disponible": True},
    ])
    sm = StateManager()
    ps = ProductosService(store)
    os_ = OrderService(store, ps)
    ays = AyudaService(store)
    us = UserService(store)
    admin = _make_admin_stub()

    from app.config import FLOWS_PATH
    return FlowEngine(
        state_manager=sm,
        productos_service=ps,
        order_service=os_,
        ayuda_service=ays,
        user_service=us,
        admin_service=admin,
        flow_path=flow_path or str(FLOWS_PATH),
    )


# ---------------------------------------------------------------------------
# p6_1 — BlockedUsersCache O(1)
# ---------------------------------------------------------------------------

def p6_1_blocked_cache_o1() -> None:
    from app.services.blocked_users_cache import BlockedUsersCache

    phones_match_counter = {"n": 0}
    blocked_ids = {f"+5730000{i:05d}" for i in range(100)}
    known_id = next(iter(blocked_ids))

    store = _make_store_stub(blocked_ids=blocked_ids)
    admin = _make_admin_stub(phones_match_counter=phones_match_counter)

    cache = BlockedUsersCache(store, admin, ttl_seconds=3600)
    cache.refresh()

    assert cache.count() == 100, f"count={cache.count()} expected 100"

    result = cache.is_blocked(known_id)
    assert result is True, f"is_blocked({known_id!r}) returned False"

    # phones_match must NOT be called: new impl uses set lookup
    assert phones_match_counter["n"] == 0, (
        f"phones_match called {phones_match_counter['n']} times; expected 0 (O(1) set lookup)"
    )

    unknown = "+57999999999"
    result2 = cache.is_blocked(unknown)
    assert result2 is False, f"is_blocked({unknown!r}) should be False"
    assert phones_match_counter["n"] == 0, "phones_match must never be called"

    # apply_local add
    cache.apply_local(unknown, True)
    assert cache.is_blocked(unknown) is True, "apply_local(True) did not add"
    assert cache.count() == 101

    # apply_local remove
    cache.apply_local(unknown, False)
    assert cache.is_blocked(unknown) is False, "apply_local(False) did not remove"
    assert cache.count() == 100


# ---------------------------------------------------------------------------
# p6_2 — ProductosService menu TTL cache
# ---------------------------------------------------------------------------

def p6_2_menu_ttl_cache() -> None:
    import app.services.productos_service as ps_mod

    call_counter = {"n": 0}
    menu = [{"id": "p1", "nombre": "Arepa", "precio": 5000.0, "categoria": "Comida", "disponible": True}]
    store = _make_store_stub(menu_items=menu, call_counter=call_counter)

    # Subclass to control business_id without relying on chatbot.business_context
    class _Svc(ps_mod.ProductosService):
        _bid = "biz_test_A"
        @staticmethod
        def _active_bid() -> str:
            return _Svc._bid
        @staticmethod
        def _default_context_override():
            return None  # bypass context override so DB path is exercised

    # Reset module-level cache to isolate test
    ps_mod._menu_cache = None

    svc = _Svc(store)

    for _ in range(10):
        result = svc.get_available_productos()
        assert result == menu, f"unexpected result: {result}"

    assert call_counter["n"] <= 2, (
        f"get_menu() called {call_counter['n']} times for 10 requests with same bid+bucket; expected ≤2"
    )

    # Changing business_id must cause a cache miss
    calls_before = call_counter["n"]
    _Svc._bid = "biz_test_B"
    svc.get_available_productos()
    assert call_counter["n"] > calls_before, (
        f"changing business_id did not trigger a DB refresh (calls before={calls_before}, after={call_counter['n']})"
    )

    # Restore to avoid polluting other tests
    ps_mod._menu_cache = None


# ---------------------------------------------------------------------------
# p6_3 — FlowEngine._cart_guard_flows cached in _apply_flow
# ---------------------------------------------------------------------------

def p6_3_cart_guard_flows_cached() -> None:
    engine = _make_flow_engine()

    assert isinstance(engine._cart_guard_flows_set, frozenset), (
        f"_cart_guard_flows_set is {type(engine._cart_guard_flows_set)}, expected frozenset"
    )

    state = {"flow": "order", "step": "order_start_node", "data": {"cart": [{"id": "p1", "qty": 1}]}}
    fset_id = id(engine._cart_guard_flows_set)

    for _ in range(5):
        engine._has_active_order(state)
        assert id(engine._cart_guard_flows_set) == fset_id, (
            "frozenset object was replaced during _has_active_order calls"
        )


# ---------------------------------------------------------------------------
# p6_4 — Flow JSON mtime cache
# ---------------------------------------------------------------------------

def p6_4_flow_json_cache() -> None:
    import app.core.flow_engine as fe_mod

    # Clear cache to get a clean first load
    fe_mod._flow_file_cache.clear()

    engine1 = _make_flow_engine()
    engine2 = _make_flow_engine()

    # Both engines must share the same parsed flow dict object
    assert engine1.flow is engine2.flow, (
        f"flow dicts are different objects (id1={id(engine1.flow)}, id2={id(engine2.flow)}); "
        "second FlowEngine should reuse the cached dict"
    )


# ---------------------------------------------------------------------------
# p6_5 — business_context imports hoisted to module level
# ---------------------------------------------------------------------------

def p6_5_business_context_imports_hoisted() -> None:
    import app.core.state_manager as sm_mod
    import app.core.flow_engine as fe_mod
    import app.integrations.db_store as db_mod

    # Hoisted references exist at module level (may be None if chatbot.business_context absent)
    assert hasattr(sm_mod, "_get_active_business_id"), (
        "state_manager missing module-level _get_active_business_id"
    )
    assert hasattr(fe_mod, "_ctx_get_prompt"), (
        "flow_engine missing module-level _ctx_get_prompt"
    )
    assert hasattr(db_mod, "_get_active_business_id"), (
        "db_store missing module-level _get_active_business_id"
    )

    # _resolve_key must not raise even without chatbot.business_context
    from app.core.state_manager import StateManager
    key = StateManager._resolve_key("test_wa_id")
    assert isinstance(key, str) and "test_wa_id" in key, (
        f"_resolve_key returned unexpected value: {key!r}"
    )


# ---------------------------------------------------------------------------
# integrity_check — golden outputs unchanged; PHASES still has 5 phases
# ---------------------------------------------------------------------------

def integrity_check() -> None:
    import selfcheck_parser as SC

    assert len(SC.PHASES) == 5, f"PHASES has {len(SC.PHASES)} entries; expected 5 (phases 1–5 intact)"
    assert set(SC.PHASES.keys()) == {1, 2, 3, 4, 5}, f"unexpected PHASES keys: {set(SC.PHASES.keys())}"

    from app.core.parser import OrderIntelligenceEngine

    r1 = SC.ENGINE_FER.parse(SC.CHAOS_1)
    assert r1.get("status") != "error", f"ENGINE_FER.parse(CHAOS_1) returned error: {r1}"

    r2 = SC.ENGINE_DEP.parse(SC.CHAOS_2)
    assert r2.get("status") != "error", f"ENGINE_DEP.parse(CHAOS_2) returned error: {r2}"

    # Spot-check: ENGINE_FER on CHAOS_1 still resolves known items
    items1 = {str(i["product"]).lower() for i in r1.get("items", [])}
    assert any("arco" in p for p in items1), f"arco not found in ENGINE_FER result: {items1}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = [
    ("6.1 BlockedUsersCache O(1)", p6_1_blocked_cache_o1),
    ("6.2 ProductosService menu TTL cache", p6_2_menu_ttl_cache),
    ("6.3 _cart_guard_flows_set cached in _apply_flow", p6_3_cart_guard_flows_cached),
    ("6.4 flow JSON mtime cache", p6_4_flow_json_cache),
    ("6.5 business_context imports hoisted", p6_5_business_context_imports_hoisted),
    ("integrity", integrity_check),
]


def main() -> int:
    for label, fn in CHECKS:
        try:
            fn()
        except AssertionError as exc:
            print(f"❌ FAIL [{label}] - {exc}")
            return 1
        except Exception as exc:
            print(f"❌ FAIL [{label}] - {type(exc).__name__}: {exc}")
            return 1
        print(f"✅ DONE [{label}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
