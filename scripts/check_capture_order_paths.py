"""Self-check: verifica los tres paths críticos de _action_capture_order.

Ejecutar: python scripts/check_capture_order_paths.py
Salida esperada: todos los asserts pasan silenciosamente; imprime PASS al final.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "chatbot"))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'check_capture_order.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "check-secret-key")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "checkpin")

SAMPLE_PRODUCTOS = [
    {"id": "p1", "nombre": "Pizza Hawaiana", "precio": 12.0, "categoria": "Pizzas", "disponible": True},
    {"id": "p2", "nombre": "Coca Cola", "precio": 2.5, "categoria": "Bebidas", "disponible": True},
]


def _fake_parse(
    items: List[Dict],
    unknown: List[str] | None = None,
    ambiguous: List[Dict] | None = None,
) -> Dict[str, Any]:
    return {"items": items, "notes": [], "unknown": unknown or [], "ambiguous_items": ambiguous or []}


def _cart_item(product: str, qty: int = 1, price: float = 12.0) -> Dict[str, Any]:
    return {"product_id": product.lower(), "product": product, "qty": qty,
            "unit_price": price, "subtotal": round(qty * price, 2)}


def _setup():
    from infrastructure.database import init_db, session_scope
    from services.business_service import ensure_default_business

    init_db()
    with session_scope() as db:
        ensure_default_business(db)

    from chatbot.runtime import get_bot_context, reset_bot_context

    reset_bot_context()
    ctx = get_bot_context(start_background=False)
    sm = ctx.flow_engine.state_manager
    sm._cancel_save_timer()
    sm._persist_path = None
    sm._states = {}
    ctx.flow_engine.reload_flow()
    return ctx.flow_engine


def check_all_unknown(engine, monkeypatch_fn):
    """PATH: all items unknown → muestra lista de desconocidos, step no cambia."""
    wa_id = "chk_all_unknown"
    engine.process_message(wa_id, "pedido")
    step_before = engine.state_manager.get(wa_id).get("step")

    monkeypatch_fn(engine, _fake_parse([], ["xifon", "zarcoleta"]))
    reply = engine.process_message(wa_id, "xifon y zarcoleta")

    step_after = engine.state_manager.get(wa_id).get("step")
    cart = engine.state_manager.get(wa_id).get("data", {}).get("cart", [])

    assert isinstance(reply, str), f"reply must be str, got {type(reply)}"
    assert "xifon" in reply.lower() or "zarcoleta" in reply.lower(), (
        f"Unknown items not shown in reply: {reply!r}"
    )
    assert step_after == step_before, (
        f"Step changed on all-unknown: {step_before!r} → {step_after!r}"
    )
    assert not cart, f"Cart must be empty on all-unknown, got {cart}"
    print(f"  [PASS] all-unknown: step={step_after!r}, reply contains unknown items")


def check_partial(engine, monkeypatch_fn):
    """PATH: some recognized + some unknown → muestra ambas listas, va a clarify."""
    wa_id = "chk_partial"
    engine.process_message(wa_id, "pedido")

    monkeypatch_fn(engine, _fake_parse([_cart_item("Pizza Hawaiana")], ["zarcoleta"]))
    reply = engine.process_message(wa_id, "pizza y zarcoleta")

    step = engine.state_manager.get(wa_id).get("step")
    cart = engine.state_manager.get(wa_id).get("data", {}).get("cart", [])

    assert isinstance(reply, str)
    assert step == "order_clarify_node", f"Expected order_clarify_node, got {step!r}"
    assert len(cart) == 1, f"Cart must have 1 item, got {cart}"
    print(f"  [PASS] partial: step={step!r}, cart={[i['product'] for i in cart]}")


def check_success_step(engine, monkeypatch_fn):
    """PATH: all recognized → goes to order_review_node."""
    wa_id = "chk_success"
    engine.process_message(wa_id, "pedido")

    monkeypatch_fn(engine, _fake_parse([_cart_item("Pizza Hawaiana"), _cart_item("Coca Cola", price=2.5)]))
    engine.process_message(wa_id, "pizza y coca cola")

    step = engine.state_manager.get(wa_id).get("step")
    cart = engine.state_manager.get(wa_id).get("data", {}).get("cart", [])

    assert step == "order_review_node", f"Expected order_review_node, got {step!r}"
    assert len(cart) == 2, f"Cart must have 2 items, got {cart}"
    print(f"  [PASS] success: step={step!r}, cart={[i['product'] for i in cart]}")


def check_greeting_stays_in_order(engine):
    """PRIORITY FIX: 'hola' at order_start_node (empty cart) must NOT show abandon_confirm."""
    wa_id = "chk_greeting"
    engine.process_message(wa_id, "pedido")
    reply = engine.process_message(wa_id, "hola")

    step = engine.state_manager.get(wa_id).get("step")
    awaiting = engine.state_manager.get(wa_id).get("data", {}).get("awaiting_abandon_confirm", False)

    assert not awaiting, f"abandon_confirm must NOT be set for greeting with empty cart, got awaiting={awaiting}"
    assert "pedido en curso" not in reply.lower(), (
        f"Should not show abandon_confirm for greeting, reply={reply!r}"
    )
    assert step == "order_start_node", f"Step must stay at order_start_node, got {step!r}"
    print(f"  [PASS] greeting-in-order: step={step!r}, no abandon_confirm")


def check_empty_cart_no_abandon(engine):
    """GUARD FIX: 'inicio' at order_start_node with empty cart must NOT show abandon_confirm."""
    wa_id = "chk_empty_cart_inicio"
    engine.process_message(wa_id, "pedido")
    reply = engine.process_message(wa_id, "inicio")

    awaiting = engine.state_manager.get(wa_id).get("data", {}).get("awaiting_abandon_confirm", False)
    assert not awaiting, f"abandon_confirm must NOT fire with empty cart; awaiting={awaiting}"
    print("  [PASS] empty-cart-inicio: no abandon_confirm")


def main():
    print("=== check_capture_order_paths.py ===\n")

    try:
        engine = _setup()
    except Exception as exc:
        print(f"SETUP ERROR: {exc}")
        return 1

    import importlib

    _original = engine.order_service.parse_order_text

    def make_monkeypatch(eng, fake_result):
        eng.order_service.parse_order_text = lambda text, cart=None, wa_id="": fake_result

    def restore(eng):
        eng.order_service.parse_order_text = _original

    errors = []

    for name, fn, *args in [
        ("all_unknown", check_all_unknown, engine, make_monkeypatch),
        ("partial", check_partial, engine, make_monkeypatch),
        ("success", check_success_step, engine, make_monkeypatch),
        ("greeting_in_order", check_greeting_stays_in_order, engine),
        ("empty_cart_no_abandon", check_empty_cart_no_abandon, engine),
    ]:
        restore(engine)
        try:
            if args:
                fn(*args)
            else:
                fn(engine)
        except AssertionError as exc:
            print(f"  [FAIL] {name}: {exc}")
            errors.append(name)
        except Exception as exc:
            print(f"  [ERROR] {name}: {exc}")
            errors.append(name)

    restore(engine)
    print()
    if errors:
        print(f"=== RESULTADO: {len(errors)} fallo(s): {errors} ===")
        return 1
    print("=== RESULTADO: todos los checks PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
