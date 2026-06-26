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

    def _goto_ref(
        self,
        wa_id: str,
        ref: str,
        *,
        current_flow: str = "idle",
        include_navigation: bool = True,
    ) -> str:
        _, step = self._parse_ref(ref, current_flow)
        return self._process_node(wa_id, step, include_navigation=include_navigation)

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

    def _cart_guard_flows(self) -> frozenset[str]:
        """Flows inferred from meta.active_order_command_targets; empty meta → no active order."""
        targets = self.meta.get("active_order_command_targets") or {}
        flows: set[str] = set()
        for target in targets.values():
            if not isinstance(target, str) or "." not in target:
                continue
            flow_name, _ = self._parse_ref(target)
            if flow_name:
                flows.add(flow_name)
        return frozenset(flows)

    def _has_active_order(self, state: Dict[str, Any]) -> bool:
        cart = state.get("data", {}).get("cart", [])
        if not cart:
            return False
        guard_flows = self._cart_guard_flows()
        if not guard_flows:
            return False
        return state.get("flow") in guard_flows

    def _resolve_ux_text(self, meta_key: str, node: Dict[str, Any]) -> str:
        text = self.meta.get(meta_key)
        if text:
            return str(text)
        fallback = node.get("fallback")
        if fallback:
            return str(fallback)
        return _SYSTEM_TECHNICAL_FALLBACK

    @staticmethod
    def _node_message_shown(state: Dict[str, Any], step: str) -> bool:
        shown = (state.get("data") or {}).get("shown_steps") or {}
        return bool(shown.get(step))

    def _mark_node_message_shown(self, wa_id: str, step: str) -> None:
        state = self.state_manager.get(wa_id)
        shown = dict((state.get("data") or {}).get("shown_steps") or {})
        if shown.get(step):
            return
        shown[step] = True
        self.state_manager.patch_data(wa_id, shown_steps=shown)

    def _node_fallback_message(self, node: Dict[str, Any]) -> str:
        return str(node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK))

    def _start_ref(self) -> str:
        return str(self.global_commands.get("inicio", "idle.start"))

    def _should_self_loop_fallback(
        self,
        next_ref: str,
        current_step: str,
        node: Dict[str, Any],
        state: Dict[str, Any],
    ) -> bool:
        _, target_step = self._parse_ref(
            str(next_ref),
            node.get("flow", state.get("flow", "idle")),
        )
        if target_step != current_step:
            return False
        if node.get("self_loop_behavior") != "fallback":
            return False
        if node.get("suppress_repeat_message") and not self._node_message_shown(
            state, current_step
        ):
            return False
        return True

    def _handle_abandon_confirm(self, wa_id: str, text: str, state: Dict[str, Any]) -> Optional[str]:
        if not state.get("data", {}).get("awaiting_abandon_confirm"):
            return None
        node = self.nodes.get(state.get("step", ""), {})
        if is_confirmation(text):
            self.state_manager.reset(wa_id)
            return self._goto_ref(wa_id, self._start_ref())
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
            active_targets = self.meta.get("active_order_command_targets") or {}
            redirect = active_targets.get("pedido")
            if redirect:
                return self._goto_ref(wa_id, str(redirect), current_flow=current_flow)

        if command == "inicio" and self._has_active_order(state):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=True)
            current_node = self.nodes.get(current_step, {})
            return self._resolve_ux_text("abandon_confirm_prompt", current_node)

        if command == "cancelar":
            self.state_manager.reset(wa_id)
            cancel_message = self._resolve_ux_text(
                "cancel_message", self.nodes.get(target_step, {})
            )
            start_message = self._goto_ref(
                wa_id, target, current_flow=current_flow, include_navigation=False
            )
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

        return self._goto_ref(wa_id, target, current_flow=current_flow)

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
        if not message:
            message = self._node_fallback_message(node)
        return self._append_navigation(message, node)

    def _compose_message(
        self,
        node: Dict[str, Any],
        parts: list[str],
        extra: Dict[str, str],
    ) -> str:
        after_action = node.get("message_after_action")
        if after_action:
            parts.append(self._render(after_action, extra))
        if node.get("dual_message"):
            secondary = node.get("message_secondary")
            if secondary:
                parts.append(self._render(secondary, extra))
        return self._join_reply(*parts)

    def process_message(self, wa_id: str, body: str) -> str:
        text = (body or "").strip()
        if not text:
            text = "hola"

        normalized = normalize_text(text)
        if normalized == "pedid":
            normalized = "pedido"
        state = self.state_manager.get(wa_id)
        current_step = state.get("step", "start")

        return self._process_message_body(
            wa_id,
            text,
            normalized,
            state,
            current_step,
        )

    def _process_message_body(
        self,
        wa_id: str,
        text: str,
        normalized: str,
        state: Dict[str, Any],
        current_step: str,
    ) -> str:
        abandon = self._handle_abandon_confirm(wa_id, text, state)
        if abandon is not None:
            return abandon

        node = self.nodes.get(current_step)
        if not node:
            self.state_manager.reset(wa_id)
            return self._goto_ref(wa_id, self._start_ref())

        options = node.get("options", {})
        if normalized in options:
            next_ref = options[normalized]
            if self._should_self_loop_fallback(next_ref, current_step, node, state):
                return self._append_navigation(self._node_fallback_message(node), node)
            return self._goto_ref(
                wa_id,
                next_ref,
                current_flow=state.get("flow", "idle"),
            )

        if normalized in self.global_commands:
            response = self._resolve_global_command(
                wa_id, normalized, current_step, state
            )
            if response:
                return response

        menu_tokens = self.menu_service.menu_literal_tokens()
        intent = infer_user_intent(text, menu_tokens=menu_tokens)
        intent_command = intent.get("command")
        if intent_command in {"pedido", "menu", "reservar"} and is_confirmation(text):
            intent_command = None
        if (
            intent_command
            and intent_command in self.global_commands
            and not intent.get("has_products")
        ):
            response = self._resolve_global_command(
                wa_id, intent_command, current_step, state
            )
            if response:
                return response

        if (
            not intent_command
            and intent.get("has_products")
            and node.get("intercept_products")
        ):
            response = self._resolve_global_command(
                wa_id, "pedido", current_step, state
            )
            if response:
                return self.process_message(wa_id, text)

        if node.get("order_greeting_on_greeting") and is_greeting(text):
            greeting = self._resolve_ux_text("order_greeting_while_ordering", node)
            return self._append_navigation(greeting, node)

        if node.get("input_mode") == "free_text":
            step_response = self._execute_input_action(
                wa_id, text, node, current_step, state
            )
            if step_response is not None:
                return step_response

        return self._append_navigation(self._node_fallback_message(node), node)

    def _process_node(
        self,
        wa_id: str,
        step: str,
        include_navigation: bool = False,
        user_input: str = "",
    ) -> str:
        _, idle_start = self._parse_ref(self._start_ref(), "idle")
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

        response = self._compose_message(node, parts, extra)

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

        if response and node.get("suppress_repeat_message"):
            self._mark_node_message_shown(wa_id, step)

        return response

    def _build_node_context(self, wa_id: str, step: str) -> Dict[str, str]:
        profile = self.user_service.get_profile(wa_id)
        name = profile.get("name", "")
        welcome_key = "welcome_with_name" if name else "welcome_without_name"
        welcome = self._render(
            self._resolve_ux_text(welcome_key, self.nodes.get(step, {})),
            {"name": name},
        )

        node = self.nodes.get(step, {})
        saved_address = profile.get("address", "")
        if saved_address:
            address_prompt = self._render(
                self._resolve_ux_text("address_prompt_saved", node),
                {"saved_address": saved_address},
            )
        else:
            address_prompt = self._resolve_ux_text("address_prompt", node)
        return {"welcome_line": welcome, "address_prompt": address_prompt}

    def _action_welcome_customer(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        return "", None

    def _action_show_menu(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        return self.menu_service.format_menu(), None

    def _action_capture_order(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        cart = state.get("data", {}).get("cart", [])
        result = self.order_service.parse_order_text(text, cart, wa_id=wa_id)

        if not result["items"]:
            return self._resolve_ux_text("capture_order_empty", node), None

        self.state_manager.patch_data(wa_id, cart=result["items"])
        notes = result.get("notes", [])
        note_text = f"\n\n{' '.join(notes)}" if notes else ""
        success = self._render(
            self._resolve_ux_text("capture_order_success", node),
            {},
        )
        return f"{success}{note_text}", "success"

    def _action_show_cart(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        cart = state.get("data", {}).get("cart", [])
        if not cart:
            node = self.nodes.get(state.get("step", ""), {})
            return self._resolve_ux_text("empty_cart_message", node), "empty_cart"
        return self.order_service.format_cart(cart), None

    def _action_handle_order_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        node = self.nodes.get(self.state_manager.get(wa_id).get("step", ""), {})
        if is_confirmation(text):
            return self._resolve_ux_text("order_confirm_yes", node), "confirmed"
        if is_rejection(text):
            return self._resolve_ux_text("order_confirm_no", node), "rejected"
        return "", None

    def _action_capture_delivery_type(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        delivery = parse_delivery_type(text)
        if not delivery:
            return "", None
        self.state_manager.patch_data(wa_id, delivery_type=delivery)
        if delivery == "domicilio":
            return "", "domicilio"
        profile = self.user_service.get_profile(wa_id)
        if profile.get("name"):
            return "", "recoger_has_name"
        return "", "recoger_no_name"

    def _action_capture_address(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        profile = self.user_service.get_profile(wa_id)
        saved = profile.get("address", "")
        address = text.strip()
        if saved and is_confirmation(text):
            address = saved
        elif not address:
            return "", None

        self.user_service.save_address(wa_id, address)
        self.state_manager.patch_data(wa_id, delivery_address=address)
        profile = self.user_service.get_profile(wa_id)
        if profile.get("name"):
            return "", "success_has_name"
        return self._resolve_ux_text("address_saved", node), "success_no_name"

    def _action_capture_customer_name(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        name = text.strip()
        if len(name) < 2:
            return "", None
        self.user_service.save_name(wa_id, name)
        return "", "success"

    def _action_save_order(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        data = state.get("data", {})
        cart = data.get("cart", [])
        if not cart:
            return self._resolve_ux_text("save_order_empty", node), "empty_cart"

        profile = self.user_service.get_profile(wa_id)
        customer_name = profile.get("name", "")
        address = data.get("delivery_address", profile.get("address", ""))
        delivery_type = data.get("delivery_type", "")

        order_id, total = self.order_service.save_order(
            wa_id,
            cart,
            customer_name=customer_name,
            address=address,
            delivery_type=delivery_type,
        )
        self.state_manager.patch_data(
            wa_id,
            cart=[],
            delivery_type="",
            delivery_address="",
            last_order_id=order_id,
            awaiting_abandon_confirm=False,
        )
        return (
            self._render(
                self._resolve_ux_text("order_saved_success", node),
                {"order_id": order_id, "total": f"{total:.2f}"},
            ),
            "success",
        )

    def _action_capture_persons(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        personas = parse_persons(text)
        if not personas:
            return "", None
        self.state_manager.patch_data(wa_id, reservation={"personas": personas})
        node = self.nodes.get(self.state_manager.get(wa_id).get("step", ""), {})
        return (
            self._render(
                self._resolve_ux_text("capture_persons_success", node),
                {"personas": personas},
            ),
            "success",
        )

    def _action_capture_date(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        reservation_date = parse_date(text)
        if not reservation_date:
            return "", None
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        reservation = state.get("data", {}).get("reservation", {})
        reservation["fecha"] = reservation_date.isoformat()
        self.state_manager.patch_data(wa_id, reservation=reservation)
        return (
            self._render(
                self._resolve_ux_text("capture_date_success", node),
                {"date": reservation_date.strftime("%d/%m/%Y")},
            ),
            "success",
        )

    def _action_capture_time(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        reservation_time = parse_time(text)
        if not reservation_time:
            return "", None

        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        reservation = state.get("data", {}).get("reservation", {})
        fecha_raw = reservation.get("fecha")
        if not fecha_raw:
            return self._resolve_ux_text("capture_date_missing", node), "missing_date"

        from datetime import date

        reservation_date = date.fromisoformat(fecha_raw)
        valid, error = validate_reservation_slot(reservation_date, reservation_time)
        if not valid:
            return error, None

        reservation["hora"] = reservation_time.strftime("%H:%M")
        self.state_manager.patch_data(wa_id, reservation=reservation)
        return (
            self._render(
                self._resolve_ux_text("capture_time_success", node),
                {"time": reservation_time.strftime("%H:%M")},
            ),
            "success",
        )

    def _action_show_reservation_summary(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        reservation = state.get("data", {}).get("reservation", {})
        if not reservation.get("personas") or not reservation.get("fecha") or not reservation.get("hora"):
            return self._resolve_ux_text("reservation_incomplete", node), "incomplete"

        from datetime import date, time

        summary = self.reservation_service.format_summary(
            personas=int(reservation["personas"]),
            reservation_date=date.fromisoformat(reservation["fecha"]),
            reservation_time=time.fromisoformat(reservation["hora"] + ":00")
            if len(reservation["hora"]) == 5
            else time.fromisoformat(reservation["hora"]),
        )
        return (
            self._render(
                self._resolve_ux_text("reservation_summary_header", node),
                {"summary": summary},
            ),
            None,
        )

    def _action_handle_reservation_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        node = self.nodes.get(self.state_manager.get(wa_id).get("step", ""), {})
        if is_confirmation(text):
            return self._resolve_ux_text("reservation_confirm_yes", node), "confirmed"
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, reservation={})
            return self._resolve_ux_text("reservation_confirm_no", node), "rejected"
        return "", None

    def _action_save_reservation(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        reservation = state.get("data", {}).get("reservation", {})
        required = ("personas", "fecha", "hora")
        if not all(reservation.get(key) for key in required):
            return self._resolve_ux_text("save_reservation_incomplete", node), "incomplete"

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
        return (
            self._render(
                self._resolve_ux_text("save_reservation_success", node),
                {"reservation_id": reservation_id},
            ),
            "success",
        )
