"""Self-check: WhatsApp Flows crypto + JSON node + engine flag."""

from __future__ import annotations

import json
import os
import sys
from base64 import b64encode
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CHATBOT = ROOT / "chatbot"
if str(CHATBOT) not in sys.path:
    sys.path.insert(0, str(CHATBOT))

os.chdir(ROOT)


def _node_declared() -> None:
    flow_path = ROOT / "flows" / "restaurant_flow.json"
    raw = json.loads(flow_path.read_text(encoding="utf-8"))
    node = raw["states"]["order"]["nodes"]["productos_whatsapp_flow_button_node"]
    assert "wa_flow" in node
    assert node.get("action_on_input") == "capture_order"
    assert raw["meta"]["global_commands"].get("catalogo")
    assert (ROOT / "flows" / "meta_productos_flow.json").is_file()
    print("JSON node OK")


def _handler_ping() -> None:
    from services.whatsapp_flows_service import handle_decrypted_flow_request

    out = handle_decrypted_flow_request(
        {"version": "3.0", "action": "ping", "flow_token": "default:x"}
    )
    assert out == {"data": {"status": "active"}}, out
    print("handler ping OK")


def _module_crypto() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    os.environ["WA_FLOWS_PRIVATE_KEY"] = pem.decode("utf-8")
    os.environ["WA_FLOWS_PRIVATE_KEY_PATH"] = ""
    for mod in ("config.settings", "services.whatsapp_flows_crypto"):
        sys.modules.pop(mod, None)

    from services.whatsapp_flows_crypto import decrypt_request, encrypt_response

    aes_key = os.urandom(16)
    iv = os.urandom(16)
    payload = {"version": "3.0", "action": "ping"}
    enc = Cipher(algorithms.AES(aes_key), modes.GCM(iv)).encryptor()
    body = enc.update(json.dumps(payload).encode()) + enc.finalize() + enc.tag
    encrypted_aes = key.public_key().encrypt(
        aes_key,
        OAEP(mgf=MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    decrypted, aes_out, iv_out = decrypt_request(
        b64encode(body).decode(),
        b64encode(encrypted_aes).decode(),
        b64encode(iv).decode(),
    )
    assert decrypted["action"] == "ping"
    out = encrypt_response({"data": {"status": "active"}}, aes_out, iv_out)
    assert isinstance(out, str) and len(out) > 10
    print("module crypto OK")


def _engine_wa_flow_flag() -> None:
    from app.core.state_manager import StateManager
    from app.core.flow_engine import FlowEngine

    engine_sm = StateManager(persist_path=None)
    engine = object.__new__(FlowEngine)
    engine.state_manager = engine_sm
    engine.nodes = {
        "productos_whatsapp_flow_button_node": {
            "wa_flow": {"button_text": "Ver productos"},
            "flow": "order",
        }
    }
    wa = "test_flow_wa"
    engine_sm.set_step(wa, "productos_whatsapp_flow_button_node", "order")
    engine_sm.patch_data(wa, wa_flow_pending=True)
    got = FlowEngine.get_current_wa_flow(engine, wa)
    assert got and got.get("button_text") == "Ver productos"
    assert not engine_sm.get(wa).get("data", {}).get("wa_flow_pending")
    print("engine wa_flow flag OK")


def main() -> int:
    _node_declared()
    _handler_ping()
    _module_crypto()
    _engine_wa_flow_flag()
    print("ALL whatsapp_flows self-checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
