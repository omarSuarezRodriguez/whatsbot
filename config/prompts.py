"""Global prompt defaults — from flows/restaurant_flow.json + gateway (Fase 3)."""

from __future__ import annotations

DEFAULT_PROMPTS: dict[str, str] = {
    "admin_unrecognized": """Comando admin no reconocido.
Bloqueo: *blockon:+573001234567* | Desbloqueo: *blockoff:+573001234567*
Pedidos: *CONFIRMAR ORD-XXXXXXXX* o *pedido ORD-XXXXXXXX listo*""",
    "cancel_message": """Entendido, cancelé el proceso actual. Estoy aquí cuando quieras continuar.""",
    "empty_body_hint": """Estoy aquí para ayudarte. Escribe *menu*, *pedido* o *reservar*.""",
    "error_generic": """Disculpa, tuve un inconveniente momentáneo. Por favor intenta de nuevo en unos segundos.

Escribe *inicio* para reiniciar.""",
    "missing_wa_id": """No pude identificar tu número. Intenta escribirnos de nuevo.""",
    "node_menu_node_after": """

Cuando quieras, escribe *pedido* para ordenar o *reservar* para agendar tu mesa.""",
    "node_order_address_message": """{{address_prompt}}""",
    "node_order_customer_name_message": """Para identificar tu pedido, ¿cuál es tu nombre?""",
    "node_order_delivery_message": """¿Cómo prefieres recibir tu pedido?

1. *Domicilio*
2. *Recoger en tienda*

Responde con el número o escribe *domicilio* / *recoger*.""",
    "node_order_modify_message": """Sin problema. Dime qué quieres agregar, quitar o cambiar.

Ejemplo: *agrega una ensalada* o *quita la coca cola*.""",
    "node_order_review_after": """

¿Confirmamos tu pedido?
Responde *sí* para confirmar o *no* para modificarlo.""",
    "node_order_saved_after": """

Gracias por tu confianza. Tu pedido fue registrado y está *pendiente* de confirmación del restaurante.

Si necesitas algo más, escribe *menu*, *pedido* o *reservar*.""",
    "node_order_start_message": """Perfecto, vamos con tu pedido.

Cuéntame qué te gustaría. Puedes escribirlo en lenguaje natural, por ejemplo:
• *2 pizza hawaiana, 1 coca cola*
• *una hamburguesa y dos aguas*

También puedes decir *quita la coca cola* o *cambia pizza por hamburguesa*.""",
    "node_reservation_date_message": """Excelente. ¿Qué fecha prefieres?

Formato sugerido: *DD/MM/AAAA* (ejemplo: 15/06/2026)""",
    "node_reservation_review_after": """

¿Confirmamos la reserva?
Responde *sí* para confirmar o *no* para modificarla.""",
    "node_reservation_saved_after": """

Tu mesa quedó registrada. Te esperamos con gusto.

Si necesitas algo más, escribe *menu*, *pedido* o *reservar*.""",
    "node_reservation_start_message": """Con gusto te ayudo con tu reserva.

¿Para cuántas personas será?""",
    "node_reservation_time_message": """Perfecto. ¿A qué hora te gustaría la reserva?

Formato sugerido: *19:30* o *7:30 pm*""",
    "node_start_message": """{{welcome_line}}""",
    "node_start_secondary": """¿Qué te gustaría hacer hoy?

1. *menu* — Ver el menú
2. *pedido* — Hacer tu pedido
3. *reservar* — Reservar mesa""",
    "welcome_secondary": """¿Qué te gustaría hacer hoy?

1. *menu* — Ver el menú
2. *pedido* — Hacer tu pedido
3. *reservar* — Reservar mesa""",
}

def get_prompt(key: str, fallback: str = "") -> str:
    return DEFAULT_PROMPTS.get(key, fallback)

# -----------------------------------------------------------------------------
# GUÍA RÁPIDA
# - Entrada: flows/restaurant_flow.json + mensajes fijos del webhook.
# - Salida: business_prompts en BD; gateway/flow usan get_prompt() como fallback.
# - Fase 9: dueño edita en Flutter → PUT /whatsbot/business/prompts.
# -----------------------------------------------------------------------------
