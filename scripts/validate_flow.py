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
    "show_menu": {"success"},
    "show_cart": {"success", "empty_cart"},
    "capture_order": {"success", "empty_cart"},
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
    "show_reservation_summary": {"success", "incomplete"},
    "handle_reservation_confirmation": {"confirmed", "rejected", "incomplete", "invalid"},
    "save_reservation": {"success", "incomplete"},
}

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


def validate_flow(flow: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    nodes = flow.get("nodes", {})
    meta = flow.get("meta", {})

    for command, target in meta.get("global_commands", {}).items():
        if not _step_exists(nodes, str(target)):
            errors.append(f"global_commands[{command!r}] -> {target!r} (nodo inexistente)")

    for key in PHASE2_META_KEYS:
        if not meta.get(key):
            errors.append(f"meta[{key!r}] ausente o vacío (requerido Fase 2)")

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

    return errors


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
    errors = validate_flow(flow)

    if errors:
        for err in errors:
            print(f"  ERROR {err}")
        print(f"\n=== Resultado: {len(errors)} error(es) ===")
        return 1

    print(f"  OK  {len(flow.get('nodes', {}))} nodos")
    print("\n=== Resultado: 0 errores ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
