"""JSON-driven conversational flow engine."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.config import FLOWS_PATH, NAV_HINT, RESTAURANT_NAME
from app.core.state_manager import StateManager
from app.services.admin_service import AdminService
from app.services.menu_service import MenuService
from app.services.order_service import OrderService
from app.services.reservation_service import ReservationService
from app.services.user_service import UserService
from app.core.parser import infer_user_intent
from app.utils.validators import (
    is_confirmation,
    is_greeting,
    is_rejection,
    normalize_text,
    parse_date,
    parse_delivery_type,
    parse_persons,
    parse_time,
    validate_reservation_slot,
)

logger = logging.getLogger(__name__)

Reply = Union[str, List[str]]


class FlowEngine:
    def __init__(
        self,
        state_manager: StateManager,
        menu_service: MenuService,
        order_service: OrderService,
        reservation_service: ReservationService,
        user_service: UserService,
        admin_service: AdminService,
        flow_path: str | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.menu_service = menu_service
        self.order_service = order_service
        self.reservation_service = reservation_service
        self.user_service = user_service
        self.admin_service = admin_service
        self.flow_path = flow_path or str(FLOWS_PATH)
        self.flow = self._load_flow()
        self.nodes = self.flow.get("nodes", {})
        self.meta = self.flow.get("meta", {})
        self.global_commands = self.meta.get("global_commands", {})

        self._actions: Dict[str, Callable[..., Tuple[str, Optional[str]]]] = {
            "welcome_customer": self._action_welcome_customer,
            "show_menu": self._action_show_menu,
            "capture_order": self._action_capture_order,
            "show_cart": self._action_show_cart,
            "handle_order_confirmation": self._action_handle_order_confirmation,
            "capture_delivery_type": self._action_capture_delivery_type,
            "capture_address": self._action_capture_address,
            "capture_customer_name": self._action_capture_customer_name,
            "save_order": self._action_save_order,
            "capture_persons": self._action_capture_persons,
            "capture_date": self._action_capture_date,
            "capture_time": self._action_capture_time,
            "show_reservation_summary": self._action_show_reservation_summary,
            "handle_reservation_confirmation": self._action_handle_reservation_confirmation,
            "save_reservation": self._action_save_reservation,
        }

    def _load_flow(self) -> Dict[str, Any]:
        with open(self.flow_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def reload_flow(self) -> None:
        self.flow = self._load_flow()
        self.nodes = self.flow.get("nodes", {})
        self.meta = self.flow.get("meta", {})
        self.global_commands = self.meta.get("global_commands", {})

    def _render(self, template: str, extra: Optional[Dict[str, Any]] = None) -> str:
        context = {"restaurant_name": RESTAURANT_NAME, "welcome_line": "", "address_prompt": ""}
        if extra:
            context.update(extra)
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _as_reply(
        self,
        message: str,
        node: Optional[Dict[str, Any]] = None,
        step: str = "",
    ) -> Reply:
        if node and node.get("dual_message"):
            primary = message.strip()
            if step == "start":
                menu_text = self.menu_service.format_menu()
                secondary = (
                    f"{menu_text}\n\n"
                    "¿Deseas hacer un pedido o reservar una mesa?\n\n"
                    "Escribe *pedido* para ordenar o *reservar* para agendar tu mesa."
                )
            elif node.get("message_secondary"):
                secondary = self._render(node.get("message_secondary", ""))
            else:
                secondary = ""
            parts = [part for part in (primary, secondary) if part]
            return parts if len(parts) > 1 else (parts[0] if parts else message)
        return message

    def _append_navigation(self, message: Reply, node: Dict[str, Any]) -> Reply:
        if not self.meta.get("navigation_hint", True):
            return message
        if node.get("suppress_navigation"):
            return message
        hint = NAV_HINT
        if isinstance(message, list):
            if message:
                message[-1] = f"{message[-1]}{hint}"
            return message
        return f"{message}{hint}"

    def _has_active_order(self, state: Dict[str, Any]) -> bool:
        cart = state.get("data", {}).get("cart", [])
        return bool(cart) and state.get("flow") == "order"

    def _handle_abandon_confirm(self, wa_id: str, text: str, state: Dict[str, Any]) -> Optional[Reply]:
        if not state.get("data", {}).get("awaiting_abandon_confirm"):
            return None
        if is_confirmation(text):
            self.state_manager.reset(wa_id)
            return self._process_node(wa_id, "start", include_navigation=True)
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=False)
            return "Perfecto, continuamos con tu pedido actual."
        return "Responde *sí* para volver al inicio o *no* para continuar tu pedido."

    def _handle_repeat_order(self, wa_id: str, text: str, state: Dict[str, Any]) -> Optional[Reply]:
        if not state.get("data", {}).get("awaiting_repeat_order"):
            return None
        if is_confirmation(text):
            items = self.user_service.get_last_order_items(wa_id)
            if not items:
                self.state_manager.patch_data(wa_id, awaiting_repeat_order=False)
                return "No encontré tu pedido anterior."
            self.state_manager.patch_data(
                wa_id,
                cart=items,
                awaiting_repeat_order=False,
            )
            self.state_manager.set_step(wa_id, "order_review", "order")
            return self._process_node(wa_id, "order_review", include_navigation=False)
        if is_rejection(text):
            self.state_manager.patch_data(
                wa_id,
                awaiting_repeat_order=False,
                skip_repeat_order_once=True,
            )
            return self._process_node(wa_id, "start", include_navigation=True)
        return "Responde *sí* para repetir tu pedido anterior o *no* para elegir otra opción."

    def _resolve_global_command(
        self,
        wa_id: str,
        command: str,
        current_step: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Reply]:
        target = self.global_commands.get(command)
        if not target:
            return None

        if state is None:
            state = self.state_manager.get(wa_id)

        if command == "pedido" and self._has_active_order(state):
            self.state_manager.set_step(wa_id, "order_review", "order")
            return self._process_node(wa_id, "order_review", include_navigation=True)

        if command == "inicio" and self._has_active_order(state):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=True)
            return (
                "Tienes un pedido en curso.\n\n"
                "¿Estás seguro de abandonar tu pedido actual?\n"
                "Responde *sí* para volver al inicio o *no* para continuar."
            )

        if command == "cancelar":
            self.state_manager.reset(wa_id)
            cancel_message = self.meta.get(
                "cancel_message",
                "Proceso cancelado. Estoy aquí cuando quieras continuar.",
            )
            start_message = self._process_node(wa_id, target, include_navigation=False)
            if isinstance(start_message, list):
                combined = [cancel_message, *start_message]
            else:
                combined = f"{cancel_message}\n\n{start_message}".strip()
            return self._append_navigation(combined, self.nodes.get(target, {}))

        if command == "inicio":
            self.state_manager.reset(wa_id)

        node = self.nodes.get(target, {})
        self.state_manager.set_step(wa_id, target, node.get("flow", "idle"))
        if (
            command in {"menu", "pedido", "reservar"}
            and target != current_step
            and not (command == "pedido" and self._has_active_order(state))
        ):
            self.state_manager.patch_data(
                wa_id,
                cart=[],
                reservation={},
                awaiting_repeat_order=False,
                awaiting_abandon_confirm=False,
            )

        return self._process_node(wa_id, target, include_navigation=True)

    _NAV_GLOBAL_COMMANDS = frozenset({"menu", "pedido", "reservar", "inicio", "cancelar"})

    def _execute_input_action(
        self,
        wa_id: str,
        text: str,
        node: Dict[str, Any],
        current_step: str,
        state: Dict[str, Any],
    ) -> Optional[Reply]:
        action_name = node.get("action_on_input") or node.get("action")
        if not action_name or action_name not in self._actions:
            return None
        if node.get("input_mode") != "free_text":
            return None

        message, next_step = self._actions[action_name](wa_id, text)
        if next_step:
            next_node = self.nodes.get(next_step, {})
            self.state_manager.set_step(
                wa_id,
                next_step,
                next_node.get("flow", state.get("flow", "idle")),
            )
            if next_step != current_step:
                follow_up = self._process_node(
                    wa_id,
                    next_step,
                    include_navigation=False,
                )
                if isinstance(follow_up, list):
                    combined: Reply = [message, *follow_up] if message else follow_up
                elif message:
                    combined = f"{message}\n\n{follow_up}".strip()
                else:
                    combined = follow_up
                return self._append_navigation(combined, next_node)
        return self._append_navigation(message, node)

    def process_message(self, wa_id: str, body: str, *, _inner: bool = False) -> Reply:
        text = (body or "").strip()
        if not text:
            text = "hola"

        normalized = normalize_text(text)
        if normalized == "pedid":
            normalized = "pedido"
        state = self.state_manager.get(wa_id)
        current_step = state.get("step", "start")
        log_meta: Dict[str, Any] = {"intent": None, "routed": None}

        return self._process_message_body(
            wa_id,
            text,
            normalized,
            state,
            current_step,
            log_meta,
            _inner=_inner,
        )

    def _process_message_body(
        self,
        wa_id: str,
        text: str,
        normalized: str,
        state: Dict[str, Any],
        current_step: str,
        log_meta: Dict[str, Any],
        *,
        _inner: bool,
    ) -> Reply:
        abandon = self._handle_abandon_confirm(wa_id, text, state)
        if abandon is not None:
            return abandon

        repeat = self._handle_repeat_order(wa_id, text, state)
        if repeat is not None:
            return repeat

        if state.get("data", {}).get("awaiting_repeat_order") and is_greeting(text):
            self.state_manager.patch_data(
                wa_id,
                awaiting_repeat_order=False,
                skip_repeat_order_once=True,
            )
            return self._process_node(wa_id, "start", include_navigation=True)

        node = self.nodes.get(current_step)
        if not node:
            self.state_manager.reset(wa_id)
            return self._process_node(wa_id, "start", include_navigation=True)

        if (
            node.get("action_on_input")
            and normalized not in self._NAV_GLOBAL_COMMANDS
        ):
            step_response = self._execute_input_action(
                wa_id, text, node, current_step, state
            )
            if step_response is not None:
                log_meta["routed"] = node.get("action_on_input") or node.get("action")
                return step_response

        if normalized in self.global_commands:
            log_meta["routed"] = normalized
            response = self._resolve_global_command(
                wa_id, normalized, current_step, state
            )
            if response:
                return response

        options = node.get("options", {})
        if normalized in options:
            next_step = options[normalized]
            next_node = self.nodes.get(next_step, {})
            self.state_manager.set_step(
                wa_id,
                next_step,
                next_node.get("flow", state.get("flow", "idle")),
            )
            return self._process_node(wa_id, next_step, include_navigation=True)

        if is_greeting(text) and node.get("flow") == "idle":
            return self._process_node(wa_id, "start", include_navigation=True)

        menu_tokens = self.menu_service.menu_literal_tokens()
        intent = infer_user_intent(text, menu_tokens=menu_tokens)
        log_meta["intent"] = intent
        intent_command = intent.get("command")
        if intent_command in {"pedido", "menu", "reservar"} and is_confirmation(text):
            intent_command = None
        if (
            intent_command
            and intent_command in self.global_commands
            and not intent.get("has_products")
        ):
            log_meta["routed"] = str(intent_command)
            response = self._resolve_global_command(
                wa_id, intent_command, current_step, state
            )
            if response:
                return response

        node_for_intent = self.nodes.get(current_step, {})
        if (
            not intent_command
            and intent.get("has_products")
            and current_step in {"start", "menu_node"}
            and node_for_intent.get("flow") == "idle"
        ):
            log_meta["routed"] = "pedido_implicito"
            response = self._resolve_global_command(
                wa_id, "pedido", current_step, state
            )
            if response:
                return self.process_message(wa_id, text, _inner=True)

        if node.get("input_mode") == "free_text":
            step_response = self._execute_input_action(
                wa_id, text, node, current_step, state
            )
            if step_response is not None:
                return step_response

        if is_greeting(text) and current_step in {"order_start", "order_modify"}:
            return self._append_navigation(
                "¡Hola! Cuando quieras, cuéntame qué deseas ordenar.\n"
                "Ejemplo: *2 hamburguesas y 1 agua*",
                node,
            )

        fallback = node.get(
            "fallback",
            "No logré entender eso del todo. Puedes reformularlo o usar uno de los comandos disponibles.",
        )
        return self._append_navigation(fallback, node)

    def _process_node(
        self,
        wa_id: str,
        step: str,
        include_navigation: bool = False,
        user_input: str = "",
    ) -> Reply:
        node = self.nodes.get(step, self.nodes.get("start", {}))
        self.state_manager.set_step(wa_id, step, node.get("flow", "idle"))

        extra = self._build_node_context(wa_id, step)
        parts = []
        base_message = node.get("message")
        if base_message:
            parts.append(self._render(base_message, extra))

        action_name = node.get("action")
        next_step: Optional[str] = None
        if action_name and action_name in self._actions:
            input_action = node.get("action_on_input") or node.get("action")
            waiting_for_input = (
                node.get("input_mode") == "free_text"
                and not user_input
                and action_name == node.get("action")
                and action_name == input_action
            )
            if not waiting_for_input:
                action_message, next_step = self._actions[action_name](
                    wa_id,
                    user_input,
                )
                if action_message:
                    parts.append(action_message)

        after_action = node.get("message_after_action")
        if after_action:
            parts.append(self._render(after_action, extra))

        response = "\n\n".join(part for part in parts if part).strip()

        if next_step and next_step != step:
            next_node = self.nodes.get(next_step, {})
            self.state_manager.set_step(
                wa_id,
                next_step,
                next_node.get("flow", node.get("flow", "idle")),
            )
            follow_up = self._process_node(
                wa_id,
                next_step,
                include_navigation=False,
            )
            if isinstance(follow_up, list):
                if response:
                    response = [response, *follow_up]
                else:
                    response = follow_up
            elif follow_up:
                response = f"{response}\n\n{follow_up}".strip() if response else follow_up

        if include_navigation:
            response = self._append_navigation(response, node)

        return self._as_reply(response, node, step=step)

    def _build_node_context(self, wa_id: str, step: str) -> Dict[str, str]:
        profile = self.user_service.get_profile(wa_id)
        name = profile.get("name", "")
        if name:
            welcome = f"Hola *{name}*, Bienvenido a *{RESTAURANT_NAME}*."
        else:
            welcome = f"Hola, Bienvenido a *{RESTAURANT_NAME}*."

        address_prompt = "Indícame la dirección de entrega a domicilio."
        saved_address = profile.get("address", "")
        if saved_address:
            address_prompt = (
                f"Tienes guardada esta dirección:\n*{saved_address}*\n\n"
                "¿Deseas usarla? Responde *sí*.\n"
                "O escribe una dirección nueva."
            )
        return {"welcome_line": welcome, "address_prompt": address_prompt}

    def _action_welcome_customer(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        data = state.get("data", {})
        if data.get("skip_repeat_order_once"):
            self.state_manager.patch_data(
                wa_id,
                skip_repeat_order_once=False,
                awaiting_repeat_order=False,
            )
            return "", None

        profile = self.user_service.get_profile(wa_id)
        last_items = profile.get("last_order_items") or []
        if last_items:
            self.state_manager.patch_data(wa_id, awaiting_repeat_order=True)
            return (
                "¿Deseas repetir tu pedido anterior?\nResponde *sí* o *no*.",
                None,
            )
        return "", None

    def _action_show_menu(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        return self.menu_service.format_menu(), None

    def _action_capture_order(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        if is_greeting(text):
            return (
                "¡Hola! Cuéntame qué te gustaría ordenar.\n"
                "Ejemplo: *2 hamburguesas y 1 agua*",
                None,
            )

        state = self.state_manager.get(wa_id)
        cart = state.get("data", {}).get("cart", [])
        result = self.order_service.parse_order_text(text, cart, wa_id=wa_id)

        if not result["items"]:
            return (
                "Aún no tengo productos en tu pedido."
                + "\n\nCuéntame qué te gustaría ordenar.",
                None,
            )

        self.state_manager.patch_data(wa_id, cart=result["items"])
        notes = result.get("notes", [])
        note_text = f"\n\n{' '.join(notes)}" if notes else ""

        return (
            f"Perfecto, actualicé tu pedido.{note_text}",
            "order_review",
        )

    def _action_show_cart(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        cart = state.get("data", {}).get("cart", [])
        if not cart:
            return "Tu carrito está vacío. Cuéntame qué te gustaría pedir.", "order_start"
        return self.order_service.format_cart(cart), None

    def _action_handle_order_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        if is_confirmation(text):
            return "¡Excelente!", "order_delivery"
        if is_rejection(text):
            return "Claro, modifiquemos tu pedido.", "order_modify"
        return (
            "Para continuar, responde *sí* para confirmar o *no* para modificar tu pedido.",
            None,
        )

    def _action_capture_delivery_type(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        delivery = parse_delivery_type(text)
        if not delivery:
            return (
                "No entendí tu elección.\n"
                "Responde *1* o *domicilio*, o *2* o *recoger*.",
                None,
            )
        self.state_manager.patch_data(wa_id, delivery_type=delivery)
        if delivery == "domicilio":
            return "", "order_address"
        profile = self.user_service.get_profile(wa_id)
        if profile.get("name"):
            return "", "order_saved"
        return "", "order_customer_name"

    def _action_capture_address(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        profile = self.user_service.get_profile(wa_id)
        saved = profile.get("address", "")
        address = text.strip()
        if saved and is_confirmation(text):
            address = saved
        elif not address:
            return "Necesito una dirección válida para el domicilio.", None

        self.user_service.save_address(wa_id, address)
        self.state_manager.patch_data(wa_id, delivery_address=address)
        profile = self.user_service.get_profile(wa_id)
        if profile.get("name"):
            return "", "order_saved"
        return "Gracias. Guardé tu dirección.", "order_customer_name"

    def _action_capture_customer_name(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        name = text.strip()
        if len(name) < 2:
            return "Por favor escribe tu nombre (mínimo 2 caracteres).", None
        self.user_service.save_name(wa_id, name)
        return "", "order_saved"

    def _action_save_order(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        data = state.get("data", {})
        cart = data.get("cart", [])
        if not cart:
            return "No encontré productos para guardar.", "order_start"

        profile = self.user_service.get_profile(wa_id)
        customer_name = profile.get("name", "")
        address = data.get("delivery_address", profile.get("address", ""))
        delivery_type = data.get("delivery_type", "")

        stored_wa = self.admin_service._resolve_e164_digits(wa_id) or wa_id
        order_id, total = self.order_service.save_order(
            stored_wa,
            cart,
            customer_name=customer_name,
            address=address,
            delivery_type=delivery_type,
        )
        order_payload = self.order_service.get_order(order_id) or {
            "order_id": order_id,
            "wa_id": stored_wa,
            "items": cart,
            "total": total,
            "customer_name": customer_name,
            "address": address,
            "delivery_type": delivery_type,
        }
        from services.notification_service import on_order_pending

        on_order_pending(order_payload)

        self.state_manager.patch_data(
            wa_id,
            cart=[],
            delivery_type="",
            delivery_address="",
            last_order_id=order_id,
            awaiting_repeat_order=False,
            awaiting_abandon_confirm=False,
        )
        self.state_manager.set_step(wa_id, "start", "idle")
        return (
            f"Pedido *{order_id}* registrado correctamente.\n"
            f"Total: *${total:.2f}*\n"
            f"Estado: *pendiente* (esperando confirmación del restaurante)",
            None,
        )

    def _action_capture_persons(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        personas = parse_persons(text)
        if not personas:
            return "Indícame un número válido de personas (entre 1 y 30).", None
        self.state_manager.patch_data(wa_id, reservation={"personas": personas})
        return f"Perfecto, reserva para *{personas}* personas.", "reservation_date"

    def _action_capture_date(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        reservation_date = parse_date(text)
        if not reservation_date:
            return (
                "No pude interpretar la fecha. Usa el formato *DD/MM/AAAA* "
                "con una fecha igual o posterior a hoy.",
                None,
            )
        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        reservation["fecha"] = reservation_date.isoformat()
        self.state_manager.patch_data(wa_id, reservation=reservation)
        return (
            f"Fecha registrada: *{reservation_date.strftime('%d/%m/%Y')}*.",
            "reservation_time",
        )

    def _action_capture_time(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        reservation_time = parse_time(text)
        if not reservation_time:
            return "No pude interpretar la hora. Prueba con *19:30* o *7:30 pm*.", None

        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        fecha_raw = reservation.get("fecha")
        if not fecha_raw:
            return "Primero necesito la fecha de la reserva.", "reservation_date"

        from datetime import date

        reservation_date = date.fromisoformat(fecha_raw)
        valid, error = validate_reservation_slot(reservation_date, reservation_time)
        if not valid:
            return error, None

        reservation["hora"] = reservation_time.strftime("%H:%M")
        self.state_manager.patch_data(wa_id, reservation=reservation)
        return f"Hora registrada: *{reservation_time.strftime('%H:%M')}*.", "reservation_review"

    def _action_show_reservation_summary(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        if not reservation.get("personas") or not reservation.get("fecha") or not reservation.get("hora"):
            return "Necesito completar los datos de la reserva.", "reservation_start"

        from datetime import date, time

        summary = self.reservation_service.format_summary(
            personas=int(reservation["personas"]),
            reservation_date=date.fromisoformat(reservation["fecha"]),
            reservation_time=time.fromisoformat(reservation["hora"] + ":00")
            if len(reservation["hora"]) == 5
            else time.fromisoformat(reservation["hora"]),
        )
        return f"*Resumen de tu reserva*\n{summary}", None

    def _action_handle_reservation_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        if is_confirmation(text):
            return "¡Perfecto!", "reservation_saved"
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, reservation={})
            return "Sin problema, empecemos de nuevo.", "reservation_start"
        return (
            "Responde *sí* para confirmar la reserva o *no* para modificarla.",
            None,
        )

    def _action_save_reservation(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        required = ("personas", "fecha", "hora")
        if not all(reservation.get(key) for key in required):
            return "Faltan datos para completar la reserva.", "reservation_start"

        from datetime import date, time

        reservation_id = self.reservation_service.save_reservation(
            wa_id=wa_id,
            personas=int(reservation["personas"]),
            reservation_date=date.fromisoformat(reservation["fecha"]),
            reservation_time=time.fromisoformat(
                reservation["hora"] + ":00"
                if len(reservation["hora"]) == 5
                else reservation["hora"]
            ),
        )
        self.state_manager.patch_data(wa_id, reservation={}, last_reservation_id=reservation_id)
        self.state_manager.set_step(wa_id, "start", "idle")
        return f"Reserva *{reservation_id}* confirmada.", None
