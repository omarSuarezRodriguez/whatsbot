"""JSON-driven conversational flow engine."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

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

_START_IDLE_FALLBACK = (
    "Disculpa, no logré entenderte. ¿Podrías intentarlo de nuevo? "
    "También puedes escribir menu, pedido o reservar."
)
_SYSTEM_TECHNICAL_FALLBACK = "Error interno: texto no configurado."


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
        self._apply_flow(self.flow)

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
            raw = json.load(handle)
        return self._normalize_flow(raw)

    def _apply_flow(self, flow: Dict[str, Any]) -> None:
        self.flow = flow
        self.nodes = flow.get("nodes", {})
        self.meta = flow.get("meta", {})
        self.global_commands = self.meta.get("global_commands", {})

    def reload_flow(self) -> None:
        self._apply_flow(self._load_flow())

    @staticmethod
    def _normalize_flow(raw: Dict[str, Any]) -> Dict[str, Any]:
        states = raw.get("states")
        if not states:
            raise ValueError(
                "Flow JSON must define 'states' (legacy flat 'nodes' no longer supported)"
            )
        meta = raw.get("meta", {})
        nodes: Dict[str, Any] = {}
        for state_name, state_def in states.items():
            for step, node in state_def.get("nodes", {}).items():
                flat = dict(node)
                flat.setdefault("flow", state_name)
                nodes[step] = flat
        return {"meta": meta, "nodes": nodes}

    def _parse_ref(self, ref: str, current_state: str = "idle") -> Tuple[str, str]:
        if "." in ref:
            state, step = ref.split(".", 1)
            return state, step
        node = self.nodes.get(ref, {})
        state = node.get("flow") or current_state or "idle"
        return state, ref

    def _resolve_transition(
        self,
        node: Dict[str, Any],
        outcome: Optional[str],
    ) -> Optional[str]:
        if not outcome:
            return None
        transitions = node.get("transitions") or {}
        if outcome not in transitions:
            return None
        dest = transitions[outcome]
        if dest is None:
            return None
        _, step = self._parse_ref(dest, node.get("flow", "idle"))
        return step

    def _render(self, template: str, extra: Optional[Dict[str, Any]] = None) -> str:
        # Use per-business prompts/name from contextvar when available
        try:
            from chatbot.business_context import get_prompt as ctx_get_prompt

            biz_name = ctx_get_prompt("restaurant_name", RESTAURANT_NAME)
        except Exception:
            biz_name = RESTAURANT_NAME
        context = {"restaurant_name": biz_name, "welcome_line": "", "address_prompt": ""}
        if extra:
            context.update(extra)
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    @staticmethod
    def _join_reply(*parts: str) -> str:
        return "\n\n".join(
            str(part).strip() for part in parts if part and str(part).strip()
        ).strip()

    def _append_navigation(self, message: str, node: Dict[str, Any]) -> str:
        if not self.meta.get("navigation_hint", True):
            return message
        if node.get("suppress_navigation"):
            return message
        return f"{message}{NAV_HINT}"

    def _has_active_order(self, state: Dict[str, Any]) -> bool:
        cart = state.get("data", {}).get("cart", [])
        return bool(cart) and state.get("flow") == "order"

    def _resolve_ux_text(self, meta_key: str, node: Dict[str, Any]) -> str:
        text = self.meta.get(meta_key)
        if text:
            return str(text)
        fallback = node.get("fallback")
        if fallback:
            return str(fallback)
        return _SYSTEM_TECHNICAL_FALLBACK

    def _handle_abandon_confirm(self, wa_id: str, text: str, state: Dict[str, Any]) -> Optional[str]:
        if not state.get("data", {}).get("awaiting_abandon_confirm"):
            return None
        node = self.nodes.get(state.get("step", ""), {})
        if is_confirmation(text):
            self.state_manager.reset(wa_id)
            _, start_step = self._parse_ref("idle.start", state.get("flow", "idle"))
            return self._process_node(wa_id, start_step, include_navigation=True)
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=False)
            return self._resolve_ux_text("abandon_confirm_continue", node)
        return self._resolve_ux_text("abandon_confirm_invalid", node)

    def _resolve_global_command(
        self,
        wa_id: str,
        command: str,
        current_step: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        target = self.global_commands.get(command)
        if not target:
            return None

        if state is None:
            state = self.state_manager.get(wa_id)

        current_flow = state.get("flow", "idle")
        target_flow, target_step = self._parse_ref(str(target), current_flow)

        if command == "pedido" and self._has_active_order(state):
            _, review_step = self._parse_ref("order.order_review", current_flow)
            self.state_manager.set_step(wa_id, review_step, "order")
            return self._process_node(wa_id, review_step, include_navigation=True)

        if command == "inicio" and self._has_active_order(state):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=True)
            current_node = self.nodes.get(current_step, {})
            return self._resolve_ux_text("abandon_confirm_prompt", current_node)

        if command == "cancelar":
            self.state_manager.reset(wa_id)
            cancel_message = self._resolve_ux_text(
                "cancel_message", self.nodes.get(target_step, {})
            )
            start_message = self._process_node(wa_id, target_step, include_navigation=False)
            combined = self._join_reply(cancel_message, start_message)
            return self._append_navigation(combined, self.nodes.get(target_step, {}))

        if command == "inicio":
            self.state_manager.reset(wa_id)

        node = self.nodes.get(target_step, {})
        self.state_manager.set_step(wa_id, target_step, node.get("flow", target_flow))
        if (
            command in {"menu", "pedido", "reservar"}
            and target_step != current_step
            and not (command == "pedido" and self._has_active_order(state))
        ):
            self.state_manager.patch_data(
                wa_id,
                cart=[],
                reservation={},
                awaiting_abandon_confirm=False,
            )

        return self._process_node(wa_id, target_step, include_navigation=True)

    _NAV_GLOBAL_COMMANDS = frozenset({"menu", "pedido", "reservar", "inicio", "cancelar"})

    def _execute_input_action(
        self,
        wa_id: str,
        text: str,
        node: Dict[str, Any],
        current_step: str,
        state: Dict[str, Any],
    ) -> Optional[str]:
        action_name = node.get("action_on_input") or node.get("action")
        if not action_name or action_name not in self._actions:
            return None
        if node.get("input_mode") != "free_text":
            return None

        message, outcome = self._actions[action_name](wa_id, text)
        next_step = self._resolve_transition(node, outcome)
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
                combined = (
                    self._join_reply(message, follow_up) if message else follow_up
                )
                return self._append_navigation(combined, next_node)
        return self._append_navigation(message, node)

    def process_message(self, wa_id: str, body: str, *, _inner: bool = False) -> str:
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
    ) -> str:
        abandon = self._handle_abandon_confirm(wa_id, text, state)
        if abandon is not None:
            return abandon

        node = self.nodes.get(current_step)
        if not node:
            self.state_manager.reset(wa_id)
            _, start_step = self._parse_ref("idle.start", "idle")
            return self._process_node(wa_id, start_step, include_navigation=True)

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
            if (
                next_step == current_step == "start"
                and state.get("data", {}).get("start_seen")
            ):
                return _START_IDLE_FALLBACK
            next_node = self.nodes.get(next_step, {})
            self.state_manager.set_step(
                wa_id,
                next_step,
                next_node.get("flow", state.get("flow", "idle")),
            )
            return self._process_node(wa_id, next_step, include_navigation=True)

        if is_greeting(text) and node.get("flow") == "idle" and current_step != "start":
            _, start_step = self._parse_ref("idle.start", node.get("flow", "idle"))
            return self._process_node(wa_id, start_step, include_navigation=True)

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

        if is_greeting(text) and current_step in {"order_start", "order_modify"}:
            greeting = self._resolve_ux_text("order_greeting_while_ordering", node)
            return self._append_navigation(greeting, node)

        if node.get("input_mode") == "free_text":
            step_response = self._execute_input_action(
                wa_id, text, node, current_step, state
            )
            if step_response is not None:
                return step_response

        if current_step == "start" and state.get("data", {}).get("start_seen"):
            return _START_IDLE_FALLBACK

        fallback = node.get("fallback") or _SYSTEM_TECHNICAL_FALLBACK
        return self._append_navigation(fallback, node)

    def _process_node(
        self,
        wa_id: str,
        step: str,
        include_navigation: bool = False,
        user_input: str = "",
    ) -> str:
        _, idle_start = self._parse_ref("idle.start", "idle")
        node = self.nodes.get(step, self.nodes.get(idle_start, {}))
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
                action_message, outcome = self._actions[action_name](
                    wa_id,
                    user_input,
                )
                if action_message:
                    parts.append(action_message)
                next_step = self._resolve_transition(node, outcome)

        after_action = node.get("message_after_action")
        if after_action:
            parts.append(self._render(after_action, extra))

        if node.get("dual_message"):
            secondary = node.get("message_secondary")
            if secondary:
                parts.append(self._render(secondary, extra))

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
            if follow_up:
                response = (
                    self._join_reply(response, follow_up) if response else follow_up
                )

        if include_navigation:
            response = self._append_navigation(response, node)

        if step == "start" and response:
            self.state_manager.patch_data(wa_id, start_seen=True)

        return response

    def _build_node_context(self, wa_id: str, step: str) -> Dict[str, str]:
        profile = self.user_service.get_profile(wa_id)
        name = profile.get("name", "")
        welcome_key = "welcome_with_name" if name else "welcome_without_name"
        welcome = self._render(
            self._resolve_ux_text(welcome_key, self.nodes.get(step, {})),
            {"name": name},
        )

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
        return "", None

    def _action_show_menu(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        return self.menu_service.format_menu(), None

    def _action_capture_order(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
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
            "success",
        )

    def _action_show_cart(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        cart = state.get("data", {}).get("cart", [])
        if not cart:
            return "Tu carrito está vacío. Cuéntame qué te gustaría pedir.", "empty_cart"
        return self.order_service.format_cart(cart), None

    def _action_handle_order_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        if is_confirmation(text):
            return "¡Excelente!", "confirmed"
        if is_rejection(text):
            return "Claro, modifiquemos tu pedido.", "rejected"
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
            return "", "domicilio"
        profile = self.user_service.get_profile(wa_id)
        if profile.get("name"):
            return "", "recoger_has_name"
        return "", "recoger_no_name"

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
            return "", "success_has_name"
        return "Gracias. Guardé tu dirección.", "success_no_name"

    def _action_capture_customer_name(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        name = text.strip()
        if len(name) < 2:
            return "Por favor escribe tu nombre (mínimo 2 caracteres).", None
        self.user_service.save_name(wa_id, name)
        return "", "success"

    def _action_save_order(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        data = state.get("data", {})
        cart = data.get("cart", [])
        if not cart:
            return "No encontré productos para guardar.", "empty_cart"

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
            awaiting_abandon_confirm=False,
        )
        return (
            f"Pedido *{order_id}* registrado correctamente.\n"
            f"Total: *${total:.2f}*\n"
            f"Estado: *pendiente* (esperando confirmación del restaurante)",
            "success",
        )

    def _action_capture_persons(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        personas = parse_persons(text)
        if not personas:
            return "Indícame un número válido de personas (entre 1 y 30).", None
        self.state_manager.patch_data(wa_id, reservation={"personas": personas})
        return f"Perfecto, reserva para *{personas}* personas.", "success"

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
            "success",
        )

    def _action_capture_time(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        reservation_time = parse_time(text)
        if not reservation_time:
            return "No pude interpretar la hora. Prueba con *19:30* o *7:30 pm*.", None

        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        fecha_raw = reservation.get("fecha")
        if not fecha_raw:
            return "Primero necesito la fecha de la reserva.", "missing_date"

        from datetime import date

        reservation_date = date.fromisoformat(fecha_raw)
        valid, error = validate_reservation_slot(reservation_date, reservation_time)
        if not valid:
            return error, None

        reservation["hora"] = reservation_time.strftime("%H:%M")
        self.state_manager.patch_data(wa_id, reservation=reservation)
        return f"Hora registrada: *{reservation_time.strftime('%H:%M')}*.", "success"

    def _action_show_reservation_summary(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        reservation = state.get("data", {}).get("reservation", {})
        if not reservation.get("personas") or not reservation.get("fecha") or not reservation.get("hora"):
            return "Necesito completar los datos de la reserva.", "incomplete"

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
            return "¡Perfecto!", "confirmed"
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, reservation={})
            return "Sin problema, empecemos de nuevo.", "rejected"
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
            return "Faltan datos para completar la reserva.", "incomplete"

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
        self.state_manager.patch_data(
            wa_id,
            reservation={},
            last_reservation_id=reservation_id,
        )
        return f"Reserva *{reservation_id}* confirmada.", "success"
