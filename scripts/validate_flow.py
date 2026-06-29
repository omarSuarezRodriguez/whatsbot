"""Validate conversational flow JSON (stdlib only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ACTION_OUTCOMES: Dict[str, Set[str]] = {
    "welcome_customer": {"success"},
    "show_productos": {"success"},
    "show_cart": {"success", "empty_cart"},
    "capture_order": {"success", "empty_cart", "partial", "ambiguous"},
    "handle_order_confirmation": {"confirmed", "rejected", "invalid"},
    "capture_delivery_type": {
        "domicilio",
        "recoger_has_name",
        "recoger_no_name",
        "invalid",
    },
    "capture_address": {"success_has_name", "success_no_name", "invalid"},
    "capture_customer_name": {"success", "invalid"},
    "save_order": {"success", "empty_cart"},
    "capture_persons": {"success", "invalid"},
    "capture_date": {"success", "invalid"},
    "capture_time": {"success", "missing_date", "invalid"},
    "show_ayuda_summary": {"success", "incomplete"},
    "handle_ayuda_confirmation": {"confirmed", "rejected", "incomplete", "invalid"},
    "save_ayuda": {"success", "incomplete"},
    "handle_order_clarification": {"partial_resolved", "partial_retry", "skip"},
    "handle_order_disambiguation": {"disambiguated", "disambiguate_next", "invalid_choice"},
}

# Meta UX estática (Fase 2). Obligatorias si el flujo usa restaurant_flow estándar.
PHASE2_META_KEYS = (
    "cancel_message",
    "abandon_confirm_prompt",
    "abandon_confirm_continue",
    "abandon_confirm_invalid",
    "order_greeting_while_ordering",
    "welcome_with_name",
    "welcome_without_name",
    "start_fallback",
    "address_prompt",
    "address_prompt_saved",
    "capture_order_empty",
    "capture_order_all_unknown",
    "capture_order_success",
    "empty_cart_message",
    "order_confirm_yes",
    "order_confirm_no",
    "address_saved",
    "save_order_empty",
    "order_saved_success",
    "capture_persons_success",
    "capture_date_success",
    "capture_date_missing",
    "capture_time_success",
    "ayuda_incomplete",
    "ayuda_summary_header",
    "ayuda_confirm_yes",
    "ayuda_confirm_no",
    "save_ayuda_incomplete",
    "save_ayuda_success",
)

# Meta de routing/config (Fase 3). Obligatorias en flujo restaurante migrado.
PHASE3_META_KEYS = (
    "navigation_hint",
    "active_order_command_targets",
)

# Campos de nodo declarativos (Fase 3B idle.start). Validados si el nodo los define.
PHASE3_NODE_OPTIONAL_FLAGS = (
    "self_loop_behavior",
    "suppress_repeat_message",
    "suppress_navigation",
    "intercept_products",
    "order_greeting_on_greeting",
    "dual_message",
)


def _normalize_flow(raw: Dict[str, Any]) -> Dict[str, Any]:
    states = raw.get("states")
    if not states:
        raise ValueError("Flow JSON must define 'states'")
    meta = raw.get("meta", {})
    nodes: Dict[str, Any] = {}
    for state_name, state_def in states.items():
        for step, node in state_def.get("nodes", {}).items():
            flat = dict(node)
            flat.setdefault("flow", state_name)
            nodes[step] = flat
    return {"meta": meta, "nodes": nodes}


def _parse_ref(ref: str, nodes: Dict[str, Any], current_state: str = "idle") -> Tuple[str, str]:
    if "." in ref:
        state, step = ref.split(".", 1)
        return state, step
    node = nodes.get(ref, {})
    state = node.get("flow") or current_state or "idle"
    return state, ref


def _step_exists(nodes: Dict[str, Any], ref: str, current_state: str = "idle") -> bool:
    _, step = _parse_ref(ref, nodes, current_state)
    return step in nodes


def validate_flow(flow: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    nodes = flow.get("nodes", {})
    meta = flow.get("meta", {})

    for command, target in meta.get("global_commands", {}).items():
        if not _step_exists(nodes, str(target)):
            errors.append(f"global_commands[{command!r}] -> {target!r} (nodo inexistente)")

    for key in PHASE2_META_KEYS:
        if not meta.get(key):
            errors.append(f"meta[{key!r}] ausente o vacío (requerido Fase 2)")

    for key in PHASE3_META_KEYS:
        if key == "navigation_hint":
            if key not in meta or meta.get(key) is None:
                errors.append(f"meta[{key!r}] ausente (requerido Fase 3)")
            continue
        if key not in meta or meta.get(key) in (None, ""):
            errors.append(f"meta[{key!r}] ausente o vacío (requerido Fase 3)")
    


    active_targets = meta.get("active_order_command_targets")
    if not isinstance(active_targets, dict):
        errors.append("meta['active_order_command_targets'] ausente o inválido")
    else:
        for command, target in active_targets.items():
            if not _step_exists(nodes, str(target)):
                errors.append(
                    f"meta.active_order_command_targets[{command!r}] -> {target!r} "
                    f"(nodo inexistente)"
                )

    for step, node in nodes.items():
        for option, target in node.get("options", {}).items():
            if not _step_exists(nodes, str(target), node.get("flow", "idle")):
                errors.append(
                    f"nodes[{step!r}].options[{option!r}] -> {target!r} (nodo inexistente)"
                )

        transitions = node.get("transitions")
        if not transitions:
            continue

        actions: Set[str] = set()
        for key in ("action", "action_on_input"):
            action = node.get(key)
            if action:
                actions.add(action)

        for action in actions:
            expected = ACTION_OUTCOMES.get(action)
            if not expected:
                errors.append(
                    f"nodes[{step!r}]: acción {action!r} sin outcomes definidos en validador"
                )
                continue
            missing = expected - set(transitions.keys())
            if missing:
                errors.append(
                    f"nodes[{step!r}].transitions: faltan outcomes {sorted(missing)} "
                    f"para acción {action!r}"
                )

        for outcome, dest in transitions.items():
            if dest is None:
                continue
            if not _step_exists(nodes, str(dest), node.get("flow", "idle")):
                errors.append(
                    f"nodes[{step!r}].transitions[{outcome!r}] -> {dest!r} "
                    f"(nodo inexistente)"
                )

        self_loop = node.get("self_loop_behavior")
        if self_loop is not None and self_loop != "fallback":
            errors.append(
                f"nodes[{step!r}].self_loop_behavior={self_loop!r} "
                f"(solo 'fallback' soportado)"
            )
        if self_loop == "fallback" and not node.get("fallback"):
            errors.append(
                f"nodes[{step!r}]: self_loop_behavior='fallback' requiere node.fallback"
            )

        if node.get("dual_message") and not node.get("message_secondary"):
            warnings.append(
                f"nodes[{step!r}]: dual_message=true sin message_secondary"
            )

        if node.get("suppress_repeat_message") and not node.get("self_loop_behavior"):
            warnings.append(
                f"nodes[{step!r}]: suppress_repeat_message sin self_loop_behavior"
            )

    return errors, warnings


def main() -> int:
    from config.bot_config import FLOWS_PATH

    path = Path(FLOWS_PATH)
    print(f"=== validate_flow: {path} ===\n")
    if not path.is_file():
        print(f"ERROR: archivo no encontrado: {path}")
        return 1

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    flow = _normalize_flow(raw)
    errors, warnings = validate_flow(flow)

    for warn in warnings:
        print(f"  WARN {warn}")

    if errors:
        for err in errors:
            print(f"  ERROR {err}")
        print(f"\n=== Resultado: {len(errors)} error(es), {len(warnings)} aviso(s) ===")
        return 1

    print(f"  OK  {len(flow.get('nodes', {}))} nodos")
    print(
        f"\n=== Resultado: 0 errores"
        + (f", {len(warnings)} aviso(s)" if warnings else "")
        + " ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
