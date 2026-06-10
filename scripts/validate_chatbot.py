"""Validate chatbot gateway (Fase 2) — run from final_system/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(label: str) -> None:
    print(f"  OK  {label}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  FAIL {label}" + (f" - {detail}" if detail else ""))


def main() -> int:
    print("=== validate_chatbot (Fase 2+) ===\n")
    failures = 0

    try:
        from chatbot.gateway import handle_incoming_message
        from chatbot.runtime import get_bot_context, reset_bot_context

        _ok("import chatbot.gateway")
    except Exception as exc:
        _fail("import chatbot.gateway", str(exc))
        print(f"\n=== Resultado: {1} fallo(s) ===")
        return 1

    reset_bot_context()
    try:
        get_bot_context(start_background=False)
        _ok("get_bot_context()")
    except Exception as exc:
        _fail("get_bot_context()", str(exc))
        failures += 1

    # Cliente: saludo
    try:
        result = handle_incoming_message(
            {
                "phone": "573009999999",
                "message": "hola",
                "profile_name": "Test User",
                "channel": "whatsapp",
            }
        )
        text = result.get("response_text", "")
        if not text:
            _fail("hola -> response_text", "vacio")
            failures += 1
        elif result.get("is_admin"):
            _fail("hola -> is_admin", "deberia ser False")
            failures += 1
        elif result.get("blocked"):
            _fail("hola -> blocked", "deberia ser False")
            failures += 1
        else:
            _ok(f"hola -> respuesta ({len(str(text))} chars)")
    except Exception as exc:
        _fail("handle_incoming_message(hola)", str(exc))
        failures += 1

    # Cliente: comando menu
    try:
        result = handle_incoming_message(
            {
                "wa_id": "573009999999",
                "body": "menu",
            }
        )
        text = str(result.get("response_text", "")).lower()
        if "menu" in text or "carta" in text or "pizza" in text or "$" in text:
            _ok("menu -> incluye contenido de menu")
        else:
            _fail("menu -> response_text", text[:120])
            failures += 1
    except Exception as exc:
        _fail("handle_incoming_message(menu)", str(exc))
        failures += 1

    # business_id opcional (passthrough)
    try:
        result = handle_incoming_message(
            {
                "phone": "573009999999",
                "message": "inicio",
                "business_id": "biz-test-001",
            }
        )
        if result.get("business_id") == "biz-test-001":
            _ok("business_id passthrough")
        else:
            _fail("business_id", repr(result.get("business_id")))
            failures += 1
    except Exception as exc:
        _fail("business_id passthrough", str(exc))
        failures += 1

    # Admin no reconocido (si ADMIN configurado en .env)
    try:
        from app.config import ADMIN_WHATSAPP_NUMBER

        if ADMIN_WHATSAPP_NUMBER:
            digits = "".join(c for c in ADMIN_WHATSAPP_NUMBER if c.isdigit())[-10:]
            admin_phone = f"57{digits[-10:]}" if len(digits) >= 10 else digits
            result = handle_incoming_message(
                {
                    "phone": admin_phone,
                    "message": "hola admin test",
                }
            )
            if result.get("is_admin") and result.get("response_text"):
                _ok("admin -> is_admin + respuesta")
            else:
                _fail(
                    "admin flow",
                    f"is_admin={result.get('is_admin')} text={bool(result.get('response_text'))}",
                )
                failures += 1
        else:
            _ok("admin skip (ADMIN_WHATSAPP_NUMBER no configurado)")
    except Exception as exc:
        _fail("admin flow", str(exc))
        failures += 1

    print(f"\n=== Resultado: {failures} fallo(s) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
