"""
Transport hygiene self-check (no real Twilio network).

LAW: buttons = quick-reply body+chips; list = list-picker.
Home: productos + pedido (titles from JSON, incl. emoji).

Run: python scripts/selfcheck_twilio_buttons.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_transport_state(tc) -> None:
    tc._CONTENT_SID_CACHE.clear()
    tc._LAST_BUTTON_SEND.clear()
    tc._ANTISTACK_LOADED = True


def main() -> None:
    import infrastructure.twilio_client as tc

    flow = json.loads(
        (ROOT / "flows" / "restaurant_flow.json").read_text(encoding="utf-8")
    )
    home = flow["states"]["home"]["nodes"]["home_node"]
    assert "buttons" in home
    assert [b["id"] for b in home["buttons"]] == ["productos", "pedido"]
    opts = home["options"]
    assert opts["productos"] == "productos.productos_node"
    assert opts["pedido"] == "order.order_start_node"
    prod = flow["states"]["productos"]["nodes"]["productos_node"]
    assert isinstance(prod.get("list"), dict)

    assert tc._BUTTON_ANTISTACK_S == 300.0

    actions = [
        {"id": "productos", "title": "📖 Ver menú"},
        {"id": "pedido", "title": "🍽️ Hacer pedido"},
    ]
    body = "Hola welcome"
    wire_actions = [
        {"title": tc._wire_btn_title("📖 Ver menú"), "id": "productos"},
        {"title": tc._wire_btn_title("🍽️ Hacer pedido"), "id": "pedido"},
    ]
    assert wire_actions[0]["title"] == "Ver menú"
    assert wire_actions[1]["title"] == "Hacer pedido"

    with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACtest"), patch.object(
        tc, "TWILIO_AUTH_TOKEN", "tok"
    ), patch.object(tc, "TWILIO_WHATSAPP_FROM", "+573001000000"):
        _reset_transport_state(tc)
        fp = tc._content_fingerprint("quick-reply", body, wire_actions)
        stack_key = tc._antistack_key("573001112233")
        btn_key = tc._namespaced_cache_key(fp)

        created: list[dict] = []
        probe_calls: list[str] = []

        def fake_get(url, **kwargs):
            sid = url.rstrip("/").split("/")[-1]
            probe_calls.append(sid)
            r = MagicMock()
            r.ok = sid != "HXdead"
            r.status_code = 404 if sid == "HXdead" else 200
            return r

        def fake_post(url, **kwargs):
            created.append(kwargs.get("json") or {})
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.json.return_value = {"sid": f"HX{len(created):04d}"}
            r.ok = True
            return r

        msg = MagicMock()
        msg.sid = "SMout1"
        msg.status = "sent"
        msg.error_code = None
        msg.from_ = "whatsapp:+573001000000"
        client = MagicMock()
        client.messages.create.return_value = msg
        client.messages.return_value.fetch.return_value = msg

        cache_path = ROOT / "data" / "_selfcheck_cache.json"
        stack_path = ROOT / "data" / "_selfcheck_antistack.json"
        for p in (cache_path, stack_path):
            p.unlink(missing_ok=True)

        with patch.object(tc, "requests") as req, patch.object(
            tc, "Client", return_value=client
        ), patch.object(tc, "_CONTENT_CACHE_PATH", cache_path), patch.object(
            tc, "_ANTISTACK_PATH", stack_path
        ):
            req.get.side_effect = fake_get
            req.post.side_effect = fake_post

            sid1 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid1 == "SMout1"
            assert len(created) == 1
            assert list(created[0]["types"].keys()) == ["twilio/quick-reply"]
            acts = created[0]["types"]["twilio/quick-reply"]["actions"]
            assert [a["id"] for a in acts] == ["productos", "pedido"]
            assert acts[0]["title"] == "Ver menú"
            assert acts[1]["title"] == "Hacer pedido"
            assert created[0]["types"]["twilio/quick-reply"]["body"] == body
            assert btn_key in tc._CONTENT_SID_CACHE

            n = len(created)
            probe_calls.clear()
            assert tc.send_whatsapp_buttons("+573009998877", body, actions) == "SMout1"
            assert len(created) == n
            assert probe_calls

            _reset_transport_state(tc)
            created.clear()
            sid3 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            cc = client.messages.create.call_count
            assert tc.send_whatsapp_buttons("+573001112233", body, actions) == sid3
            assert client.messages.create.call_count == cc

            tc._LAST_BUTTON_SEND[stack_key] = (fp, time.time() - 301.0, sid3)
            n = len(created)
            probe_calls.clear()
            assert tc.send_whatsapp_buttons("+573001112233", body, actions) == "SMout1"
            assert len(created) == n
            assert probe_calls

            created.clear()
            rows = [
                {"id": "__cat__A", "title": "Cat A", "description": ""},
                {"id": "__cat__B", "title": "Cat B", "description": ""},
            ]
            assert tc.send_whatsapp_list("+573001112233", "Menú", rows) == "SMout1"
            assert list(created[0]["types"].keys()) == ["twilio/list-picker"]

        for p in (cache_path, stack_path):
            p.unlink(missing_ok=True)

    from chatbot.gateway import handle_incoming_message

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
        for body, payload, expect in (
            ("Confirmar", "confirmar", "confirmar"),
            ("Ver menú", "productos", "productos"),
            ("Hacer pedido", "pedido", "pedido"),
        ):
            captured.clear()
            handle_incoming_message(
                {
                    "phone": "573001112233",
                    "from_number": "whatsapp:+573001112233",
                    "message": body,
                    "business_id": None,
                    "metadata": {
                        "ButtonPayload": payload,
                        "ButtonText": body,
                        "Body": body,
                        "MessageSid": "SMin",
                    },
                }
            )
            assert captured.get("body") == expect, captured

    print("selfcheck_twilio_buttons: OK")


if __name__ == "__main__":
    main()
