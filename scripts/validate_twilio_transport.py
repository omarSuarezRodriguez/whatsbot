"""
Static validator: ARCHITECTURE_LAW.md invariant 11 (WhatsApp transport).

No network. Fails loud if transport hygiene regresses.

Run: python scripts/validate_twilio_transport.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> None:
    tc_path = ROOT / "infrastructure" / "twilio_client.py"
    fe_path = ROOT / "chatbot" / "app" / "core" / "flow_engine.py"
    webhook_path = ROOT / "api" / "routes" / "whatsapp.py"
    gateway_path = ROOT / "chatbot" / "gateway.py"
    flow_path = ROOT / "flows" / "restaurant_flow.json"
    start_path = ROOT / "start.ps1"

    tc = tc_path.read_text(encoding="utf-8")
    fe = fe_path.read_text(encoding="utf-8")
    webhook = webhook_path.read_text(encoding="utf-8")
    gateway = gateway_path.read_text(encoding="utf-8")
    flow = json.loads(flow_path.read_text(encoding="utf-8"))
    start = start_path.read_text(encoding="utf-8") if start_path.is_file() else ""

    # --- LAW 11.6 anti-stack ~5 min + disk ---
    if not re.search(r"_BUTTON_ANTISTACK_S\s*=\s*300(\.0)?\b", tc):
        fail("LAW 11.6: button anti-stack must be ~300s")
    if "twilio_button_antistack.json" not in tc:
        fail("anti-stack must persist to data/twilio_button_antistack.json")
    if "_atomic_write_json" not in tc:
        fail("disk writes must use atomic temp+replace")
    # LAW 11.4: quick-reply reuses HX (not cache_key=None CREATE flood)
    if re.search(
        r"send_whatsapp_buttons[\s\S]*?cache_key\s*=\s*None",
        tc,
    ):
        fail("LAW 11.4: quick-reply must reuse HX (not cache_key=None)")
    # Multi-button: one Content with all JSON actions (newest msg has every chip)
    if "for action in safe_actions:" in tc and '_send_one("👇"' in tc:
        fail("do not split chips across msgs (older chip = no webhook / LAW 11.11)")
    if '"actions": safe_actions' not in tc and "'actions': safe_actions" not in tc:
        fail("quick-reply Content must include full safe_actions list from JSON")
    if 'str(b.get("title", ""))[:20]' not in tc and "_wire_btn_title" not in tc:
        fail("button titles must come from JSON map (truncate ≤20)")
    if "_wire_btn_title" not in tc:
        fail("use _wire_btn_title (strip emoji, keep accents) for quick-reply")
    if "text fallback" in tc:
        fail("do not text-fallback button sends (strips chips from hola)")
    if "deliver_reply QUICK-REPLY" not in tc and "JSON buttons, not list" not in tc:
        fail("deliver_reply must separate JSON buttons (quick-reply) from list")
    if "deliver_reply LIST-PICKER" not in tc and "JSON list" not in tc:
        fail("deliver_reply must log list-picker path for JSON list")

    # --- LAW 11.1 / 11.3–11.5 ---
    if "twilio/quick-reply" not in tc:
        fail("buttons must use twilio/quick-reply")
    if "twilio/list-picker" not in tc:
        fail("lists must use twilio/list-picker")
    if "_content_fingerprint" not in tc or "_namespaced_cache_key" not in tc:
        fail("HX fingerprint + account namespace required")
    if "twilio_content_cache.json" not in tc:
        fail("HX cache path missing")
    if "content.twilio.com/v1/Content/" not in tc:
        fail("probe GET before HX reuse required")

    # --- LAW 11.7: simplify wire titles; ids from JSON intact ---
    if "def _btn_title" not in tc:
        fail("LAW 11.7: _btn_title helper required")
    if 'str(b.get("id"' not in tc and "b.get('id'" not in tc:
        fail("button ids must come from JSON map")

    # --- LAW 11.8 From pin ---
    if "TWILIO_WHATSAPP_FROM" not in tc:
        fail("From pin via TWILIO_WHATSAPP_FROM required")
    if "+1555" not in tc:
        fail("phantom +1555 guard missing")

    # --- LAW §7 / 11.10 inbound ---
    for label, src in (("webhook", webhook), ("gateway", gateway)):
        if "ButtonPayload" not in src:
            fail(f"{label} must log ButtonPayload")
    if "InteractiveData" not in webhook:
        fail("webhook must mention InteractiveData")
    if "ButtonText" not in gateway:
        fail("gateway must read ButtonText")
    # Prefer ButtonPayload id for reply buttons (LAW §7); Body/ButtonText fallback
    gflat = gateway.replace("\n", " ")
    if "button_payload or body or button_text" not in gflat:
        fail("gateway must prefer ButtonPayload then Body/ButtonText for buttons")
    if "list_payload" not in gateway:
        fail("gateway must still use list_payload for list replies")

    # --- LAW: transport not in FlowEngine ---
    for banned in (
        "twilio/quick-reply",
        "twilio/list-picker",
        "twilio_content_cache",
        "_BUTTON_ANTISTACK",
        "ContentSid",
    ):
        if banned in fe:
            fail(f"FlowEngine must not own transport ({banned})")

    # --- LAW: start.ps1 must NOT wipe HX/antistack cache every boot ---
    for banned in ("twilio_content_cache", "twilio_button_antistack"):
        if banned in start and re.search(
            rf"Remove-Item.*{banned}|rm\s+.*{banned}|unlink.*{banned}",
            start,
            re.I,
        ):
            fail(f"start.ps1 must not delete {banned} on every boot (causes HX flood)")

    # --- JSON map: home = buttons (reply); pad fixes action[0] fantasma ---
    home = flow["states"]["home"]["nodes"]["home_node"]
    if "buttons" not in home:
        fail("home_node must declare buttons (reply chips)")
    if home.get("list", {}).get("source") == "static":
        fail("home must stay reply buttons, not static list")
    ids = [b["id"] for b in home["buttons"]]
    if ids != ["productos", "pedido"]:
        fail(f"home button ids must be productos/pedido, got {ids}")
    if home.get("list", {}).get("source") == "static":
        fail("home must stay reply buttons, not static list")
    opts = home["options"]
    if opts.get("productos") != "productos.productos_node":
        fail("home options productos routing broken")
    if opts.get("pedido") != "order.order_start_node":
        fail("home options pedido routing broken")
    prod = flow["states"]["productos"]["nodes"]["productos_node"]
    if not isinstance(prod.get("list"), dict):
        fail("productos_node must declare list (categories) — not buttons-as-list")
    gc = flow.get("meta", {}).get("global_commands", {})
    if gc.get("productos") != "productos.productos_node":
        fail("global_commands productos routing broken")

    # --- data/ gitignored ---
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if not re.search(r"(?m)^data/?$", gitignore):
        fail("data/ must be gitignored (HX + antistack caches)")

    print("validate_twilio_transport: OK")


if __name__ == "__main__":
    main()
