"""WhatsApp Flows endpoint encryption (Meta data_api_version 3.0)."""

from __future__ import annotations

import json
import logging
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Tuple

from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from config.settings import WA_FLOWS_PRIVATE_KEY, WA_FLOWS_PRIVATE_KEY_PATH

logger = logging.getLogger(__name__)


def _load_private_key_pem() -> bytes:
    if WA_FLOWS_PRIVATE_KEY:
        return WA_FLOWS_PRIVATE_KEY.replace("\\n", "\n").encode("utf-8")
    path = Path(WA_FLOWS_PRIVATE_KEY_PATH) if WA_FLOWS_PRIVATE_KEY_PATH else None
    if path and path.is_file():
        return path.read_bytes()
    raise FileNotFoundError(
        "WhatsApp Flows private key missing. Set WA_FLOWS_PRIVATE_KEY or "
        f"WA_FLOWS_PRIVATE_KEY_PATH (tried {WA_FLOWS_PRIVATE_KEY_PATH!r})."
    )


def decrypt_request(
    encrypted_flow_data_b64: str,
    encrypted_aes_key_b64: str,
    initial_vector_b64: str,
) -> Tuple[dict[str, Any], bytes, bytes]:
    flow_data = b64decode(encrypted_flow_data_b64)
    iv = b64decode(initial_vector_b64)
    encrypted_aes_key = b64decode(encrypted_aes_key_b64)

    private_key = load_pem_private_key(_load_private_key_pem(), password=None)
    aes_key = private_key.decrypt(
        encrypted_aes_key,
        OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
    )

    encrypted_body = flow_data[:-16]
    tag = flow_data[-16:]
    decryptor = Cipher(algorithms.AES(aes_key), modes.GCM(iv, tag)).decryptor()
    plain = decryptor.update(encrypted_body) + decryptor.finalize()
    return json.loads(plain.decode("utf-8")), aes_key, iv


def encrypt_response(response: dict[str, Any], aes_key: bytes, iv: bytes) -> str:
    flipped_iv = bytes(b ^ 0xFF for b in iv)
    encryptor = Cipher(algorithms.AES(aes_key), modes.GCM(flipped_iv)).encryptor()
    cipher = (
        encryptor.update(json.dumps(response).encode("utf-8"))
        + encryptor.finalize()
        + encryptor.tag
    )
    return b64encode(cipher).decode("utf-8")
