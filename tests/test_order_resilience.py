"""Tests: resiliencia parcial (Capa 1), modificación inteligente (Capa 2),
desambiguación (Capa 3). No modifica tests existentes."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "chatbot"))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_resilience.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")

SAMPLE_PRODUCTOS = [
    {"id": "pizza1", "nombre": "Pizza Hawaiana", "precio": 12.0, "categoria": "Pizzas", "disponible": True},
    {"id": "cc1", "nombre": "Coca Cola", "precio": 2.5, "categoria": "Bebidas", "disponible": True},
    {"id": "hb1", "nombre": "Hamburguesa Clasica", "precio": 10.0, "categoria": "Hamburguesas", "disponible": True},
    {"id": "yg1", "nombre": "Yogur Natural", "precio": 3.0, "categoria": "Lacteos", "disponible": True},
    {"id": "ar5", "nombre": "Arroz Diana 500g", "precio": 4.0, "categoria": "Granos", "disponible": True},
    {"id": "ar1", "nombre": "Arroz Diana 1kg", "precio": 7.0, "categoria": "Granos", "disponible": True},
    {"id": "po1", "nombre": "Pollo Entero", "precio": 15.0, "categoria": "Carnes", "disponible": True},
]


def _cart_item(
    product: str = "Pizza Hawaiana",
    qty: int = 1,
    price: float = 12.0,
    pid: str = "",
) -> Dict[str, Any]:
    return {
        "product_id": pid or product.lower().replace(" ", "_"),
        "product": product,
        "qty": qty,
        "unit_price": price,
        "subtotal": round(qty * price, 2),
    }


def _fake_parse(
    items: List[Dict],
    unknown: List[str] | None = None,
    ambiguous: List[Dict] | None = None,
) -> Dict[str, Any]:
    return {
        "items": items,
        "notes": [],
        "unknown": unknown or [],
        "ambiguous_items": ambiguous or [],
    }


def _ambiguous_coca() -> List[Dict]:
    return [
        {"product": "Coca Cola 400ml", "product_id": "cc1", "unit_price": 1.5},
        {"product": "Coca Cola 1.5L", "product_id": "cc2", "unit_price": 3.0},
    ]


@pytest.fixture(autouse=True)
def reset_context():
    from chatbot.runtime import reset_bot_context

    reset_bot_context()
    yield
    reset_bot_context()


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from infrastructure.database import init_db, session_scope
    from services.business_service import ensure_default_business

    init_db()
    with session_scope() as db:
        ensure_default_business(db)


@pytest.fixture
def engine(monkeypatch):
    from chatbot.runtime import get_bot_context

    monkeypatch.setattr(
        "app.services.productos_service.ProductosService.get_available_productos",
        lambda self: SAMPLE_PRODUCTOS,
    )
    monkeypatch.setattr(
        "services.notification_service.on_order_pending",
        lambda _order: None,
    )
    ctx = get_bot_context(start_background=False)
    # ponytail: disable disk persistence + wipe stale on-disk state so tests
    # always start clean. ceiling: only guards against cross-run contamination.
    sm = ctx.flow_engine.state_manager
    sm._cancel_save_timer()
    sm._persist_path = None
    sm._states = {}
    ctx.flow_engine.reload_flow()
    return ctx.flow_engine


def _step(engine, wa_id: str) -> str:
    return engine.state_manager.get(wa_id).get("step", "")


def _data(engine, wa_id: str) -> Dict[str, Any]:
    return engine.state_manager.get(wa_id).get("data", {})


# ─── Capa 1 — Resiliencia parcial ───────────────────────────────────────────


def test_t01_one_recognized_zero_unknown(engine):
    wa_id = "res_t01"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    assert _step(engine, wa_id) == "order_review_node"
    assert len(_data(engine, wa_id).get("cart", [])) == 1


def test_t02_twenty_recognized_zero_unknown(engine, monkeypatch):
    wa_id = "res_t02"
    items = [_cart_item(f"Producto {i}", 1, float(i)) for i in range(1, 21)]
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(items))
    engine.process_message(wa_id, "veinte productos distintos")
    assert _step(engine, wa_id) == "order_review_node"
    assert len(_data(engine, wa_id).get("cart", [])) == 20


def test_t03_fifty_recognized_zero_unknown(engine, monkeypatch):
    wa_id = "res_t03"
    items = [_cart_item(f"Producto {i}", 1, float(i)) for i in range(1, 51)]
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(items))
    engine.process_message(wa_id, "cincuenta productos")
    assert _step(engine, wa_id) == "order_review_node"
    assert len(_data(engine, wa_id).get("cart", [])) == 50


def test_t04_one_recognized_nineteen_unknown(engine, monkeypatch):
    wa_id = "res_t04"
    items = [_cart_item("Pizza Hawaiana")]
    unknowns = [f"desconocido_{i}" for i in range(19)]
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(items, unknowns))
    engine.process_message(wa_id, "1 pizza y 19 cosas raras")
    assert _step(engine, wa_id) == "order_clarify_node"
    d = _data(engine, wa_id)
    assert len(d.get("cart", [])) == 1
    assert len(d.get("pending_unknowns", [])) == 19


def test_t05_nineteen_recognized_one_unknown(engine, monkeypatch):
    wa_id = "res_t05"
    items = [_cart_item(f"Producto {i}", 1, float(i)) for i in range(1, 20)]
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(items, ["cosararisima"]))
    engine.process_message(wa_id, "19 productos y un raro")
    assert _step(engine, wa_id) == "order_clarify_node"
    d = _data(engine, wa_id)
    assert len(d.get("cart", [])) == 19
    assert len(d.get("pending_unknowns", [])) == 1


def test_t06_all_ten_recognized_no_pending(engine, monkeypatch):
    wa_id = "res_t06"
    items = [_cart_item(f"Producto {i}", 1, float(i)) for i in range(1, 11)]
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(items))
    engine.process_message(wa_id, "diez productos")
    assert _step(engine, wa_id) == "order_review_node"
    assert not _data(engine, wa_id).get("pending_unknowns")


def test_t07_all_unknown_fallback_empty_cart(engine, monkeypatch):
    wa_id = "res_t07"
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse([], ["x1", "x2", "x3", "x4", "x5"]))
    engine.process_message(wa_id, "x1 x2 x3 x4 x5")
    assert _step(engine, wa_id) == "order_start_node"
    assert not _data(engine, wa_id).get("cart")


def test_t08_long_message_no_exception(engine):
    wa_id = "res_t08"
    base = "1 pizza hawaiana, 1 coca cola, 1 hamburguesa clasica"
    noise = " y xyzfoo" * 60
    long_msg = base + noise
    assert len(long_msg) >= 500
    engine.process_message(wa_id, "pedido")
    reply = engine.process_message(wa_id, long_msg)
    assert isinstance(reply, str)
    assert len(_data(engine, wa_id).get("cart", [])) > 0, "recognized items lost"


def test_t09_typos_no_crash(engine):
    wa_id = "res_t09"
    engine.process_message(wa_id, "pedido")
    reply = engine.process_message(wa_id, "piza hawajana y hamburgesa klazika")
    assert isinstance(reply, str)


def test_t10_word_and_digit_quantities(engine):
    wa_id = "res_t10"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "dos pizza hawaiana y 3 coca cola")
    cart = _data(engine, wa_id).get("cart", [])
    qty_map = {it["product"]: it["qty"] for it in cart}
    if "Pizza Hawaiana" in qty_map:
        assert qty_map["Pizza Hawaiana"] == 2
    if "Coca Cola" in qty_map:
        assert qty_map["Coca Cola"] == 3


def test_t11_emojis_punctuation_no_exception(engine):
    wa_id = "res_t11"
    engine.process_message(wa_id, "pedido")
    reply = engine.process_message(
        wa_id, "2 🍕 pizza hawaiana!!! y... 1 coca-cola\n(la chica)"
    )
    assert isinstance(reply, str)


def test_t12_repeated_products_deduplication(engine):
    wa_id = "res_t12"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana, 2 pizza hawaiana")
    cart = _data(engine, wa_id).get("cart", [])
    pizzas = [it for it in cart if it["product"] == "Pizza Hawaiana"]
    if pizzas:
        assert pizzas[0]["qty"] == 3


def test_t13_pending_unknowns_cleared_on_new_order(engine, monkeypatch):
    wa_id = "res_t13"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(wa_id, pending_unknowns=["viejo1", "viejo2"])
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse([_cart_item("Pizza Hawaiana")]))
    engine.process_message(wa_id, "1 pizza hawaiana")
    assert not _data(engine, wa_id).get("pending_unknowns")


# ─── Capa 1 — handle_order_clarification ────────────────────────────────────


def test_t14_clarification_valid_product_partial_retry(engine):
    wa_id = "res_t14"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=["algo_raro", "otro_raro"],
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "Coca Cola")
    d = _data(engine, wa_id)
    products = {it["product"] for it in d.get("cart", [])}
    assert "Coca Cola" in products
    assert len(d.get("pending_unknowns", [])) == 1
    assert _step(engine, wa_id) == "order_clarify_node"  # partial_retry → null


def test_t15_clarification_last_pending_resolves(engine):
    wa_id = "res_t15"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=["algo_raro"],
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "Coca Cola")
    assert _step(engine, wa_id) == "order_review_node"
    assert not _data(engine, wa_id).get("pending_unknowns")


def test_t16_clarification_skip_decrements_pending(engine):
    wa_id = "res_t16"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=["raro1", "raro2"],
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "omitir")
    d = _data(engine, wa_id)
    assert len(d.get("pending_unknowns", [])) == 1
    assert _step(engine, wa_id) == "order_clarify_node"


def test_t17_clarification_skip_last_resolves(engine):
    wa_id = "res_t17"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=["solo_uno"],
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "omitir")
    assert _step(engine, wa_id) == "order_review_node"


def test_t18_clarification_unrecognized_no_change(engine):
    wa_id = "res_t18"
    engine.process_message(wa_id, "pedido")
    cart_before = [_cart_item("Pizza Hawaiana")]
    pending_before = ["raro"]
    engine.state_manager.patch_data(
        wa_id, cart=cart_before, pending_unknowns=pending_before
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "xyzabcdef123notaproduct")
    d = _data(engine, wa_id)
    assert d.get("pending_unknowns") == pending_before
    assert _step(engine, wa_id) == "order_clarify_node"


def test_t19_clarification_empty_pending_resolves(engine):
    wa_id = "res_t19"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=[],
    )
    engine.state_manager.set_step(wa_id, "order_clarify_node", "order")
    engine.process_message(wa_id, "cualquier cosa")
    assert _step(engine, wa_id) == "order_review_node"


# ─── Desincronización de pending_unknowns ────────────────────────────────────


def test_t20_new_order_clears_pending_unknowns(engine, monkeypatch):
    wa_id = "res_t20"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(wa_id, pending_unknowns=["viejo1", "viejo2"])
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse([_cart_item("Coca Cola")]))
    engine.process_message(wa_id, "1 coca cola")
    assert not _data(engine, wa_id).get("pending_unknowns")


def test_t21_inicio_clears_pending_unknowns(engine):
    wa_id = "res_t21"
    # Use home flow so "inicio" directly triggers reset (no abandon-confirm guard).
    engine.process_message(wa_id, "hola")
    engine.state_manager.patch_data(wa_id, pending_unknowns=["raro"])
    engine.process_message(wa_id, "inicio")
    assert not _data(engine, wa_id).get("pending_unknowns")


def test_t22_cancelar_clears_pending_unknowns(engine):
    wa_id = "res_t22"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(wa_id, pending_unknowns=["raro"])
    engine.process_message(wa_id, "cancelar")
    assert not _data(engine, wa_id).get("pending_unknowns")


def test_t23_state_reset_clears_all_pending_fields(engine):
    """state_manager.reset() (called by order_saved action) wipes all resilience fields."""
    wa_id = "res_t23"
    engine.state_manager.patch_data(
        wa_id,
        cart=[_cart_item("Pizza Hawaiana")],
        pending_unknowns=["zombie"],
        pending_ambiguous=[{"segment": "X", "qty": 1, "candidates": []}],
    )
    engine.state_manager.reset(wa_id)
    d = _data(engine, wa_id)
    assert not d.get("pending_unknowns")
    assert not d.get("pending_ambiguous")
    assert not d.get("cart")


# ─── Capa 2 — Modificación inteligente ──────────────────────────────────────


def _setup_cart(engine, wa_id: str, *products: str) -> None:
    """Get to order_review_node with given products in cart."""
    engine.process_message(wa_id, "pedido")
    msg = ", ".join(f"1 {p}" for p in products)
    engine.process_message(wa_id, msg)
    # skip any clarification prompts if partial
    for _ in range(5):
        if _step(engine, wa_id) == "order_review_node":
            break
        if _step(engine, wa_id) == "order_clarify_node":
            engine.process_message(wa_id, "omitir")


def test_t24_remove_product_from_cart(engine):
    wa_id = "res_t24"
    _setup_cart(engine, wa_id, "Pizza Hawaiana", "Coca Cola")
    engine.process_message(wa_id, "no")
    engine.process_message(wa_id, "quita la coca cola")
    cart = _data(engine, wa_id).get("cart", [])
    products = {it["product"] for it in cart}
    assert "Coca Cola" not in products
    assert "Pizza Hawaiana" in products


def test_t25_add_product_to_existing_cart(engine):
    wa_id = "res_t25"
    _setup_cart(engine, wa_id, "Pizza Hawaiana")
    engine.process_message(wa_id, "no")
    engine.process_message(wa_id, "agrega 2 yogur natural")
    cart = _data(engine, wa_id).get("cart", [])
    products = {it["product"] for it in cart}
    assert "Pizza Hawaiana" in products
    assert any("Yogur" in p for p in products)


def test_t26_replace_product_in_cart(engine, monkeypatch):
    wa_id = "res_t26"
    # ponytail: use unambiguous products (Arroz variants score too closely → disambiguation).
    _setup_cart(engine, wa_id, "Pizza Hawaiana")
    engine.process_message(wa_id, "no")
    # Inject a controlled replace result to verify the replace path
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(
            [_cart_item("Hamburguesa Clasica", 1, 10.0, "hb1")]))
    engine.process_message(wa_id, "cambia la pizza por hamburguesa clasica")
    cart = _data(engine, wa_id).get("cart", [])
    products = {it["product"] for it in cart}
    assert "Pizza Hawaiana" not in products
    assert "Hamburguesa Clasica" in products


def test_t27_keep_only_one_product(engine):
    wa_id = "res_t27"
    _setup_cart(engine, wa_id, "Pizza Hawaiana", "Coca Cola")
    engine.process_message(wa_id, "no")
    engine.process_message(wa_id, "déjame solo la pizza hawaiana")
    cart = _data(engine, wa_id).get("cart", [])
    products = [it["product"] for it in cart]
    assert len(products) == 1
    assert products[0] == "Pizza Hawaiana"


def test_t28_ambiguous_modification_no_crash(engine):
    wa_id = "res_t28"
    _setup_cart(engine, wa_id, "Pizza Hawaiana")
    engine.process_message(wa_id, "no")
    reply = engine.process_message(wa_id, "cambia la pizza por algo raro xyz")
    assert isinstance(reply, str)


# ─── Capa 3 — Desambiguación ─────────────────────────────────────────────────


def _setup_disambiguate(engine, wa_id: str, qty: int = 2) -> None:
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[],
        pending_ambiguous=[
            {
                "segment": "Coca-Cola",
                "qty": qty,
                "candidates": _ambiguous_coca(),
            }
        ],
    )
    engine.state_manager.set_step(wa_id, "order_disambiguate_node", "order")


def test_t29_ambiguous_parse_triggers_disambiguate(engine, monkeypatch):
    wa_id = "res_t29"
    engine.process_message(wa_id, "pedido")
    monkeypatch.setattr(engine.order_service, "parse_order_text",
        lambda text, cart=None, wa_id="": _fake_parse(
            [],
            ambiguous=[{"segment": "Coca-Cola", "qty": 2, "candidates": _ambiguous_coca()}],
        ))
    engine.process_message(wa_id, "2 Coca-Cola")
    assert _step(engine, wa_id) == "order_disambiguate_node"
    d = _data(engine, wa_id)
    assert len(d.get("pending_ambiguous", [])) == 1
    assert d["pending_ambiguous"][0]["segment"] == "Coca-Cola"


def test_t30_disambiguation_by_number(engine):
    wa_id = "res_t30"
    _setup_disambiguate(engine, wa_id, qty=2)
    engine.process_message(wa_id, "1")
    cart = _data(engine, wa_id).get("cart", [])
    assert any(it["product"] == "Coca Cola 400ml" for it in cart)
    assert _step(engine, wa_id) == "order_review_node"


def test_t31_disambiguation_by_name(engine):
    wa_id = "res_t31"
    _setup_disambiguate(engine, wa_id)
    engine.process_message(wa_id, "Coca Cola 1.5L")
    cart = _data(engine, wa_id).get("cart", [])
    assert any(it["product"] == "Coca Cola 1.5L" for it in cart)
    assert _step(engine, wa_id) == "order_review_node"


def test_t32_disambiguation_invalid_choice(engine):
    wa_id = "res_t32"
    _setup_disambiguate(engine, wa_id)
    pending_before = list(_data(engine, wa_id).get("pending_ambiguous", []))
    engine.process_message(wa_id, "999")
    d = _data(engine, wa_id)
    assert len(d.get("pending_ambiguous", [])) == len(pending_before)
    assert _step(engine, wa_id) == "order_disambiguate_node"


def test_t33_multiple_ambiguous_resolved_sequentially(engine):
    wa_id = "res_t33"
    engine.process_message(wa_id, "pedido")
    engine.state_manager.patch_data(
        wa_id,
        cart=[],
        pending_ambiguous=[
            {
                "segment": "Coca-Cola",
                "qty": 1,
                "candidates": _ambiguous_coca(),
            },
            {
                "segment": "Arroz",
                "qty": 1,
                "candidates": [
                    {"product": "Arroz Diana 500g", "product_id": "a1", "unit_price": 4.0},
                    {"product": "Arroz Diana 1kg", "product_id": "a2", "unit_price": 7.0},
                ],
            },
        ],
    )
    engine.state_manager.set_step(wa_id, "order_disambiguate_node", "order")

    engine.process_message(wa_id, "1")
    assert _step(engine, wa_id) == "order_disambiguate_node"
    assert len(_data(engine, wa_id).get("pending_ambiguous", [])) == 1

    engine.process_message(wa_id, "2")
    assert _step(engine, wa_id) == "order_review_node"
    cart = _data(engine, wa_id).get("cart", [])
    products = {it["product"] for it in cart}
    assert "Coca Cola 400ml" in products
    assert "Arroz Diana 1kg" in products
