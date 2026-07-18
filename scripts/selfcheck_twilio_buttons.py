"""
Minimal self-check: WhatsApp button transport hygiene (no network).

Run: python scripts/selfcheck_twilio_buttons.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_transport_state(tc) -> None:
    tc._CONTENT_SID_CACHE.clear()
    tc._LAST_BUTTON_SEND.clear()


def main() -> None:
    import infrastructure.twilio_client as tc

    flow = json.loads((ROOT / "flows" / "restaurant_flow.json").read_text(encoding="utf-8"))
    home_btns = flow["states"]["home"]["nodes"]["home_node"]["buttons"]
    ids = [b["id"] for b in home_btns]
    assert ids == ["productos", "pedido"], f"home button ids unexpected: {ids}"

    webhook_src = (ROOT / "api" / "routes" / "whatsapp.py").read_text(encoding="utf-8")
    gateway_src = (ROOT / "chatbot" / "gateway.py").read_text(encoding="utf-8")
    assert "ButtonPayload" in webhook_src
    assert "ButtonPayload" in gateway_src
    assert "InteractiveData" in webhook_src
    assert "MessageSid" in webhook_src

    actions = [{"id": "productos", "title": "📖 Ver menú"}, {"id": "pedido", "title": "🍽️ Hacer pedido"}]
    body = "Hola welcome"

    with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACtest"), patch.object(
        tc, "TWILIO_AUTH_TOKEN", "tok"
    ), patch.object(tc, "TWILIO_WHATSAPP_FROM", "+573001000000"):
        _reset_transport_state(tc)

        # --- fingerprint reuse + account namespace ---
        fp = tc._content_fingerprint(
            "quick-reply",
            body,
            [{"title": "Ver menú", "id": "productos"}, {"title": "Hacer pedido", "id": "pedido"}],
        )
        key_a = tc._namespaced_cache_key(fp)
        assert key_a.startswith("ACtest:"), key_a
        with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACother"):
            key_b = tc._namespaced_cache_key(fp)
        assert key_a != key_b

        created: list[dict] = []
        probe_calls: list[str] = []

        def fake_get(url, **kwargs):
            sid = url.rstrip("/").split("/")[-1]
            probe_calls.append(sid)
            r = MagicMock()
            if sid == "HXdead":
                r.ok = False
                r.status_code = 404
            else:
                r.ok = True
                r.status_code = 200
            return r

        def fake_post(url, **kwargs):
            created.append(kwargs.get("json") or {})
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.json.return_value = {"sid": f"HX{len(created):04d}"}
            r.ok = True
            r.status_code = 201
            return r

        msg = MagicMock()
        msg.sid = "SMout1"
        msg.status = "sent"
        msg.error_code = None
        msg.from_ = "whatsapp:+573001000000"
        client = MagicMock()
        client.messages.create.return_value = msg
        client.messages.return_value.fetch.return_value = msg

        with patch.object(tc, "requests") as req, patch.object(tc, "Client", return_value=client), patch.object(
            tc, "_save_content_cache"
        ), patch.object(tc, "_load_content_cache"), patch.object(
            tc, "_CONTENT_CACHE_PATH", ROOT / "data" / "_selfcheck_cache.json"
        ):
            req.get.side_effect = fake_get
            req.post.side_effect = fake_post

            # 1) buttons → only quick-reply, no twilio/text
            sid1 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid1 == "SMout1"
            assert len(created) == 1
            types1 = created[0]["types"]
            assert list(types1.keys()) == ["twilio/quick-reply"]
            assert "twilio/text" not in types1
            titles = [a["title"] for a in types1["twilio/quick-reply"]["actions"]]
            assert titles == ["Ver menú", "Hacer pedido"], titles
            assert [a["id"] for a in types1["twilio/quick-reply"]["actions"]] == [
                "productos",
                "pedido",
            ]

            # 2) fingerprint reuse (probe ok) — no second CREATE
            tc._CONTENT_SID_CACHE[key_a] = "HXalive"
            sid2 = tc.send_whatsapp_buttons("+573009998877", body, actions)
            assert sid2 == "SMout1"
            assert len(created) == 1
            assert "HXalive" in probe_calls

            # 3) probe 404 → drop + recreate
            _reset_transport_state(tc)
            created.clear()
            probe_calls.clear()
            tc._CONTENT_SID_CACHE[key_a] = "HXdead"
            sid3 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid3 == "SMout1"
            assert "HXdead" not in tc._CONTENT_SID_CACHE.values()
            assert len(created) == 1
            assert created[0]["types"] == types1

            # 4) anti-stack: same to + same fp within window → no second create/send
            create_count = client.messages.create.call_count
            sid4 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid4 == sid3
            assert client.messages.create.call_count == create_count
            assert len(created) == 1

            # 5) list stays list-picker (+ cache key)
            created.clear()
            rows = [
                {"id": "__cat__A", "title": "Cat A", "description": ""},
                {"id": "__cat__B", "title": "Cat B", "description": ""},
            ]
            sid_list = tc.send_whatsapp_list("+573001112233", "Menú", rows)
            assert sid_list == "SMout1"
            assert len(created) == 1
            assert list(created[0]["types"].keys()) == ["twilio/list-picker"]
            assert "twilio/quick-reply" not in created[0]["types"]

    # 6) gateway prefers ButtonPayload over Body
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
        admin_service.canonical_wa_id.side_effect = lambda a, b=None: a or ""
        flow_engine = FakeEngine()
        user_service = MagicMock()
        blocked_cache = MagicMock()
        blocked_cache.is_blocked.return_value = False

    with patch("chatbot.gateway.get_bot_context", return_value=FakeCtx()), patch(
        "chatbot.gateway.business_scope"
    ), patch("chatbot.gateway.notify_svc.is_admin_sender", return_value=False), patch(
        "chatbot.gateway.schedule_client_message_log"
    ), patch("chatbot.gateway._normalize_reply", side_effect=lambda r: r), patch(
        "chatbot.gateway.get_prompt", return_value="x"
    ):
        FakeCtx.admin_service.canonical_wa_id = MagicMock(side_effect=lambda a, b=None: a or "")
        for payload_id in ("productos", "pedido"):
            captured.clear()
            handle_incoming_message(
                {
                    "phone": "573001112233",
                    "from_number": "whatsapp:+573001112233",
                    "message": "ignored body",
                    "business_id": None,
                    "metadata": {
                        "ButtonPayload": payload_id,
                        "ButtonText": payload_id,
                        "Body": "ignored body",
                        "MessageSid": "SMin1",
                    },
                }
            )
            assert captured.get("body") == payload_id, captured

    print("selfcheck_twilio_buttons: OK")


if __name__ == "__main__":
    main()
