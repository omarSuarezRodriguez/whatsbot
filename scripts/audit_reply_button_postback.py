"""Audit reply-button postback assumptions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    flow = json.loads((ROOT / "flows" / "restaurant_flow.json").read_text(encoding="utf-8"))
    home = flow["states"]["home"]["nodes"]["home_node"]
    tc = (ROOT / "infrastructure" / "twilio_client.py").read_text(encoding="utf-8")
    assert [b["id"] for b in home["buttons"]] == ["pedido", "productos"]
    assert "_wire_btn_title" in tc
    assert 'btn_body = "Selecciona una opcion:"' not in tc
    print("OK: home buttons pedido then productos (menu last = postback slot)")
    print("NOTE: Twilio gets Hacer pedido; Ver menu often missing on this chat tonight")
    print("audit_reply_button_postback: done")


if __name__ == "__main__":
    main()
