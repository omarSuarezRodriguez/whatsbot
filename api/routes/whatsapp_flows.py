"""
Meta WhatsApp Flows data endpoint (encrypted).

POST /whatsapp/flows/data
  Body: {encrypted_flow_data, encrypted_aes_key, initial_vector}
  Response: text/plain base64 ciphertext
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from services.whatsapp_flows_crypto import decrypt_request, encrypt_response
from services.whatsapp_flows_service import handle_decrypted_flow_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp-flows"])


@router.post("/whatsapp/flows/data")
async def whatsapp_flows_data(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400, content="invalid json")

    try:
        encrypted_flow_data = body["encrypted_flow_data"]
        encrypted_aes_key = body["encrypted_aes_key"]
        initial_vector = body["initial_vector"]
    except (KeyError, TypeError):
        return Response(status_code=400, content="missing encrypted fields")

    try:
        decrypted, aes_key, iv = decrypt_request(
            encrypted_flow_data,
            encrypted_aes_key,
            initial_vector,
        )
    except Exception:
        logger.exception("WhatsApp Flow decrypt failed")
        return Response(status_code=421, content="decrypt failed")

    try:
        response_payload = handle_decrypted_flow_request(decrypted)
        cipher_b64 = encrypt_response(response_payload, aes_key, iv)
    except Exception:
        logger.exception("WhatsApp Flow handler failed")
        return Response(status_code=500, content="handler failed")

    return Response(content=cipher_b64, media_type="text/plain")
