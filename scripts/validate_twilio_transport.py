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
        fail("anti-stack window must be 300s (~5 min per LAW 11.6)")
    if "twilio_button_antistack.json" not in tc:
        fail("anti-stack must persist to data/twilio_button_antistack.json")
    if "_atomic_write_json" not in tc:
        fail("disk writes must use atomic temp+replace")
    if "_ensure_antistack_loaded" not in tc or "_save_antistack" not in tc:
        fail("anti-stack load/save helpers missing")

    # --- LAW 11.3–11.5 HX hygiene ---
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

    # --- LAW 11.7 titles presentation only ---
    if "_btn_title" not in tc:
        fail("_btn_title missing (emoji/accent strip at wire)")

    # --- LAW 11.8 From pin ---
    if "TWILIO_WHATSAPP_FROM" not in tc:
        fail("From pin via TWILIO_WHATSAPP_FROM required")
    if "+1555" not in tc:
        fail("phantom +1555 guard missing")

    # --- LAW 11.10 inbound logs ---
    for label, src in (("webhook", webhook), ("gateway", gateway)):
        if "ButtonPayload" not in src:
            fail(f"{label} must log/prefer ButtonPayload")
    if "InteractiveData" not in webhook:
        fail("webhook must mention InteractiveData")

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

    # --- JSON map intact: home buttons ids ---
    home_btns = flow["states"]["home"]["nodes"]["home_node"]["buttons"]
    ids = [b["id"] for b in home_btns]
    if ids != ["productos", "pedido"]:
        fail(f"home button ids must stay productos/pedido, got {ids}")
    opts = flow["states"]["home"]["nodes"]["home_node"]["options"]
    if opts.get("productos") != "productos.productos_node":
        fail("home options productos routing broken")
    if opts.get("pedido") != "order.order_start_node":
        fail("home options pedido routing broken")
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
