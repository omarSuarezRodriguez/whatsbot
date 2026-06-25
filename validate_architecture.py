"""Architecture guardrails for the JSON-driven WhatsBot flow.

Run from the repository root:

    python scripts/validate_architecture.py

This validator protects the core architecture contract:

    JSON = map
    Python = engine
    Services = business logic
    StateManager = conversational state owner
    business_scope = tenant boundary

It cannot prove the architecture is perfect, but it catches the most common
ways future changes break it.

Governance rule:
    ARCHITECTURE_LAW.md is read-only for normal implementation tasks. It must
    not be changed unless the user explicitly requested governance changes. If
    law changes were explicitly requested, run with:

        ARCHITECTURE_ALLOW_LAW_CHANGES=1 python scripts/validate_architecture.py

    Existing tests must not be changed to make an implementation pass unless
    the user explicitly requested test changes. If test changes were explicitly
    requested, run with:

        ARCHITECTURE_ALLOW_TEST_CHANGES=1 python scripts/validate_architecture.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path.cwd()

FLOW_PATHS = [
    ROOT / "flows" / "restaurant_flow.json",
]

FLOW_ENGINE_PATH = ROOT / "chatbot" / "app" / "core" / "flow_engine.py"
STATE_MANAGER_PATH = ROOT / "chatbot" / "app" / "core" / "state_manager.py"
GATEWAY_PATH = ROOT / "chatbot" / "gateway.py"
LAW_PATH = ROOT / "ARCHITECTURE_LAW.md"

PYTHON_SCAN_ROOTS = [
    ROOT / "chatbot",
    ROOT / "api",
    ROOT / "services",
]

TEST_PATH_PREFIXES = (
    "tests/",
    "test/",
)

ALLOW_TEST_CHANGES_ENV = "ARCHITECTURE_ALLOW_TEST_CHANGES"
ALLOW_LAW_CHANGES_ENV = "ARCHITECTURE_ALLOW_LAW_CHANGES"

LEGACY_ALLOWED_FLOW_ENGINE_COMMAND_BRANCHES = {
    # Known debt. Keep visible here so it cannot grow silently.
    'command == "pedido"',
    'command == "inicio"',
    'command == "cancelar"',
    'command in {"menu", "pedido", "reservar"}',
}

DOMAIN_WORDS = {
    "pedido",
    "pedidos",
    "reservar",
    "reserva",
    "reservas",
    "domicilio",
    "recoger",
    "carrito",
    "mesa",
    "restaurante",
    "cliente",
}

ALLOWED_META_KEYS = {
    "restaurant_name",
    "global_commands",
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
    "active_order_command_targets",
    "capture_order_empty",
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
    "reservation_incomplete",
    "reservation_summary_header",
    "reservation_confirm_yes",
    "reservation_confirm_no",
    "save_reservation_incomplete",
    "save_reservation_success",
    "navigation_hint",
}

ALLOWED_NODE_KEYS = {
    "action",
    "action_on_input",
    "dual_message",
    "fallback",
    "flow",
    "input_mode",
    "intercept_products",
    "message",
    "message_after_action",
    "message_secondary",
    "options",
    "order_greeting_on_greeting",
    "self_loop_behavior",
    "suppress_navigation",
    "suppress_repeat_message",
    "transitions",
}

ALLOWED_NODE_FLAGS = {
    # Current declarative flags. If a new flag is added, make it explicit here.
    "dual_message",
    "intercept_products",
    "order_greeting_on_greeting",
    "suppress_navigation",
    "suppress_repeat_message",
}

ERRORS: list[str] = []
WARNINGS: list[str] = []


@dataclass(frozen=True)
class FlowRef:
    state: str
    node: str


def fail(message: str) -> None:
    ERRORS.append(message)


def warn(message: str) -> None:
    WARNINGS.append(message)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def python_files() -> Iterable[Path]:
    for root in PYTHON_SCAN_ROOTS:
        if root.exists():
            yield from root.rglob("*.py")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_flow(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Missing flow file: {rel(path)}")
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {rel(path)}: {exc}")
        return {}


def iter_flow_nodes(flow: dict[str, Any]):
    for state_name, state_def in (flow.get("states") or {}).items():
        nodes = state_def.get("nodes") or {}
        for node_name, node in nodes.items():
            yield state_name, node_name, node


def all_node_refs(flow: dict[str, Any]) -> set[FlowRef]:
    return {
        FlowRef(state_name, node_name)
        for state_name, node_name, _node in iter_flow_nodes(flow)
    }


def parse_ref(ref: str, current_state: str) -> FlowRef:
    if "." in ref:
        state, node = ref.split(".", 1)
        return FlowRef(state, node)
    return FlowRef(current_state, ref)


def validate_flow_shape(flow: dict[str, Any], path: Path) -> None:
    if "states" not in flow:
        fail(f"{rel(path)} must use top-level 'states'. Legacy top-level 'nodes' is forbidden.")
    if "nodes" in flow:
        fail(f"{rel(path)} has forbidden top-level 'nodes'. Nodes must live under states.*.nodes.")

    meta = flow.get("meta")
    if not isinstance(meta, dict):
        fail(f"{rel(path)} must define object meta.")
        return

    global_commands = meta.get("global_commands")
    if not isinstance(global_commands, dict):
        fail(f"{rel(path)} meta.global_commands must exist and be an object.")

    unknown_meta = sorted(set(meta) - ALLOWED_META_KEYS)
    for key in unknown_meta:
        warn(f"{rel(path)} meta.{key} is not in the known architecture contract.")

    states = flow.get("states") or {}
    if not states:
        fail(f"{rel(path)} must define at least one state.")

    for state_name, state_def in states.items():
        if not isinstance(state_def, dict):
            fail(f"{rel(path)} state '{state_name}' must be an object.")
            continue
        if "nodes" not in state_def:
            fail(f"{rel(path)} state '{state_name}' must define nodes.")
        if "initial" in state_def:
            initial = str(state_def["initial"])
            if initial not in (state_def.get("nodes") or {}):
                fail(f"{rel(path)} state '{state_name}' initial node '{initial}' does not exist.")


def validate_node_contract(flow: dict[str, Any], path: Path) -> None:
    for state_name, node_name, node in iter_flow_nodes(flow):
        location = f"{rel(path)} {state_name}.{node_name}"

        if not isinstance(node, dict):
            fail(f"{location} must be an object.")
            continue

        unknown_keys = sorted(set(node) - ALLOWED_NODE_KEYS)
        for key in unknown_keys:
            warn(f"{location} has unknown node key '{key}'. Add it to the contract if intentional.")

        for key in ("options", "transitions"):
            if key in node and not isinstance(node[key], dict):
                fail(f"{location}.{key} must be an object.")

        for key in ALLOWED_NODE_FLAGS:
            if key in node and not isinstance(node[key], bool):
                fail(f"{location}.{key} must be boolean.")

        if "input_mode" in node and node["input_mode"] != "free_text":
            fail(f"{location}.input_mode has unsupported value '{node['input_mode']}'.")

        if "action_on_input" in node and node.get("input_mode") != "free_text":
            fail(f"{location} uses action_on_input but input_mode is not free_text.")

        if "action" not in node and "message" not in node:
            warn(f"{location} has neither action nor message.")


def validate_references(flow: dict[str, Any], path: Path) -> None:
    refs = all_node_refs(flow)

    def ensure_ref(source: str, ref_value: Any, current_state: str) -> None:
        if ref_value is None:
            return
        if not isinstance(ref_value, str):
            fail(f"{source} must point to a node string or null.")
            return
        target = parse_ref(ref_value, current_state)
        if target not in refs:
            fail(f"{source} points to missing node '{ref_value}'.")

    meta = flow.get("meta") or {}
    for command, target in (meta.get("global_commands") or {}).items():
        ensure_ref(f"{rel(path)} meta.global_commands.{command}", target, "idle")

    for state_name, node_name, node in iter_flow_nodes(flow):
        for option, target in (node.get("options") or {}).items():
            ensure_ref(f"{rel(path)} {state_name}.{node_name}.options.{option}", target, state_name)
        for outcome, target in (node.get("transitions") or {}).items():
            ensure_ref(f"{rel(path)} {state_name}.{node_name}.transitions.{outcome}", target, state_name)


def validate_no_duplicate_node_names(flow: dict[str, Any], path: Path) -> None:
    seen: dict[str, str] = {}
    for state_name, node_name, _node in iter_flow_nodes(flow):
        if node_name in seen:
            fail(
                f"{rel(path)} node name '{node_name}' is duplicated in states "
                f"'{seen[node_name]}' and '{state_name}'. FlowEngine flattens nodes by name."
            )
        seen[node_name] = state_name


def collect_flow_actions(flow: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for _state, _node_name, node in iter_flow_nodes(flow):
        for key in ("action", "action_on_input"):
            action = node.get(key)
            if action:
                actions.add(str(action))
    return actions


def collect_registered_actions() -> set[str]:
    if not FLOW_ENGINE_PATH.exists():
        fail(f"Missing FlowEngine file: {rel(FLOW_ENGINE_PATH)}")
        return set()

    source = read_text(FLOW_ENGINE_PATH)
    tree = ast.parse(source)
    actions: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "_actions"
                and isinstance(node.value, ast.Dict)
            ):
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        actions.add(key.value)

    if not actions:
        fail("Could not find FlowEngine._actions registry.")
    return actions


def validate_actions_registered(flows: list[dict[str, Any]]) -> None:
    flow_actions: set[str] = set()
    for flow in flows:
        flow_actions.update(collect_flow_actions(flow))

    registered_actions = collect_registered_actions()

    for action in sorted(flow_actions - registered_actions):
        fail(f"Flow action '{action}' is used in JSON but not registered in FlowEngine._actions.")

    for action in sorted(registered_actions - flow_actions):
        warn(f"FlowEngine action '{action}' is registered but not used by the JSON flow.")


def collect_action_outcomes() -> dict[str, set[str]]:
    """Collect literal outcomes returned by FlowEngine _action_* methods."""
    if not FLOW_ENGINE_PATH.exists():
        return {}

    tree = ast.parse(read_text(FLOW_ENGINE_PATH))
    outcomes: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_action_"):
            continue

        action_name = node.name.removeprefix("_action_")
        outcomes.setdefault(action_name, set())

        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            value = child.value
            if not isinstance(value, ast.Tuple) or len(value.elts) < 2:
                continue
            outcome_node = value.elts[1]
            if isinstance(outcome_node, ast.Constant):
                if isinstance(outcome_node.value, str):
                    outcomes[action_name].add(outcome_node.value)
                elif outcome_node.value is None:
                    outcomes[action_name].add("<none>")

    return outcomes


def validate_action_transitions(flow: dict[str, Any], path: Path) -> None:
    action_outcomes = collect_action_outcomes()

    for state_name, node_name, node in iter_flow_nodes(flow):
        location = f"{rel(path)} {state_name}.{node_name}"
        transitions = node.get("transitions") or {}
        action_names = [node.get("action"), node.get("action_on_input")]

        for action_name in [str(action) for action in action_names if action]:
            known_outcomes = action_outcomes.get(action_name, set())
            concrete_outcomes = known_outcomes - {"<none>"}

            for outcome in sorted(concrete_outcomes):
                if outcome not in transitions:
                    fail(f"{location} action '{action_name}' can return outcome '{outcome}' but has no transition for it.")

            for outcome in transitions:
                if concrete_outcomes and outcome not in concrete_outcomes:
                    warn(f"{location} declares transition '{outcome}' not found as literal return in action '{action_name}'.")


def expression_text(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return " ".join(segment.split()) if segment else ""


def validate_flow_engine_does_not_become_map() -> None:
    if not FLOW_ENGINE_PATH.exists():
        return

    source = read_text(FLOW_ENGINE_PATH)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue

        expr = expression_text(source, node.test)

        if "business_id" in expr:
            fail(f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} branches on business_id. Tenant behavior belongs to config/scope.")

        if re.search(r"\b(current_step|step)\s*={2}\s*['\"][A-Za-z0-9_]+['\"]", expr):
            fail(f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} routes by hardcoded step name: {expr}")

        if "command ==" in expr or "command in" in expr:
            if expr not in LEGACY_ALLOWED_FLOW_ENGINE_COMMAND_BRANCHES:
                fail(f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} branches on command outside known legacy list: {expr}")

    for legacy_expr in LEGACY_ALLOWED_FLOW_ENGINE_COMMAND_BRANCHES:
        if legacy_expr in source:
            warn(f"{rel(FLOW_ENGINE_PATH)} contains known routing debt: {legacy_expr}")


def validate_global_commands_are_json_owned() -> None:
    for file_path in python_files():
        source = read_text(file_path)
        if "GLOBAL_COMMAND_ROUTES" in source:
            fail(f"{rel(file_path)} uses GLOBAL_COMMAND_ROUTES. Runtime routing belongs to meta.global_commands.")


def validate_no_hardcoded_tenants() -> None:
    tenant_patterns = [
        re.compile(r"business_id\s*={2}\s*['\"][^'\"]+['\"]"),
        re.compile(r"business_id\s+in\s+\[[^\]]+['\"][^'\"]+['\"]"),
        re.compile(r"business_id\s+in\s+\{[^\}]+['\"][^'\"]+['\"]"),
    ]

    for file_path in python_files():
        source = read_text(file_path)
        for pattern in tenant_patterns:
            match = pattern.search(source)
            if match:
                fail(f"{rel(file_path)} appears to hardcode tenant behavior: {match.group(0)}")


def validate_gateway_uses_business_scope() -> None:
    if not GATEWAY_PATH.exists():
        warn(f"Gateway file not found: {rel(GATEWAY_PATH)}")
        return

    source = read_text(GATEWAY_PATH)
    if "business_scope" not in source:
        fail(f"{rel(GATEWAY_PATH)} must use business_scope before calling the bot engine.")
    if "handle_incoming_message" not in source:
        warn(f"{rel(GATEWAY_PATH)} does not expose handle_incoming_message; confirm gateway is still unique entrypoint.")


def validate_state_manager_ownership() -> None:
    forbidden_mutations = [
        re.compile(r"\bstate\s*\[\s*['\"]step['\"]\s*\]\s*="),
        re.compile(r"\bstate\s*\[\s*['\"]flow['\"]\s*\]\s*="),
        re.compile(r"\bstate\s*\[\s*['\"]data['\"]\s*\]\s*="),
    ]

    for file_path in python_files():
        if file_path == STATE_MANAGER_PATH:
            continue
        source = read_text(file_path)
        for pattern in forbidden_mutations:
            match = pattern.search(source)
            if match:
                fail(f"{rel(file_path)} mutates conversational state directly: {match.group(0)}")


def validate_flow_engine_has_no_ux_copy() -> None:
    if not FLOW_ENGINE_PATH.exists():
        return

    tree = ast.parse(read_text(FLOW_ENGINE_PATH))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value.strip()
        if len(value) < 45:
            continue
        lower = value.lower()
        if any(word in lower for word in DOMAIN_WORDS):
            fail(
                f"{rel(FLOW_ENGINE_PATH)}:{getattr(node, 'lineno', '?')} "
                "contains likely UX/domain copy. Flow copy belongs in JSON meta/nodes."
            )


def validate_service_boundary() -> None:
    if not FLOW_ENGINE_PATH.exists():
        return

    source = read_text(FLOW_ENGINE_PATH)
    suspicious_imports = [
        "from models",
        "import models",
        "SessionLocal",
        "get_db",
        "create_engine",
    ]
    for token in suspicious_imports:
        if token in source:
            fail(f"{rel(FLOW_ENGINE_PATH)} imports or uses persistence detail '{token}'. Business persistence belongs to Services.")


def validate_runtime_flow_path_is_single_source() -> None:
    if not FLOW_ENGINE_PATH.exists():
        return

    source = read_text(FLOW_ENGINE_PATH)
    if "FLOWS_PATH" not in source:
        warn(f"{rel(FLOW_ENGINE_PATH)} does not reference FLOWS_PATH; confirm flow loading is still centralized.")
    if "json.load" not in source:
        warn(f"{rel(FLOW_ENGINE_PATH)} does not load JSON directly; confirm JSON remains the flow source.")


def git_changed_files() -> list[str] | None:
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        warn("Could not run git to verify governed file changes.")
        return None

    if diff_result.returncode != 0 or untracked_result.returncode != 0:
        warn("Could not verify governed file changes because a git command failed.")
        return None

    changed_files = diff_result.stdout.splitlines() + untracked_result.stdout.splitlines()
    return [
        line.strip().replace("\\", "/")
        for line in changed_files
        if line.strip()
    ]


def validate_architecture_law_not_changed_without_permission() -> None:
    if os.environ.get(ALLOW_LAW_CHANGES_ENV) == "1":
        warn(f"Architecture law changes explicitly allowed by {ALLOW_LAW_CHANGES_ENV}=1.")
        return

    if not LAW_PATH.exists():
        fail(f"{rel(LAW_PATH)} must exist at the repository root.")
        return

    changed_files = git_changed_files()
    if changed_files is None:
        return

    if "ARCHITECTURE_LAW.md" in changed_files:
        fail(
            f"{rel(LAW_PATH)} was modified. This contract is read-only for normal tasks. "
            f"If the user explicitly authorized law changes, rerun with {ALLOW_LAW_CHANGES_ENV}=1."
        )


def validate_tests_not_changed_without_permission() -> None:
    if os.environ.get(ALLOW_TEST_CHANGES_ENV) == "1":
        warn(f"Test changes explicitly allowed by {ALLOW_TEST_CHANGES_ENV}=1.")
        return

    changed_files = git_changed_files()
    if changed_files is None:
        return

    changed_tests = [
        path
        for path in changed_files
        if path.startswith(TEST_PATH_PREFIXES) or "/tests/" in path or "/test/" in path
    ]

    for path in changed_tests:
        fail(
            f"{path} was modified. Existing tests must not change unless the user explicitly requested it. "
            f"If authorized, rerun with {ALLOW_TEST_CHANGES_ENV}=1."
        )


def validate_all(flows: list[dict[str, Any]], flow_paths: list[Path]) -> None:
    for flow, path in zip(flows, flow_paths):
        if not flow:
            continue
        validate_flow_shape(flow, path)
        validate_node_contract(flow, path)
        validate_no_duplicate_node_names(flow, path)
        validate_references(flow, path)
        validate_action_transitions(flow, path)

    validate_actions_registered(flows)
    validate_flow_engine_does_not_become_map()
    validate_global_commands_are_json_owned()
    validate_no_hardcoded_tenants()
    validate_gateway_uses_business_scope()
    validate_state_manager_ownership()
    validate_flow_engine_has_no_ux_copy()
    validate_service_boundary()
    validate_runtime_flow_path_is_single_source()
    validate_architecture_law_not_changed_without_permission()
    validate_tests_not_changed_without_permission()


def main() -> int:
    flow_paths = [path for path in FLOW_PATHS if path.exists()]
    if not flow_paths:
        flow_paths = FLOW_PATHS

    flows = [load_flow(path) for path in flow_paths]
    validate_all(flows, flow_paths)

    if WARNINGS:
        print("Architecture validation warnings:\n")
        for warning in WARNINGS:
            print(f"- {warning}")
        print()

    if ERRORS:
        print("Architecture validation failed:\n")
        for error in ERRORS:
            print(f"- {error}")
        return 1

    print("Architecture validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
