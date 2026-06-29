"""JSON-driven conversational flow engine."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, Optional, Tuple

from app.config import FLOWS_PATH, RESTAURANT_NAME

try:
    from chatbot.business_context import get_prompt as _ctx_get_prompt
except ImportError:  # pragma: no cover
    _ctx_get_prompt = None  # type: ignore[assignment]
from app.core.state_manager import StateManager
from app.services.admin_service import AdminService
from app.services.productos_service import ProductosService
from app.services.order_service import OrderService
from app.services.ayuda_service import AyudaService
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

# ponytail: (path_str, mtime) → parsed flow dict; avoids re-parsing unchanged JSON.
# ceiling: FAT32 mtime granularity is 2s; rapid in-test rewrites may not be detected.
# upgrade: add sha256 of file content as secondary discriminator.
_flow_file_cache: Dict[str, Any] = {}  # key: path_str → (mtime, flow_dict)

_SYSTEM_TECHNICAL_FALLBACK = "Error interno: texto no configurado."

_CLARIFY_SKIP: frozenset = frozenset(["omitir", "saltar", "skip", "omite", "salta"])


class FlowEngine:
    def __init__(
        self,
        state_manager: StateManager,
        productos_service: ProductosService,
        order_service: OrderService,
        ayuda_service: AyudaService,
        user_service: UserService,
        admin_service: AdminService,
        flow_path: str | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.productos_service = productos_service
        self.order_service = order_service
        self.ayuda_service = ayuda_service
        self.user_service = user_service
        self.admin_service = admin_service
        self.flow_path = flow_path or str(FLOWS_PATH)
        self.flow = self._load_flow()
        self._apply_flow(self.flow)

        self._actions: Dict[str, Callable[..., Tuple[str, Optional[str]]]] = {
            "welcome_customer": self._action_welcome_customer,
            "show_productos": self._action_show_productos,
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
            "show_ayuda_summary": self._action_show_ayuda_summary,
            "handle_ayuda_confirmation": self._action_handle_ayuda_confirmation,
            "save_ayuda": self._action_save_ayuda,
            "handle_order_clarification": self._action_handle_order_clarification,
            "handle_order_disambiguation": self._action_handle_order_disambiguation,
        }

    def _load_flow(self) -> Dict[str, Any]:
        path = self.flow_path
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        cached = _flow_file_cache.get(path)
        if cached is not None and mtime is not None and cached[0] == mtime:
            return cached[1]
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        flow = self._normalize_flow(raw)
        if mtime is not None:
            _flow_file_cache[path] = (mtime, flow)
        return flow

    def _apply_flow(self, flow: Dict[str, Any]) -> None:
        self.flow = flow
        self.nodes = flow.get("nodes", {})
        self.meta = flow.get("meta", {})
        self.global_commands = self.meta.get("global_commands", {})
        self.abandon_bypass_commands = frozenset(
            self.meta.get("abandon_bypass_commands") or ("cancelar",)
        )
        self._cart_guard_flows_set = self._build_cart_guard_flows(self.meta)

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
        try:
            biz_name = (
                _ctx_get_prompt("restaurant_name", RESTAURANT_NAME)
                if _ctx_get_prompt is not None
                else RESTAURANT_NAME
            )
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
        return "".join(str(part) for part in parts if part is not None and part != "")

    def _append_navigation(self, message: str, node: Dict[str, Any]) -> str:
        if node.get("suppress_navigation"):
            return message
        hint = node.get("navigation_hint", self.meta.get("navigation_hint", ""))
        if not hint:
            return message
        return f"{message}{hint}"



    @staticmethod
    def _build_cart_guard_flows(meta: Dict[str, Any]) -> frozenset:
        """Compute once in _apply_flow; call-sites use self._cart_guard_flows_set."""
        targets = meta.get("active_order_command_targets") or {}
        flows: set[str] = set()
        for target in targets.values():
            if not isinstance(target, str) or "." not in target:
                continue
            flow_name = target.split(".", 1)[0]
            if flow_name:
                flows.add(flow_name)
        return frozenset(flows)

    def _has_active_order(self, state: Dict[str, Any]) -> bool:
        cart = state.get("data", {}).get("cart", [])
        if not cart:
            return False
        guard_flows = self._cart_guard_flows_set
        if not guard_flows:
            return False
        return state.get("flow") in guard_flows

    def _should_prompt_abandon(self, state: Dict[str, Any]) -> bool:
        if state.get("flow") not in self._cart_guard_flows_set:
            return False
        # ponytail: only guard when there is actually something in the cart to lose.
        # ceiling: empty-cart entry still in guarded flow → no abandon-confirm shown.
        return bool(state.get("data", {}).get("cart"))

    def _target_leaves_guarded_flow(
        self, state: Dict[str, Any], target_ref: str
    ) -> bool:
        guard_flows = self._cart_guard_flows_set
        current_flow = state.get("flow")
        if current_flow not in guard_flows:
            return False
        target_flow, _ = self._parse_ref(str(target_ref), current_flow)
        return target_flow not in guard_flows

    def _prompt_abandon_if_leaving(
        self,
        wa_id: str,
        state: Dict[str, Any],
        current_step: str,
        target_ref: str,
        *,
        bypass: bool = False,
    ) -> Optional[str]:
        if bypass:
            return None
        if not self._should_prompt_abandon(state):
            return None
        if not self._target_leaves_guarded_flow(state, target_ref):
            return None
        self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=True)
        node = self.nodes.get(current_step, {})
        return self._resolve_ux_text("abandon_confirm_prompt", node)


    def _resolve_ux_text(self, meta_key: str, node: Dict[str, Any]) -> str:
        if meta_key in self.meta:
            return str(self.meta[meta_key])
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
        cleaned = normalize_text(text)
        # Continuar pedido (UI nuevo + compat "no")
        if cleaned in {"continuar"} or cleaned.startswith("continuar "):
            self.state_manager.patch_data(wa_id, awaiting_abandon_confirm=False)
            return self._resolve_ux_text("abandon_confirm_continue", node)
        # Cancelar / volver al inicio (UI nuevo + compat "si")
        if cleaned in {"cancelar"} or is_confirmation(text):
            self.state_manager.reset(wa_id)
            return self._goto_ref(wa_id, self._start_ref())
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

        abandon = self._prompt_abandon_if_leaving(
            wa_id,
            state,
            current_step,
            str(target),
            bypass=command in self.abandon_bypass_commands,
        )
        if abandon:
            return abandon

        if command == "inicio":
            self.state_manager.reset(wa_id)

        node = self.nodes.get(target_step, {})
        self.state_manager.set_step(wa_id, target_step, node.get("flow", target_flow))
        if (
            command in {"productos", "pedido", "ayuda"}
            and target_step != current_step
            and not (command == "pedido" and self._has_active_order(state))
        ):
            self.state_manager.patch_data(
                wa_id,
                cart=[],
                ayuda={},
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
        _, default_step = self._parse_ref(self._start_ref(), "idle")
        current_step = state.get("step") or default_step


        
        response = self._process_message_body(
            wa_id,
            text,
            normalized,
            state,
            current_step,
        )
        return response.rstrip("\n") if response else response

        

    def _try_missing_node_recovery(
        self, wa_id: str, node: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        if node:
            return None
        self.state_manager.reset(wa_id)
        return self._goto_ref(wa_id, self._start_ref())

    def _try_node_options(
        self,
        wa_id: str,
        normalized: str,
        current_step: str,
        node: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Optional[str]:
        options = node.get("options", {})
        if normalized not in options:
            return None
        next_ref = options[normalized]
        if self._should_self_loop_fallback(next_ref, current_step, node, state):
            return self._append_navigation(self._node_fallback_message(node), node)
        abandon = self._prompt_abandon_if_leaving(
            wa_id,
            state,
            current_step,
            next_ref,
            bypass=normalized in self.abandon_bypass_commands,
        )
        if abandon:
            return abandon
        return self._goto_ref(
            wa_id,
            next_ref,
            current_flow=state.get("flow", "idle"),
        )

    def _try_normalized_global_command(
        self,
        wa_id: str,
        normalized: str,
        current_step: str,
        state: Dict[str, Any],
    ) -> Optional[str]:
        if normalized not in self.global_commands:
            return None
        response = self._resolve_global_command(
            wa_id, normalized, current_step, state
        )
        if response:
            return response
        return None

    def _try_intent_global_command(
        self,
        wa_id: str,
        intent_command: Optional[str],
        current_step: str,
        state: Dict[str, Any],
        intent: Dict[str, Any],
    ) -> Optional[str]:
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
        return None

    def _try_product_intercept(
        self,
        wa_id: str,
        text: str,
        node: Dict[str, Any],
        current_step: str,
        state: Dict[str, Any],
        intent_command: Optional[str],
        intent: Dict[str, Any],
    ) -> Optional[str]:
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
        return None

    def _try_order_greeting(self, text: str, node: Dict[str, Any]) -> Optional[str]:
        if not (node.get("order_greeting_on_greeting") and is_greeting(text)):
            return None
        greeting = self._resolve_ux_text("order_greeting_while_ordering", node)
        return self._append_navigation(greeting, node)

    def _try_free_text_input(
        self,
        wa_id: str,
        text: str,
        node: Dict[str, Any],
        current_step: str,
        state: Dict[str, Any],
    ) -> Optional[str]:
        if node.get("input_mode") != "free_text":
            return None
        return self._execute_input_action(wa_id, text, node, current_step, state)

    def _process_message_body(
        self,
        wa_id: str,
        text: str,
        normalized: str,
        state: Dict[str, Any],
        current_step: str,
    ) -> str:
        response = self._handle_abandon_confirm(wa_id, text, state)
        if response is not None:
            return response

        node = self.nodes.get(current_step)
        response = self._try_missing_node_recovery(wa_id, node)
        if response is not None:
            return response

        response = self._try_node_options(
            wa_id, normalized, current_step, node, state
        )
        if response is not None:
            return response

        # ponytail: when the node opts in to order_greeting_on_greeting, greetings
        # must be handled before global_commands so that words like "hola" (which are
        # also in meta.global_commands) reach _try_order_greeting instead of triggering
        # the abandon-confirm flow. ceiling: only skips global-command for greeting words.
        if node.get("order_greeting_on_greeting") and is_greeting(text):
            response = self._try_order_greeting(text, node)
            if response is not None:
                return response

        response = self._try_normalized_global_command(
            wa_id, normalized, current_step, state
        )
        if response is not None:
            return response

        productos_tokens = self.productos_service.productos_literal_tokens()
        intent = infer_user_intent(text, menu_tokens=productos_tokens)
        intent_command = intent.get("command")
        if intent_command in {"pedido", "productos", "ayuda"} and is_confirmation(text):
            intent_command = None

        response = self._try_intent_global_command(
            wa_id, intent_command, current_step, state, intent
        )
        if response is not None:
            return response

        response = self._try_product_intercept(
            wa_id, text, node, current_step, state, intent_command, intent
        )
        if response is not None:
            return response

        response = self._try_order_greeting(text, node)
        if response is not None:
            return response

        response = self._try_free_text_input(
            wa_id, text, node, current_step, state
        )
        if response is not None:
            return response

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
        state_data = self.state_manager.get(wa_id).get("data", {})
        return {
            "welcome_line": welcome,
            "address_prompt": address_prompt,
            "order_id": str(state_data.get("order_id", "")),
            "total": str(state_data.get("total", "")),
            "delivery_address": str(state_data.get("delivery_address", "")),
        }

    def _action_welcome_customer(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        return "", None

    def _action_show_productos(self, wa_id: str, text: str = "") -> Tuple[str, Optional[str]]:
        templates = {
            key: str(self.meta[key])
            for key in (
                "productos_empty",
                "productos_category_header",
                "productos_item_line",
                "productos_category_end",
            )
            if key in self.meta
        }
        return self.productos_service.format_productos(templates), None

    def _action_capture_order(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        # ponytail: clear stale pending_* fields on any new order text; covers re-entry
        # after interrupted clarification/disambiguation. ceiling: clears on first visit too.
        data = state.get("data", {})
        stale = {}
        if data.get("pending_unknowns"):
            stale["pending_unknowns"] = []
        if data.get("pending_ambiguous"):
            stale["pending_ambiguous"] = []
        if stale:
            self.state_manager.patch_data(wa_id, **stale)
        node = self.nodes.get(state.get("step", ""), {})
        cart = state.get("data", {}).get("cart", [])
        result = self.order_service.parse_order_text(text, cart, wa_id=wa_id)

        items = result["items"]
        unknown = result.get("unknown") or []
        ambiguous = result.get("ambiguous_items") or []

        if not items and not unknown and not ambiguous:
            return self._resolve_ux_text("capture_order_empty", node), None
        if not items and not ambiguous:
            # ponytail: all-unknown — show the unrecognized list so user can correct.
            # outcome=None keeps user in current node; no transition fires.
            return self._render(
                self._resolve_ux_text("capture_order_all_unknown", node),
                {"unknown_list": ", ".join(unknown)},
            ), None

        if not items and ambiguous:
            # Only ambiguous items — ask for the first one
            first = ambiguous[0]
            candidates_list = "\n".join(
                f"{i + 1}. {c['product']}" for i, c in enumerate(first["candidates"])
            )
            self.state_manager.patch_data(wa_id, pending_ambiguous=ambiguous)
            return self._render(
                self._resolve_ux_text("disambiguate_prompt", node),
                {"segment": first["segment"], "candidates_list": candidates_list},
            ), "ambiguous"

        if unknown or ambiguous:
            # Partial: some recognized, some not / ambiguous
            recognized = "\n".join(f"- {it['qty']}x {it['product']}" for it in items)
            all_unclear = list(unknown) + [a["segment"] for a in ambiguous]
            self.state_manager.patch_data(
                wa_id,
                cart=items,
                pending_unknowns=unknown,
                pending_ambiguous=ambiguous,
            )
            msg = self._render(
                self._resolve_ux_text("capture_order_partial", node),
                {"recognized": recognized, "unknown_list": ", ".join(all_unclear)},
            )
            return msg, "partial"

        self.state_manager.patch_data(wa_id, cart=items)
        return self._render(self._resolve_ux_text("capture_order_success", node), {}), "success"

    def _action_handle_order_clarification(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        data = state.get("data", {})
        pending = list(data.get("pending_unknowns") or [])
        cart = list(data.get("cart") or [])

        if not pending:
            return self._resolve_ux_text("clarify_resolved_all", node), "partial_resolved"

        if normalize_text(text) in _CLARIFY_SKIP:
            pending.pop(0)
            self.state_manager.patch_data(wa_id, pending_unknowns=pending)
            if not pending:
                return self._resolve_ux_text("clarify_resolved_all", node), "partial_resolved"
            return self._render(
                self._resolve_ux_text("clarify_unknown_prompt", node),
                {"unknown_item": pending[0]},
            ), "skip"

        # ponytail: apply_message always returns existing cart items too, so
        # result["items"] is always truthy. Detect by total qty growth instead.
        total_before = sum(it.get("qty", 0) for it in cart)
        result = self.order_service.parse_order_text(text, cart, wa_id=wa_id)
        total_after = sum(it.get("qty", 0) for it in result["items"])
        if total_after > total_before:
            pending.pop(0)
            self.state_manager.patch_data(
                wa_id, cart=result["items"], pending_unknowns=pending
            )
            if not pending:
                return self._resolve_ux_text("clarify_resolved_all", node), "partial_resolved"
            return self._render(
                self._resolve_ux_text("clarify_unknown_prompt", node),
                {"unknown_item": pending[0]},
            ), "partial_retry"

        # nothing recognized — re-ask same item
        return self._render(
            self._resolve_ux_text("clarify_unknown_prompt", node),
            {"unknown_item": pending[0]},
        ), "partial_retry"

    def _action_handle_order_disambiguation(
        self, wa_id: str, text: str
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        data = state.get("data", {})
        pending = list(data.get("pending_ambiguous") or [])
        cart = list(data.get("cart") or [])

        if not pending:
            return self._resolve_ux_text("disambiguate_resolved_all", node), "disambiguated"

        current = pending[0]
        candidates = current.get("candidates", [])
        original_qty = current.get("qty", 1)

        choice = None
        stripped = text.strip()
        if stripped.isdigit():
            idx = int(stripped) - 1
            if 0 <= idx < len(candidates):
                choice = candidates[idx]
        if choice is None:
            norm_input = normalize_text(text)
            for cand in candidates:
                if normalize_text(cand["product"]) == norm_input:
                    choice = cand
                    break

        if choice is None:
            candidates_list = "\n".join(
                f"{i + 1}. {c['product']}" for i, c in enumerate(candidates)
            )
            return self._render(
                self._resolve_ux_text("disambiguate_prompt", node),
                {"segment": current["segment"], "candidates_list": candidates_list},
            ), "invalid_choice"

        # Merge chosen item into cart
        qty_to_add = max(original_qty, 1)
        found = False
        for item in cart:
            if item["product"] == choice["product"]:
                item["qty"] += qty_to_add
                item["subtotal"] = round(item["qty"] * item["unit_price"], 2)
                found = True
                break
        if not found:
            cart.append({
                "product_id": choice["product_id"],
                "product": choice["product"],
                "qty": qty_to_add,
                "unit_price": choice["unit_price"],
                "subtotal": round(qty_to_add * choice["unit_price"], 2),
            })

        pending.pop(0)
        self.state_manager.patch_data(wa_id, cart=cart, pending_ambiguous=pending)

        if not pending:
            return self._resolve_ux_text("disambiguate_resolved_all", node), "disambiguated"

        next_item = pending[0]
        next_candidates_list = "\n".join(
            f"{i + 1}. {c['product']}" for i, c in enumerate(next_item["candidates"])
        )
        return self._render(
            self._resolve_ux_text("disambiguate_prompt", node),
            {"segment": next_item["segment"], "candidates_list": next_candidates_list},
        ), "disambiguate_next"

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
        delivery_address = data.get("delivery_address", "")
        return (
            self._render(
                self._resolve_ux_text("order_saved_success", node),
                {"order_id": order_id, "total": f"{total:.2f}", "delivery_address": delivery_address},
            ),
            "success",
        )

    def _action_capture_persons(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        personas = parse_persons(text)
        if not personas:
            return "", None
        self.state_manager.patch_data(wa_id, ayuda={"personas": personas})
        node = self.nodes.get(self.state_manager.get(wa_id).get("step", ""), {})
        return (
            self._render(
                self._resolve_ux_text("capture_persons_success", node),
                {"personas": personas},
            ),
            "success",
        )

    def _action_capture_date(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        ayuda_date = parse_date(text)
        if not ayuda_date:
            return "", None
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        ayuda = state.get("data", {}).get("ayuda", {})
        ayuda["fecha"] = ayuda_date.isoformat()
        self.state_manager.patch_data(wa_id, ayuda=ayuda)
        return (
            self._render(
                self._resolve_ux_text("capture_date_success", node),
                {"date": ayuda_date.strftime("%d/%m/%Y")},
            ),
            "success",
        )

    def _action_capture_time(self, wa_id: str, text: str) -> Tuple[str, Optional[str]]:
        ayuda_time = parse_time(text)
        if not ayuda_time:
            return "", None

        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        ayuda = state.get("data", {}).get("ayuda", {})
        fecha_raw = ayuda.get("fecha")
        if not fecha_raw:
            return self._resolve_ux_text("capture_date_missing", node), "missing_date"

        from datetime import date

        ayuda_date = date.fromisoformat(fecha_raw)
        valid, error = validate_reservation_slot(ayuda_date, ayuda_time)
        if not valid:
            return error, None

        ayuda["hora"] = ayuda_time.strftime("%H:%M")
        self.state_manager.patch_data(wa_id, ayuda=ayuda)
        return (
            self._render(
                self._resolve_ux_text("capture_time_success", node),
                {"time": ayuda_time.strftime("%H:%M")},
            ),
            "success",
        )

    def _action_show_ayuda_summary(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        ayuda = state.get("data", {}).get("ayuda", {})
        if not ayuda.get("personas") or not ayuda.get("fecha") or not ayuda.get("hora"):
            return self._resolve_ux_text("ayuda_incomplete", node), "incomplete"

        from datetime import date, time

        summary = self.ayuda_service.format_summary(
            personas=int(ayuda["personas"]),
            ayuda_date=date.fromisoformat(ayuda["fecha"]),
            ayuda_time=time.fromisoformat(ayuda["hora"] + ":00")
            if len(ayuda["hora"]) == 5
            else time.fromisoformat(ayuda["hora"]),
        )
        return (
            self._render(
                self._resolve_ux_text("ayuda_summary_header", node),
                {"summary": summary},
            ),
            None,
        )

    def _action_handle_ayuda_confirmation(
        self,
        wa_id: str,
        text: str,
    ) -> Tuple[str, Optional[str]]:
        node = self.nodes.get(self.state_manager.get(wa_id).get("step", ""), {})
        if is_confirmation(text):
            return self._resolve_ux_text("ayuda_confirm_yes", node), "confirmed"
        if is_rejection(text):
            self.state_manager.patch_data(wa_id, ayuda={})
            return self._resolve_ux_text("ayuda_confirm_no", node), "rejected"
        return "", None

    def _action_save_ayuda(
        self,
        wa_id: str,
        text: str = "",
    ) -> Tuple[str, Optional[str]]:
        state = self.state_manager.get(wa_id)
        node = self.nodes.get(state.get("step", ""), {})
        ayuda = state.get("data", {}).get("ayuda", {})
        required = ("personas", "fecha", "hora")
        if not all(ayuda.get(key) for key in required):
            return self._resolve_ux_text("save_ayuda_incomplete", node), "incomplete"

        from datetime import date, time

        ayuda_id = self.ayuda_service.save_ayuda(
            wa_id=wa_id,
            personas=int(ayuda["personas"]),
            ayuda_date=date.fromisoformat(ayuda["fecha"]),
            ayuda_time=time.fromisoformat(
                ayuda["hora"] + ":00"
                if len(ayuda["hora"]) == 5
                else ayuda["hora"]
            ),
        )
        self.state_manager.patch_data(
            wa_id,
            ayuda={},
            last_ayuda_id=ayuda_id,
        )
        return (
            self._render(
                self._resolve_ux_text("save_ayuda_success", node),
                {"ayuda_id": ayuda_id},
            ),
            "success",
        )
