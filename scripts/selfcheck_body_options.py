"""
Verify reply-button ButtonPayload/Body → JSON options / free_text (no Twilio).

Run: python scripts/selfcheck_body_options.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CHATBOT = ROOT / "chatbot"
if str(CHATBOT) not in sys.path:
    sys.path.insert(0, str(CHATBOT))


def main() -> None:
    from app.utils.validators import normalize_text
    from chatbot.gateway import handle_incoming_message
    from chatbot.runtime import get_bot_context
    from chatbot.business_context import business_scope
    from infrastructure.twilio_client import _list_row_key

    flow = json.loads((ROOT / "flows" / "restaurant_flow.json").read_text(encoding="utf-8"))
    home = flow["states"]["home"]["nodes"]["home_node"]
    assert "buttons" in home
    assert [b["id"] for b in home["buttons"]] == ["productos", "pedido"]
    prod = flow["states"]["productos"]["nodes"]["productos_node"]
    assert isinstance(prod.get("list"), dict)
    assert normalize_text("Ver menu") == "ver menu"
    assert _list_row_key("🍛 Platos principales") == "platos principales"

    captured: dict = {}

    class FakeEngine:
        productos_service = MagicMock()
        productos_service.get_producto_by_id.return_value = None

        def process_message(self, wa_id, body):
            captured["body"] = body
            return "ok"

        def get_current_buttons(self, wa_id):
            return []

        def get_current_list(self, wa_id):
            return None

    class FakeCtx:
        admin_service = MagicMock()
        flow_engine = FakeEngine()
        user_service = MagicMock()
        blocked_cache = MagicMock()
        blocked_cache.is_blocked.return_value = False

    FakeCtx.admin_service.canonical_wa_id = MagicMock(side_effect=lambda a, b=None: a or "")

    with patch("chatbot.gateway.get_bot_context", return_value=FakeCtx()), patch(
        "chatbot.gateway.business_scope"
    ), patch("chatbot.gateway.notify_svc.is_admin_sender", return_value=False), patch(
        "chatbot.gateway.schedule_client_message_log"
    ), patch("chatbot.gateway._normalize_reply", side_effect=lambda r: r), patch(
        "chatbot.gateway.get_prompt", return_value="x"
    ):
        # ButtonPayload id preferred (LAW §7) — same for all reply buttons
        for body, payload, expect in (
            ("Ver menú", "productos", "productos"),
            ("Hacer pedido", "pedido", "pedido"),
            ("Confirmar", "confirmar", "confirmar"),
            ("Domicilio", "domicilio", "domicilio"),
        ):
            captured.clear()
            handle_incoming_message(
                {
                    "phone": "57300",
                    "message": body,
                    "metadata": {
                        "Body": body,
                        "ButtonPayload": payload,
                        "ButtonText": body,
                    },
                }
            )
            assert captured["body"] == expect, (body, captured)

    wa = "selfcheck_body_options_wa"
    ctx = get_bot_context(start_background=False)
    fe = ctx.flow_engine
    cart = [
        {
            "product_id": "1",
            "product": "Bandeja Paisa",
            "nombre": "Bandeja Paisa",
            "precio": 20000,
            "unit_price": 20000,
            "qty": 1,
            "subtotal": 20000,
        }
    ]

    # Same motor path as Hacer pedido: payload id OR body label
    cases = [
        ("home", "home_node", "productos", "productos_node"),
        ("home", "home_node", "pedido", "order_start_node"),
        ("home", "home_node", "Ver menu", "productos_node"),
        ("home", "home_node", "Hacer pedido", "order_start_node"),
        ("order", "order_review_node", "confirmar", "order_delivery_node"),
        ("order", "order_review_node", "Confirmar", "order_delivery_node"),
        ("order", "order_review_node", "modificar", "order_modify_node"),
        ("order", "order_delivery_node", "domicilio", "order_address_node"),
        ("order", "order_delivery_node", "Domicilio", "order_address_node"),
    ]

    with business_scope("default"):
        for flow_name, step, body, expect in cases:
            fe.state_manager.reset(wa)
            fe.state_manager.set_step(wa, step, flow_name)
            if "order" in flow_name:
                fe.state_manager.patch_data(wa, cart=list(cart))
            fe.process_message(wa, body)
            st = fe.state_manager.get(wa)
            assert st.get("step") == expect, (body, st.get("step"), expect)

        fe.state_manager.reset(wa)
        fe.state_manager.set_step(wa, "productos_node", "productos")
        cats = fe.productos_service.get_categories()
        assert cats
        wire = f"__cat__{_list_row_key(cats[0])}"
        fe.process_message(wa, wire)
        st = fe.state_manager.get(wa)
        assert st.get("step") == "productos_category_node", st
        assert st.get("data", {}).get("selected_category") == cats[0], st

        # Abandon + Ver menu / productos leaves to menu
        fe.state_manager.reset(wa)
        fe.state_manager.set_step(wa, "order_review_node", "order")
        fe.state_manager.patch_data(
            wa, cart=list(cart), awaiting_abandon_confirm=True
        )
        fe.process_message(wa, "productos")
        st = fe.state_manager.get(wa)
        assert st.get("step") == "productos_node", st

        fe.state_manager.reset(wa)
        fe.state_manager.set_step(wa, "order_review_node", "order")
        fe.state_manager.patch_data(
            wa, cart=list(cart), awaiting_abandon_confirm=True
        )
        btns = fe.get_current_buttons(wa)
        assert [b.get("id") for b in btns] == ["continuar", "cancelar"]

        fe.process_message(wa, "pedido")
        st = fe.state_manager.get(wa)
        assert st.get("step") == "order_review_node", st

    print("selfcheck_body_options: OK")


if __name__ == "__main__":
    main()
