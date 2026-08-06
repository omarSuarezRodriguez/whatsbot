"""
AdminService._send_whatsapp bonus: (1) mismo pacing por destinatario que
infrastructure/twilio_client.py, (2) registra outbox (pending_button_fallbacks)
para permitir el retry async de services/button_fallback_service.py cuando hay
un business_id resoluble (explícito o ambiental via business_context). Sin
business_id disponible, se omite el registro (no adivina el tenant).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ponytail: NO importar app.services.admin_service (ni nada que arrastre
# config.settings) a nivel de módulo. Ese import, en tiempo de collection,
# congelaría constantes como FCM_ENABLED/DATABASE_URL antes de que OTROS
# test_*.py alcancen a fijar sus propias env vars (convención ya usada por
# el resto de tests/ — imports de app siempre dentro de fixtures/funciones).


def _make_admin():
    from chatbot.app.services.admin_service import AdminService

    # _send_whatsapp no toca self.sheets/self.order_service; evita construir
    # esas dependencias pesadas en un test unitario.
    return AdminService.__new__(AdminService)


def _mock_twilio_client(sid: str = "SM_TEST_SID", status: str = "queued"):
    message = MagicMock(sid=sid, status=status, error_code=None)
    client = MagicMock()
    client.messages.create.return_value = message
    client.messages.return_value.fetch.return_value = message
    return client


def test_send_whatsapp_paces_and_registers_with_explicit_business_id():
    admin = _make_admin()
    with (
        patch("chatbot.app.services.admin_service.TWILIO_ACCOUNT_SID", "AC_TEST"),
        patch("chatbot.app.services.admin_service.TWILIO_AUTH_TOKEN", "tok"),
        patch("chatbot.app.services.admin_service.TWILIO_WHATSAPP_FROM", "+10000000000"),
        patch("twilio.rest.Client", return_value=_mock_twilio_client()),
        patch("infrastructure.twilio_client._pace_recipient") as mock_pace,
        patch("infrastructure.twilio_client.register_button_fallback") as mock_register,
    ):
        sid = admin._send_whatsapp("+573001112222", "hola", business_id="biz1")

    assert sid == "SM_TEST_SID"
    mock_pace.assert_called_once_with("+573001112222")
    mock_register.assert_called_once_with("SM_TEST_SID", "biz1", "+573001112222", "hola")


def test_send_whatsapp_registers_with_ambient_business_id():
    admin = _make_admin()
    with (
        patch("chatbot.app.services.admin_service.TWILIO_ACCOUNT_SID", "AC_TEST"),
        patch("chatbot.app.services.admin_service.TWILIO_AUTH_TOKEN", "tok"),
        patch("chatbot.app.services.admin_service.TWILIO_WHATSAPP_FROM", "+10000000000"),
        patch("twilio.rest.Client", return_value=_mock_twilio_client()),
        patch("infrastructure.twilio_client._pace_recipient"),
        patch("infrastructure.twilio_client.register_button_fallback") as mock_register,
        patch("chatbot.business_context.get_active_business_id", return_value="ambient-biz"),
    ):
        admin._send_whatsapp("+573001112222", "hola")

    mock_register.assert_called_once_with("SM_TEST_SID", "ambient-biz", "+573001112222", "hola")


def test_send_whatsapp_skips_registration_without_any_business_id():
    admin = _make_admin()
    with (
        patch("chatbot.app.services.admin_service.TWILIO_ACCOUNT_SID", "AC_TEST"),
        patch("chatbot.app.services.admin_service.TWILIO_AUTH_TOKEN", "tok"),
        patch("chatbot.app.services.admin_service.TWILIO_WHATSAPP_FROM", "+10000000000"),
        patch("twilio.rest.Client", return_value=_mock_twilio_client()),
        patch("infrastructure.twilio_client._pace_recipient"),
        patch("infrastructure.twilio_client.register_button_fallback") as mock_register,
        patch("chatbot.business_context.get_active_business_id", return_value=None),
    ):
        sid = admin._send_whatsapp("+573001112222", "hola")

    assert sid == "SM_TEST_SID"
    mock_register.assert_not_called()
