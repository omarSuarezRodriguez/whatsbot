"""Validador arquitectónico alineado con ARCHITECTURE_LAW.md y FlowEngine real.

Ejecutar desde la raíz del repositorio:

    python validar_arquitectura.py

Prioridad de verdad:
    1. ARCHITECTURE_LAW.md
    2. chatbot/app/core/flow_engine.py
    3. flows/*.json
    4. Este validador (se adapta a la arquitectura, no al revés)

Gobernanza (igual que validate_architecture.py):
    ARCHITECTURE_ALLOW_LAW_CHANGES=1   — cambios en ARCHITECTURE_LAW.md
    ARCHITECTURE_ALLOW_TEST_CHANGES=1  — cambios en tests
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

FLOW_ENGINE_PATH = ROOT / "chatbot" / "app" / "core" / "flow_engine.py"
STATE_MANAGER_PATH = ROOT / "chatbot" / "app" / "core" / "state_manager.py"
GATEWAY_PATH = ROOT / "chatbot" / "gateway.py"
LAW_PATH = ROOT / "ARCHITECTURE_LAW.md"

PYTHON_SCAN_ROOTS = [
    ROOT / "chatbot",
    ROOT / "api",
    ROOT / "services",
]

RUNTIME_ROUTING_PATHS = {
    FLOW_ENGINE_PATH,
    GATEWAY_PATH,
    ROOT / "chatbot" / "app" / "core" / "parser.py",
}

CONFIG_SEED_PATH_PREFIXES = (
    "config/",
    "services/",
)

TEST_PATH_PREFIXES = (
    "tests/",
    "test/",
)

ALLOW_TEST_CHANGES_ENV = "ARCHITECTURE_ALLOW_TEST_CHANGES"
ALLOW_LAW_CHANGES_ENV = "ARCHITECTURE_ALLOW_LAW_CHANGES"

# Deuda de routing documentada en ARCHITECTURE_LAW.md §10 — WARNING, no ERROR.
FLOW_ENGINE_COMMAND_DEBT_MARKERS = (
    'command == "pedido"',
    'command == "inicio"',
    'command == "cancelar"',
    'command in {"menu", "pedido", "reservar"}',
    "intent_command",
)

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

# Claves conocidas hoy; claves nuevas generan WARNING extensible, no ERROR.
KNOWN_META_KEYS = {
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

KNOWN_NODE_KEYS = {
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

KNOWN_NODE_FLAGS = {
    "dual_message",
    "intercept_products",
    "order_greeting_on_greeting",
    "suppress_navigation",
    "suppress_repeat_message",
}

ERRORS: list[str] = []
WARNINGS: list[str] = []
INFOS: list[str] = []
RESULTS: list["CheckResult"] = []

SEP_WIDTH = 62


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool


@dataclass(frozen=True)
class FlowRef:
    state: str
    node: str


def fail(message: str) -> None:
    ERRORS.append(message)


def warn(message: str) -> None:
    WARNINGS.append(message)


def info(message: str) -> None:
    INFOS.append(message)


def run_check(name: str, fn, *args, **kwargs) -> CheckResult:
    errors_before = len(ERRORS)
    fn(*args, **kwargs)
    result = CheckResult(name=name, passed=len(ERRORS) == errors_before)
    RESULTS.append(result)
    return result


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def discover_flow_paths() -> list[Path]:
    flows_dir = ROOT / "flows"
    if flows_dir.is_dir():
        paths = sorted(
            path
            for path in flows_dir.glob("*.json")
            if " copy" not in path.name.lower()
        )
        if paths:
            return paths
    default = ROOT / "flows" / "restaurant_flow.json"
    return [default]


def python_files() -> Iterable[Path]:
    for root in PYTHON_SCAN_ROOTS:
        if root.exists():
            yield from root.rglob("*.py")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_flow(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Falta archivo de flujo: {rel(path)}")
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido en {rel(path)}: {exc}")
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


def parse_qualified_ref(ref: str) -> FlowRef | None:
    if "." not in ref:
        return None
    state, node = ref.split(".", 1)
    if not state or not node:
        return None
    return FlowRef(state, node)


def extract_actions_dict(node: ast.AST) -> dict[str, Any] | None:
    if isinstance(node, ast.Dict):
        return node
    return None


def iter_actions_registry_assignments(tree: ast.AST) -> Iterable[ast.Dict]:
    """Detecta self._actions = {...} y variantes (Assign y AnnAssign)."""
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.AST | None = None

        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value

        if value is None:
            continue

        actions_dict = extract_actions_dict(value)
        if actions_dict is None:
            continue

        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "_actions":
                yield actions_dict
            elif isinstance(target, ast.Name) and target.id == "_actions":
                yield actions_dict


def collect_registered_actions() -> set[str]:
    if not FLOW_ENGINE_PATH.exists():
        fail(f"Falta FlowEngine: {rel(FLOW_ENGINE_PATH)}")
        return set()

    tree = ast.parse(read_text(FLOW_ENGINE_PATH))
    actions: set[str] = set()

    for actions_dict in iter_actions_registry_assignments(tree):
        for key in actions_dict.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                actions.add(key.value)

    if not actions:
        fail("No se encontró el registro FlowEngine._actions.")
    return actions


def collect_action_outcomes() -> dict[str, set[str]]:
    """Outcomes literales devueltos por métodos _action_* (análisis estático)."""
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
            if not isinstance(child, ast.Return) or child.value is None:
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


def collect_flow_actions(flow: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for _state, _node_name, node in iter_flow_nodes(flow):
        for key in ("action", "action_on_input"):
            action = node.get(key)
            if action:
                actions.add(str(action))
    return actions


def node_action_roles(node: dict[str, Any]) -> tuple[str | None, str | None]:
    """Separa acción de entrada (_process_node) y acción de input (_execute_input_action)."""
    entry_action = node.get("action")
    if entry_action is not None:
        entry_action = str(entry_action)

    input_action: str | None = None
    if node.get("input_mode") == "free_text":
        raw = node.get("action_on_input") or node.get("action")
        if raw is not None:
            input_action = str(raw)

    return entry_action, input_action


def concrete_outcomes(action_outcomes: dict[str, set[str]], action_name: str) -> set[str]:
    return action_outcomes.get(action_name, set()) - {"<none>"}


def validate_flow_shape(flow: dict[str, Any], path: Path) -> None:
    if "states" not in flow:
        fail(f"{rel(path)} debe usar 'states' en la raíz. 'nodes' plano legacy prohibido.")
    if "nodes" in flow:
        fail(f"{rel(path)} tiene 'nodes' en la raíz prohibido. Los nodos viven en states.*.nodes.")

    meta = flow.get("meta")
    if not isinstance(meta, dict):
        fail(f"{rel(path)} debe definir objeto meta.")
        return

    global_commands = meta.get("global_commands")
    if not isinstance(global_commands, dict):
        fail(f"{rel(path)} meta.global_commands debe existir y ser un objeto.")

    for key in sorted(set(meta) - KNOWN_META_KEYS):
        warn(f"{rel(path)} meta.{key} no está en el contrato conocido (extensible).")

    states = flow.get("states") or {}
    if not states:
        fail(f"{rel(path)} debe definir al menos un estado.")
        return

    info(f"{rel(path)} define estados: {', '.join(sorted(states))}")

    for state_name, state_def in states.items():
        if not isinstance(state_def, dict):
            fail(f"{rel(path)} estado '{state_name}' debe ser un objeto.")
            continue
        if "nodes" not in state_def:
            fail(f"{rel(path)} estado '{state_name}' debe definir nodes.")
        if "initial" not in state_def:
            warn(f"{rel(path)} estado '{state_name}' no declara initial.")
            continue
        initial = str(state_def["initial"])
        if initial not in (state_def.get("nodes") or {}):
            fail(
                f"{rel(path)} estado '{state_name}' initial '{initial}' "
                "no existe en states.*.nodes."
            )
        if not initial.endswith("_node"):
            warn(
                f"{rel(path)} estado '{state_name}' initial '{initial}' "
                "no sigue la convención *_node."
            )


def validate_node_contract(flow: dict[str, Any], path: Path) -> None:
    for state_name, node_name, node in iter_flow_nodes(flow):
        location = f"{rel(path)} {state_name}.{node_name}"

        if not isinstance(node, dict):
            fail(f"{location} debe ser un objeto.")
            continue

        if not node_name.endswith("_node"):
            warn(f"{location} no sigue la convención de nombre *_node.")

        for key in sorted(set(node) - KNOWN_NODE_KEYS):
            warn(f"{location} tiene clave de nodo desconocida '{key}' (extensible).")

        for key in ("options", "transitions"):
            if key in node and not isinstance(node[key], dict):
                fail(f"{location}.{key} debe ser un objeto.")

        for key in KNOWN_NODE_FLAGS:
            if key in node and not isinstance(node[key], bool):
                fail(f"{location}.{key} debe ser boolean.")

        if "input_mode" in node and node["input_mode"] != "free_text":
            fail(f"{location}.input_mode tiene valor no soportado '{node['input_mode']}'.")

        if "action_on_input" in node and node.get("input_mode") != "free_text":
            fail(f"{location} usa action_on_input pero input_mode no es free_text.")

        if "action" not in node and "message" not in node:
            warn(f"{location} no tiene action ni message.")

        explicit_flow = node.get("flow")
        if explicit_flow is not None and str(explicit_flow) != state_name:
            warn(
                f"{location}.flow='{explicit_flow}' difiere del estado contenedor "
                f"'{state_name}' (FlowEngine inyecta flow={state_name} al normalizar)."
            )


def validate_no_duplicate_node_names(flow: dict[str, Any], path: Path) -> None:
    seen: dict[str, str] = {}
    for state_name, node_name, _node in iter_flow_nodes(flow):
        if node_name in seen:
            fail(
                f"{rel(path)} nombre de nodo '{node_name}' duplicado en estados "
                f"'{seen[node_name]}' y '{state_name}'. FlowEngine aplana nodos por nombre."
            )
        seen[node_name] = state_name


def validate_references(flow: dict[str, Any], path: Path) -> None:
    refs = all_node_refs(flow)
    state_names = set((flow.get("states") or {}).keys())

    def ensure_ref(source: str, ref_value: Any) -> None:
        if ref_value is None:
            return
        if not isinstance(ref_value, str):
            fail(f"{source} debe apuntar a un string de nodo o null.")
            return

        parsed = parse_qualified_ref(ref_value)
        if parsed is None:
            fail(
                f"{source} usa referencia '{ref_value}' sin formato estado.nodo. "
                "Las referencias relativas legacy no están permitidas."
            )
            return

        if parsed.state not in state_names:
            fail(f"{source} apunta a estado inexistente '{parsed.state}'.")

        if parsed not in refs:
            fail(f"{source} apunta a nodo inexistente '{ref_value}'.")

    meta = flow.get("meta") or {}
    for command, target in (meta.get("global_commands") or {}).items():
        ensure_ref(f"{rel(path)} meta.global_commands.{command}", target)

    active_targets = meta.get("active_order_command_targets") or {}
    if not isinstance(active_targets, dict):
        fail(f"{rel(path)} meta.active_order_command_targets debe ser un objeto.")
    else:
        for command, target in active_targets.items():
            ensure_ref(f"{rel(path)} meta.active_order_command_targets.{command}", target)

    for state_name, node_name, node in iter_flow_nodes(flow):
        for option, target in (node.get("options") or {}).items():
            ensure_ref(f"{rel(path)} {state_name}.{node_name}.options.{option}", target)
        for outcome, target in (node.get("transitions") or {}).items():
            ensure_ref(f"{rel(path)} {state_name}.{node_name}.transitions.{outcome}", target)


def validate_action_outcomes_for_role(
    location: str,
    action_name: str,
    role: str,
    transitions: dict[str, Any],
    action_outcomes: dict[str, set[str]],
) -> set[str]:
    known = concrete_outcomes(action_outcomes, action_name)
    if not known:
        info(
            f"{location} acción '{action_name}' ({role}): sin outcomes literales detectables "
            "estáticamente; transiciones no validadas por AST."
        )
        return set()

    for outcome in sorted(known):
        if outcome not in transitions:
            fail(
                f"{location} acción '{action_name}' ({role}) puede devolver outcome "
                f"'{outcome}' pero no hay transitions.{outcome}."
            )
    return known


def validate_action_transitions(flow: dict[str, Any], path: Path) -> None:
    action_outcomes = collect_action_outcomes()

    for state_name, node_name, node in iter_flow_nodes(flow):
        location = f"{rel(path)} {state_name}.{node_name}"
        transitions = node.get("transitions") or {}
        if not transitions:
            continue

        entry_action, input_action = node_action_roles(node)
        static_union: set[str] = set()

        if entry_action and input_action and entry_action != input_action:
            static_union |= validate_action_outcomes_for_role(
                location, entry_action, "entrada", transitions, action_outcomes
            )
            static_union |= validate_action_outcomes_for_role(
                location, input_action, "input", transitions, action_outcomes
            )
        elif input_action:
            static_union |= validate_action_outcomes_for_role(
                location, input_action, "input", transitions, action_outcomes
            )
        elif entry_action:
            static_union |= validate_action_outcomes_for_role(
                location, entry_action, "entrada", transitions, action_outcomes
            )

        for outcome in transitions:
            if static_union and outcome not in static_union:
                info(
                    f"{location} transitions.{outcome} sin outcome literal estático "
                    "en las acciones del nodo; puede ser defensivo o dinámico."
                )


def validate_actions_registered(flows: list[dict[str, Any]]) -> None:
    flow_actions: set[str] = set()
    for flow in flows:
        flow_actions.update(collect_flow_actions(flow))

    registered_actions = collect_registered_actions()

    for action in sorted(flow_actions - registered_actions):
        fail(f"Acción '{action}' usada en JSON pero no registrada en FlowEngine._actions.")

    for action in sorted(registered_actions - flow_actions):
        info(f"Acción '{action}' registrada en FlowEngine pero no usada en ningún flujo JSON.")


def expression_text(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return " ".join(segment.split()) if segment else ""


def is_flow_engine_command_debt(expr: str) -> bool:
    return any(marker in expr for marker in FLOW_ENGINE_COMMAND_DEBT_MARKERS)


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
            fail(
                f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} ramifica por business_id. "
                "Comportamiento por tenant pertenece a config/scope."
            )

        if re.search(r"\b(current_step|step)\s*={2}\s*['\"][A-Za-z0-9_]+['\"]", expr):
            fail(
                f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} enruta por step hardcodeado: {expr}"
            )

        if "command ==" in expr or "command in" in expr or "intent_command" in expr:
            if is_flow_engine_command_debt(expr):
                warn(
                    f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} deuda de routing conocida: {expr}"
                )
            else:
                fail(
                    f"{rel(FLOW_ENGINE_PATH)}:{node.lineno} ramifica por command fuera "
                    f"de deuda documentada: {expr}"
                )


def validate_global_commands_are_json_owned() -> None:
    for file_path in python_files():
        source = read_text(file_path)
        if "GLOBAL_COMMAND_ROUTES" not in source:
            continue

        rel_path = rel(file_path).replace("\\", "/")

        if file_path in RUNTIME_ROUTING_PATHS:
            fail(
                f"{rel_path} usa GLOBAL_COMMAND_ROUTES en capa de runtime. "
                "El routing conversacional pertenece a meta.global_commands del JSON."
            )
            continue

        if rel_path.startswith(CONFIG_SEED_PATH_PREFIXES):
            info(
                f"{rel_path} referencia GLOBAL_COMMAND_ROUTES como semilla/config "
                "(no es routing runtime del motor)."
            )
            continue

        warn(
            f"{rel_path} referencia GLOBAL_COMMAND_ROUTES; confirmar que no sea "
            "routing runtime paralelo al JSON."
        )


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
                fail(
                    f"{rel(file_path)} parece hardcodear comportamiento por tenant: "
                    f"{match.group(0)}"
                )


def validate_gateway_uses_business_scope() -> None:
    if not GATEWAY_PATH.exists():
        warn(f"No se encontró gateway: {rel(GATEWAY_PATH)}")
        return

    source = read_text(GATEWAY_PATH)
    if "business_scope" not in source:
        fail(f"{rel(GATEWAY_PATH)} debe usar business_scope antes del motor del bot.")
    if "handle_incoming_message" not in source:
        warn(
            f"{rel(GATEWAY_PATH)} no expone handle_incoming_message; "
            "confirmar que sigue siendo el único entrypoint."
        )


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
                fail(
                    f"{rel(file_path)} muta estado conversacional directamente: "
                    f"{match.group(0)}"
                )


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
                "contiene copy UX/dominio probable. El copy del flujo pertenece al JSON."
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
            fail(
                f"{rel(FLOW_ENGINE_PATH)} importa o usa detalle de persistencia "
                f"'{token}'. La persistencia pertenece a Services."
            )


def validate_runtime_flow_path_is_single_source() -> None:
    if not FLOW_ENGINE_PATH.exists():
        return

    source = read_text(FLOW_ENGINE_PATH)
    if "FLOWS_PATH" not in source and "flow_path" not in source:
        warn(
            f"{rel(FLOW_ENGINE_PATH)} no referencia FLOWS_PATH/flow_path; "
            "confirmar que la carga del JSON sigue centralizada."
        )
    if "json.load" not in source:
        warn(
            f"{rel(FLOW_ENGINE_PATH)} no carga JSON directamente; "
            "confirmar que el JSON sigue siendo la fuente del mapa."
        )


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
        warn("No se pudo ejecutar git para verificar archivos gobernados.")
        return None

    if diff_result.returncode != 0 or untracked_result.returncode != 0:
        warn("No se pudo verificar archivos gobernados: comando git falló.")
        return None

    changed_files = diff_result.stdout.splitlines() + untracked_result.stdout.splitlines()
    return [
        line.strip().replace("\\", "/")
        for line in changed_files
        if line.strip()
    ]


def validate_architecture_law_not_changed_without_permission() -> None:
    if os.environ.get(ALLOW_LAW_CHANGES_ENV) == "1":
        info(f"Cambios en la ley explícitamente permitidos ({ALLOW_LAW_CHANGES_ENV}=1).")
        return

    if not LAW_PATH.exists():
        fail(f"{rel(LAW_PATH)} debe existir en la raíz del repositorio.")
        return

    changed_files = git_changed_files()
    if changed_files is None:
        return

    if "ARCHITECTURE_LAW.md" in changed_files:
        fail(
            f"{rel(LAW_PATH)} fue modificado. Contrato de solo lectura para tareas normales. "
            f"Si el usuario autorizó cambios en la ley, reejecutar con {ALLOW_LAW_CHANGES_ENV}=1."
        )


def validate_tests_not_changed_without_permission() -> None:
    if os.environ.get(ALLOW_TEST_CHANGES_ENV) == "1":
        info(f"Cambios en tests explícitamente permitidos ({ALLOW_TEST_CHANGES_ENV}=1).")
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
            f"{path} fue modificado. Los tests existentes no deben cambiar salvo solicitud "
            f"explícita. Si está autorizado, reejecutar con {ALLOW_TEST_CHANGES_ENV}=1."
        )


def validate_all(flows: list[dict[str, Any]], flow_paths: list[Path]) -> list[CheckResult]:
    RESULTS.clear()
    for flow, path in zip(flows, flow_paths):
        if not flow:
            continue
        flow_label = rel(path)
        run_check(f"JSON mapa — forma ({flow_label})", validate_flow_shape, flow, path)
        run_check(
            f"JSON mapa — contrato nodos ({flow_label})",
            validate_node_contract,
            flow,
            path,
        )
        run_check(
            f"JSON mapa — nodos únicos ({flow_label})",
            validate_no_duplicate_node_names,
            flow,
            path,
        )
        run_check(f"JSON mapa — referencias ({flow_label})", validate_references, flow, path)
        run_check(
            f"JSON mapa — transiciones/acciones ({flow_label})",
            validate_action_transitions,
            flow,
            path,
        )

    run_check("Python core — acciones registradas", validate_actions_registered, flows)
    run_check("Python core — motor no es mapa", validate_flow_engine_does_not_become_map)
    run_check("Python core — sin copy UX", validate_flow_engine_has_no_ux_copy)
    run_check("Python core — frontera Services", validate_service_boundary)
    run_check("JSON mapa — comandos globales en JSON", validate_global_commands_are_json_owned)
    run_check("JSON mapa — carga centralizada", validate_runtime_flow_path_is_single_source)
    run_check("Multi-tenant — sin tenants hardcodeados", validate_no_hardcoded_tenants)
    run_check("Multi-tenant — gateway usa business_scope", validate_gateway_uses_business_scope)
    run_check("StateManager — ownership del estado", validate_state_manager_ownership)
    run_check(
        "Gobernanza — ARCHITECTURE_LAW.md",
        validate_architecture_law_not_changed_without_permission,
    )
    run_check("Gobernanza — tests", validate_tests_not_changed_without_permission)
    return RESULTS


def print_architecture_report(results: list[CheckResult]) -> int:
    sep = "=" * SEP_WIDTH

    print()
    print(sep)
    print("AUDITORIA ARQUITECTONICA")
    print(sep)
    print()

    for result in results:
        tag = "PASS" if result.passed else "FAIL"
        print(f"[{tag}] {result.name}")

    if INFOS:
        print()
        print("Validación arquitectónica — información:\n")
        for item in INFOS:
            print(f"- {item}")
        print()

    if WARNINGS:
        print("Validación arquitectónica — advertencias:\n")
        for warning in WARNINGS:
            print(f"- {warning}")
        print()

    if ERRORS:
        print("Validación arquitectónica falló:\n")
        for error in ERRORS:
            print(f"- {error}")
        print()

    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed
    coverage = (passed / total * 100.0) if total else 0.0

    print(sep)
    print("RESULTADO FINAL")
    print(sep)
    print()
    if ERRORS:
        print(f"[FAIL] Auditoria fallida -- {len(ERRORS)} error(s) encontrado(s).")
    else:
        print("[OK] Auditoria completada correctamente.")
    print()
    print(f"Cobertura arquitectónica: {coverage:.0f}%")
    print(f"Pruebas ejecutadas:        {total}")
    print(f"Pruebas superadas:         {passed}")
    if failed:
        print(f"Pruebas fallidas:          {failed}")
    print(f"Warnings:                  {len(WARNINGS)}")
    print(f"Errores:                   {len(ERRORS)}")
    print()

    return 1 if ERRORS else 0


def main() -> int:
    flow_paths = discover_flow_paths()
    flows = [load_flow(path) for path in flow_paths]
    results = validate_all(flows, flow_paths)
    return print_architecture_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
