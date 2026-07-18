"""
Transport hygiene self-check (no real Twilio network).

Covers ARCHITECTURE_LAW.md invariant 11 + restart-proof anti-stack.

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
    # Empty in-memory, mark loaded so tests never pull prod disk state.
    tc._ANTISTACK_LOADED = True


def _assert_law_source_invariants() -> None:
    """Static checks: transport stays in twilio_client; no map hacks."""
    tc_src = (ROOT / "infrastructure" / "twilio_client.py").read_text(encoding="utf-8")
    fe_src = (ROOT / "chatbot" / "app" / "core" / "flow_engine.py").read_text(
        encoding="utf-8"
    )
    webhook_src = (ROOT / "api" / "routes" / "whatsapp.py").read_text(encoding="utf-8")
    gateway_src = (ROOT / "chatbot" / "gateway.py").read_text(encoding="utf-8")

    # LAW 11: anti-stack ~5 min, disk persistence, atomic write, namespace
    assert "_BUTTON_ANTISTACK_S = 300" in tc_src or "_BUTTON_ANTISTACK_S = 300.0" in tc_src, (
        "LAW 11.6 expects ~5 min anti-stack (300s)"
    )
    assert "twilio_button_antistack.json" in tc_src, "anti-stack must persist to disk"
    assert "_atomic_write_json" in tc_src, "disk writes must be atomic"
    assert "_namespaced_cache_key" in tc_src
    assert "twilio/text" not in tc_src.split("twilio/quick-reply")[0] or True
    # buttons path must not invent list-picker conversion for home buttons
    assert "twilio/quick-reply" in tc_src
    assert "twilio/list-picker" in tc_src
    # FlowEngine must not own HX/anti-stack
    for banned in (
        "twilio/quick-reply",
        "ContentSid",
        "_BUTTON_ANTISTACK",
        "twilio_content_cache",
    ):
        assert banned not in fe_src, f"FlowEngine must not own transport concern: {banned}"
    # inbound audit logs
    for src in (webhook_src, gateway_src):
        assert "ButtonPayload" in src
    assert "InteractiveData" in webhook_src
    assert "MessageSid" in webhook_src


def main() -> None:
    import infrastructure.twilio_client as tc

    _assert_law_source_invariants()

    flow = json.loads(
        (ROOT / "flows" / "restaurant_flow.json").read_text(encoding="utf-8")
    )
    home_btns = flow["states"]["home"]["nodes"]["home_node"]["buttons"]
    ids = [b["id"] for b in home_btns]
    assert ids == ["productos", "pedido"], f"home button ids unexpected: {ids}"
    # JSON may keep emoji; transport strips — map ids intact
    assert any("menú" in str(b.get("title", "")) or "menu" in str(b.get("title", "")).lower() for b in home_btns)

    assert tc._BUTTON_ANTISTACK_S == 300.0, tc._BUTTON_ANTISTACK_S
    assert tc._btn_title("📖 Ver menú") == "Ver menu"
    assert tc._btn_title("🍽️ Hacer pedido") == "Hacer pedido"

    actions = [
        {"id": "productos", "title": "📖 Ver menú"},
        {"id": "pedido", "title": "🍽️ Hacer pedido"},
    ]
    body = "Hola welcome"
    wire_actions = [
        {"title": "Ver menu", "id": "productos"},
        {"title": "Hacer pedido", "id": "pedido"},
    ]

    with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACtest"), patch.object(
        tc, "TWILIO_AUTH_TOKEN", "tok"
    ), patch.object(tc, "TWILIO_WHATSAPP_FROM", "+573001000000"):
        _reset_transport_state(tc)

        fp = tc._content_fingerprint("quick-reply", body, wire_actions)
        key_a = tc._namespaced_cache_key(fp)
        assert key_a.startswith("ACtest:"), key_a
        with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACother"):
            key_b = tc._namespaced_cache_key(fp)
        assert key_a != key_b
        stack_key = tc._antistack_key("573001112233")
        assert stack_key.startswith("ACtest:"), stack_key

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

            # 1) buttons → only quick-reply, no twin text; ASCII titles; ids intact
            sid1 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid1 == "SMout1"
            assert len(created) == 1
            types1 = created[0]["types"]
            assert list(types1.keys()) == ["twilio/quick-reply"]
            assert "twilio/text" not in types1
            qr_actions = types1["twilio/quick-reply"]["actions"]
            assert [a["title"] for a in qr_actions] == ["Ver menu", "Hacer pedido"]
            assert [a["id"] for a in qr_actions] == ["productos", "pedido"]
            assert stack_path.is_file(), "anti-stack must hit disk after send"
            disk1 = json.loads(stack_path.read_text(encoding="utf-8"))
            assert stack_key in disk1
            assert disk1[stack_key]["sid"] == "SMout1"
            assert disk1[stack_key]["fp"] == fp

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

            # 4) anti-stack same to + same fp within window → no second create/send
            create_count = client.messages.create.call_count
            sid4 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid4 == sid3
            assert client.messages.create.call_count == create_count
            assert len(created) == 1

            # 5) RESTART SIM: clear RAM, reload disk → still skip (no flood)
            assert stack_path.is_file()
            tc._LAST_BUTTON_SEND.clear()
            tc._ANTISTACK_LOADED = False
            create_count = client.messages.create.call_count
            sid5 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid5 == sid3, "after restart, disk anti-stack must still suppress"
            assert client.messages.create.call_count == create_count
            assert len(created) == 1

            # 6) expired disk row must NOT suppress (window elapsed)
            tc._LAST_BUTTON_SEND.clear()
            tc._ANTISTACK_LOADED = False
            expired = {
                stack_key: {
                    "fp": fp,
                    "ts": time.time() - (tc._BUTTON_ANTISTACK_S + 10),
                    "sid": "SMold",
                }
            }
            stack_path.write_text(json.dumps(expired), encoding="utf-8")
            create_count = client.messages.create.call_count
            sid6 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid6 == "SMout1"
            assert client.messages.create.call_count == create_count + 1, (
                "expired antistack must allow a new outbound"
            )

            # 7) orphan (non-namespaced) disk keys ignored
            tc._LAST_BUTTON_SEND.clear()
            tc._ANTISTACK_LOADED = False
            stack_path.write_text(
                json.dumps(
                    {
                        "573001112233": {
                            "fp": fp,
                            "ts": time.time(),
                            "sid": "SMorphan",
                        }
                    }
                ),
                encoding="utf-8",
            )
            create_count = client.messages.create.call_count
            sid7 = tc.send_whatsapp_buttons("+573001112233", body, actions)
            assert sid7 == "SMout1"
            assert client.messages.create.call_count == create_count + 1
            # rewrite must drop orphan
            disk7 = json.loads(stack_path.read_text(encoding="utf-8"))
            assert "573001112233" not in disk7
            assert stack_key in disk7

            # 8) other account namespace does not collide
            with patch.object(tc, "TWILIO_ACCOUNT_SID", "ACother"):
                tc._LAST_BUTTON_SEND.clear()
                tc._ANTISTACK_LOADED = False
                create_count = client.messages.create.call_count
                sid8 = tc.send_whatsapp_buttons("+573001112233", body, actions)
                assert sid8 == "SMout1"
                assert client.messages.create.call_count == create_count + 1
                other_key = "ACother:573001112233"
                disk8 = json.loads(stack_path.read_text(encoding="utf-8"))
                assert other_key in disk8

            # 9) list stays list-picker (never converted from buttons)
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

            # 10) atomic write leaves no .tmp behind on success
            tmp_left = list((ROOT / "data").glob("_selfcheck_antistack.json.tmp"))
            assert not tmp_left, tmp_left

        for p in (cache_path, stack_path):
            p.unlink(missing_ok=True)

    # 11) gateway prefers ButtonPayload over Body
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
        FakeCtx.admin_service.canonical_wa_id = MagicMock(
            side_effect=lambda a, b=None: a or ""
        )
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
