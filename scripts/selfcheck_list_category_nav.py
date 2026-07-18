"""
List category navigation: id (__cat__) and title/Body-only must open product list.

No Twilio network. Run: python scripts/selfcheck_list_category_nav.py
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "chatbot"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass

MENU: List[Dict[str, Any]] = [
    {
        "id": "1",
        "nombre": "Changua",
        "precio": 8000.0,
        "categoria": "🍲 Sopas",
        "disponible": True,
    },
    {
        "id": "2",
        "nombre": "Ajiaco",
        "precio": 12000.0,
        "categoria": "🍲 Sopas",
        "disponible": True,
    },
    {
        "id": "3",
        "nombre": "Bandeja Paisa",
        "precio": 20000.0,
        "categoria": "🍲 Platos principales",
        "disponible": True,
    },
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def _store() -> Any:
    store = types.SimpleNamespace()
    store.refresh_users_cache = lambda: None
    store.get_blocked_wa_ids = lambda: set()
    store.get_menu = lambda: list(MENU)
    store.upsert_user = lambda **kw: None
    store.get_user = lambda wa_id: {
        "wa_id": wa_id,
        "name": "",
        "address": "",
        "blocked": False,
    }
    store.create_order = lambda *a, **kw: "ORD-TEST"
    store.get_order = lambda *a, **kw: None
    store.update_order_status = lambda *a, **kw: True
    store.get_pending_orders = lambda: []
    store.create_reservation = lambda *a, **kw: "RES-TEST"
    store.get_last_order = lambda *a, **kw: None
    return store


def _engine():
    from app.core.state_manager import StateManager
    from app.services.productos_service import ProductosService
    from app.services.order_service import OrderService
    from app.services.ayuda_service import AyudaService
    from app.services.user_service import UserService
    from app.core.flow_engine import FlowEngine
    from app.config import FLOWS_PATH

    store = _store()
    sm = StateManager()
    ps = ProductosService(store)
    return FlowEngine(
        state_manager=sm,
        productos_service=ps,
        order_service=OrderService(store, ps),
        ayuda_service=AyudaService(store),
        user_service=UserService(store),
        admin_service=types.SimpleNamespace(
            normalize_wa_id_e164=lambda wa_id: wa_id,
            phones_match=lambda a, b: a == b,
            canonical_wa_id=lambda wa_id, _from=None: wa_id,
        ),
        flow_path=str(FLOWS_PATH),
    )


def _goto_productos(engine, wa_id: str) -> None:
    engine.state_manager.reset(wa_id)
    engine.process_message(wa_id, "productos")
    state = engine.state_manager.get(wa_id)
    step = state.get("step") or ""
    if "productos_node" not in step:
        fail(f"expected productos_node after 'productos', got {step!r}")


def _cart_names(engine, wa_id: str) -> List[str]:
    data = engine.state_manager.get(wa_id).get("data") or {}
    items = data.get("order_items") or data.get("cart") or []
    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            names.append(str(item.get("nombre") or item.get("product") or ""))
    return [n for n in names if n]


def _assert_category_list(engine, wa_id: str, category: str, label: str) -> None:
    state = engine.state_manager.get(wa_id)
    step = state.get("step") or ""
    data = state.get("data") or {}
    if "productos_category_node" not in step:
        fail(f"{label}: expected productos_category_node, got {step!r}")
    if data.get("selected_category") != category:
        fail(
            f"{label}: selected_category={data.get('selected_category')!r}, "
            f"want {category!r}"
        )
    cart = _cart_names(engine, wa_id)
    if cart:
        fail(f"{label}: cart must be empty, got {cart!r}")


def resolve_user_input(
    list_payload: str = "",
    button_payload: str = "",
    body: str = "",
) -> str:
    """Mirror gateway preference (list id wins)."""
    return list_payload or button_payload or body


def main() -> None:
    # --- gateway preference ---
    assert (
        resolve_user_input(
            list_payload="__cat__Sopas",
            button_payload="pedido",
            body="Sopas",
        )
        == "__cat__Sopas"
    ), "list_payload must win"
    assert (
        resolve_user_input(list_payload="", button_payload="pedido", body="hola")
        == "pedido"
    ), "button when no list"
    assert resolve_user_input(body="Sopas") == "Sopas", "body fallback"
    print("PASS gateway list_id preference")

    # --- source order in gateway.py ---
    gw = (ROOT / "chatbot" / "gateway.py").read_text(encoding="utf-8")
    if "user_input = list_payload or button_payload or body" not in gw:
        fail("gateway.py must prefer list_payload over button_payload/body")
    if "user_input = button_payload or list_payload or body" in gw:
        fail("gateway.py still prefers button_payload over list_payload")
    print("PASS gateway.py source order")

    engine = _engine()
    wa = "selfcheck_list_cat_1"

    # 1) __cat__ id path (Twilio uses full DB category in id)
    _goto_productos(engine, wa)
    engine.process_message(wa, "__cat__🍲 Sopas")
    _assert_category_list(engine, wa, "🍲 Sopas", "__cat__ with emoji")
    print("PASS __cat__🍲 Sopas → category list")

    # 1b) __cat__ without emoji still resolves to DB name
    wa1b = "selfcheck_list_cat_1b"
    _goto_productos(engine, wa1b)
    engine.process_message(wa1b, "__cat__Sopas")
    _assert_category_list(engine, wa1b, "🍲 Sopas", "__cat__Sopas no emoji")
    print("PASS __cat__Sopas → 🍲 Sopas")

    # 2) title/Body-only without emoji (the bug)
    wa2 = "selfcheck_list_cat_2"
    _goto_productos(engine, wa2)
    engine.process_message(wa2, "Sopas")
    _assert_category_list(engine, wa2, "🍲 Sopas", "Body Sopas")
    print("PASS Body Sopas (no emoji) → category list")

    # 3) casefold
    wa3 = "selfcheck_list_cat_3"
    _goto_productos(engine, wa3)
    engine.process_message(wa3, "sopas")
    _assert_category_list(engine, wa3, "🍲 Sopas", "casefold sopas")
    print("PASS casefold category title")

    # 3b) with emoji (as WhatsApp may send)
    wa3b = "selfcheck_list_cat_3b"
    _goto_productos(engine, wa3b)
    engine.process_message(wa3b, "🍲 Platos principales")
    _assert_category_list(
        engine, wa3b, "🍲 Platos principales", "Body with emoji"
    )
    print("PASS Body with emoji → category list")

    wa4 = "selfcheck_list_cat_4"
    _goto_productos(engine, wa4)
    engine.process_message(wa4, "Platos principales")
    _assert_category_list(
        engine, wa4, "🍲 Platos principales", "Platos without emoji"
    )
    print("PASS Platos principales (no emoji) → category list")

    # 4) product name must not be swallowed as category
    matched = engine._match_list_category("Changua")
    if matched is not None:
        fail(f"product name Changua must not match category, got {matched!r}")
    print("PASS product name is not a category")

    # 5) InteractiveData parse → list id (gateway shape)
    interactive = {
        "interactive": {
            "type": "list_reply",
            "list_reply": {"id": "__cat__Sopas", "title": "Sopas"},
        }
    }
    list_id = (
        interactive.get("interactive", {})
        .get("list_reply", {})
        .get("id", "")
    )
    user_input = resolve_user_input(
        list_payload=list_id,
        body="Sopas",
    )
    if user_input != "__cat__Sopas":
        fail(f"InteractiveData id must win, got {user_input!r}")
    print("PASS InteractiveData list_reply.id wins over Body")

    # motor helper present
    fe = (ROOT / "chatbot" / "app" / "core" / "flow_engine.py").read_text(
        encoding="utf-8"
    )
    if "_match_list_category" not in fe:
        fail("flow_engine missing _match_list_category")
    if "list_category_target" not in fe:
        fail("flow_engine must still honor list_category_target from JSON")
    print("PASS flow_engine helpers")

    print("\nALL PASS selfcheck_list_category_nav")


if __name__ == "__main__":
    main()
