"""Global intent defaults — migrated from legacy app/core/parser.py (Fase 3)."""

from __future__ import annotations

from typing import Dict

GLOBAL_COMMAND_ROUTES: Dict[str, str] = {
    "menu": "menu_node",
    "pedido": "order_start",
    "reservar": "reservation_start",
    "inicio": "start",
    "cancelar": "start",
}

GLOBAL_COMMANDS = frozenset(GLOBAL_COMMAND_ROUTES.keys())

MENU_INTENT_TOKENS = frozenset({"menu", "carta", "catalogo", "catálogo", "lista", "ver"})

ORDER_INTENT_PHRASES = (
    "quiero comer",
    "tengo hambre",
    "tengo mucha hambre",
    "tengo mucho hambre",
    "algo de comer",
    "hacer pedido",
    "hacer un pedido",
    "me gustaria pedir",
    "me gustaría pedir",
    "quisiera pedir",
    "quisiera ordenar",
    "voy a pedir",
    "deseo pedir",
)

MENU_INTENT_PHRASES = (
    "ver la carta",
    "ver el menu",
    "ver menú",
    "ver catalogo",
    "ver catálogo",
    "mostrar menu",
    "mostrar menú",
    "mostrar carta",
    "que tienen",
    "qué tienen",
    "que hay",
    "qué hay",
    "que venden",
    "qué venden",
    "pasame el menu",
    "pásame el menú",
    "lista de precios",
    "precios del menu",
)

# Global flow commands — only the five documented commands (+ explicit NL phrases).
GLOBAL_COMMAND_INTENTS: Dict[str, Dict[str, Any]] = {
    "menu": {
        "phrases": MENU_INTENT_PHRASES
        + (
            "quiero ver el menu",
            "quiero la carta",
            "muestrame el menu",
            "muéstrame el menú",
            "que me recomiendan",
            "qué me recomiendan",
            "opciones del menu",
            "opciones de comida",
        ),
        "tokens": frozenset({"menu", "menú", "carta", "catalogo", "catálogo"}),
    },
    "pedido": {
        "phrases": ORDER_INTENT_PHRASES
        + (
            "hacer pedido",
            "hacer un pedido",
            "realizar pedido",
            "mandar pedido",
            "enviar pedido",
            "ordenar comida",
            "ordenar algo",
            "quiero ordenar",
            "voy a ordenar",
            "deseo ordenar",
            "me gustaria ordenar",
            "me gustaría ordenar",
            "puedo pedir",
            "para pedir",
            "pasar pedido",
            "tomar pedido",
            "poner pedido",
            "necesito pedir",
            "me animo a pedir",
            "me animo a ordenar",
        ),
        "tokens": frozenset({"pedido", "pedidos"}),
    },
    "reservar": {
        "phrases": (
            "quiero reservar",
            "quisiera reservar",
            "hacer reserva",
            "hacer una reserva",
            "reservar mesa",
            "reservar una mesa",
            "agendar mesa",
            "agendar una mesa",
            "apartar mesa",
            "mesa para",
            "necesito reservar",
            "me gustaria reservar",
            "me gustaría reservar",
            "quiero una mesa",
            "necesito una mesa",
            "apartar una mesa",
            "cita para comer",
            "reservacion de mesa",
            "reservación de mesa",
            "apartar lugar",
            "guardar mesa",
        ),
        "tokens": frozenset(
            {
                "reservar",
                "reserva",
                "reservacion",
                "reservación",
                "agendar",
                "apartar",
                "cita",
            }
        ),
    },
    "inicio": {
        "phrases": (
            "volver al inicio",
            "ir al inicio",
            "empezar de nuevo",
            "desde cero",
            "reiniciar chat",
            "menu principal",
            "menú principal",
            "volver al menu principal",
            "volver al menu",
            "volver al menú",
            "regresar al inicio",
            "comenzar de nuevo",
            "otra vez desde el inicio",
            "reiniciar conversacion",
            "reiniciar conversación",
        ),
        "tokens": frozenset({"inicio", "reiniciar", "restart"}),
    },
    "cancelar": {
        "phrases": (
            "cancelar pedido",
            "cancelar mi pedido",
            "anular pedido",
            "anular mi pedido",
            "abortar pedido",
            "no quiero el pedido",
            "olvidar pedido",
            "borrar pedido",
            "cancelar todo",
            "cancelar la orden",
            "no quiero continuar",
            "dejalo asi",
            "déjalo así",
            "ya no quiero pedir",
            "ya no sigo con el pedido",
            "ya no sigo con este pedido",
            "mejor ya no sigo con este pedido",
            "suspender pedido",
        ),
        "tokens": frozenset(
            {"cancelar", "anular", "abortar", "olvidar", "borrar", "suspender"}
        ),
    },
}

GREETING_PHRASES = frozenset(
    {
        "hola",
        "holaa",
        "holaaa",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "buen dia",
        "hey",
        "hello",
        "hi",
        "que tal",
        "qué tal",
        "saludos",
        "como estas",
        "cómo estás",
    }
)


def global_commands_frozenset() -> frozenset[str]:
    return GLOBAL_COMMANDS


# -----------------------------------------------------------------------------
# GUÍA RÁPIDA
# - Entrada: semilla al crear negocio; copia a business_intents en BD.
# - Salida: GLOBAL_COMMAND_INTENTS consumido por chatbot/parser.py.
# - El dueño edita intents en Flutter (Fase 9); no este archivo.
# -----------------------------------------------------------------------------
