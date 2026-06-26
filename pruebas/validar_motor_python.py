#!/usr/bin/env python3
"""
pruebas/validar_motor_python.py

Auditoría estática del FlowEngine (motor Python).

NO valida el JSON del flujo ni la arquitectura global del repo.
Enfocado en chatbot/app/core/flow_engine.py y su contrato con:
    StateManager, Services, parser, gateway, flows/*.json

Uso:
    python pruebas/validar_motor_python.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).parent.parent
FLOW_ENGINE_PATH = ROOT / "chatbot" / "app" / "core" / "flow_engine.py"
STATE_MANAGER_PATH = ROOT / "chatbot" / "app" / "core" / "state_manager.py"
PARSER_PATH = ROOT / "chatbot" / "app" / "core" / "parser.py"
GATEWAY_PATH = ROOT / "chatbot" / "gateway.py"
RUNTIME_PATH = ROOT / "chatbot" / "runtime.py"
API_WHATSAPP_PATH = ROOT / "api" / "routes" / "whatsapp.py"

SEP_WIDTH = 30

# ponytail: umbrales estáticos; upgrade path: CLI --max-lines / --max-cc
MAX_METHOD_LINES = 80
MAX_CYCLOMATIC = 18

FLOW_ENGINE_COMMAND_DEBT = (
    'command == "pedido"',
    'command == "inicio"',
    'command == "cancelar"',
    'command in {"menu", "pedido", "reservar"}',
    "intent_command",
)

GENERIC_FLOW_DEFAULTS = frozenset({"idle", "start"})
DOMAIN_FLOW_NAMES = frozenset({"order", "reservation", "menu", "home"})

DOMAIN_WORDS = frozenset({
    "pedido", "pedidos", "reservar", "reserva", "reservas",
    "domicilio", "recoger", "carrito", "mesa", "restaurante", "cliente",
})

PROHIBITED_IMPORT_TOKENS = (
    "sqlalchemy",
    "SessionLocal",
    "get_db",
    "create_engine",
    "from models",
    "import models",
)

PROHIBITED_SIDE_EFFECT_IMPORTS = (
    "notification_service",
    "on_order_pending",
    "on_reservation",
)

CHECK_NAMES = (
    "Motor interpreta JSON",
    "Sin estados hardcodeados",
    "Sin nodos hardcodeados",
    "Sin referencias hardcodeadas",
    "Sin comandos hardcodeados fuera de deuda documentada",
    "Registro de acciones consistente",
    "Resolución de referencias centralizada",
    "Resolución de transiciones centralizada",
    "Separación Action / Transition",
    "Sin lógica de negocio",
    "Sin copy UX",
    "Sin persistencia directa",
    "Sin acceso SQL",
    "Sin mutación directa del estado",
    "StateManager como única fuente del estado",
    "Services como única lógica de negocio",
    "Parser desacoplado",
    "Carga única del JSON",
    "Sin duplicación de navegación",
    "Multi-tenant respetado",
    "Gateway como único entrypoint",
    "Sin dependencias circulares",
    "Métodos dentro del tamaño permitido",
    "Complejidad ciclomática aceptable",
    "Sin código muerto",
    "Sin TODO/FIXME críticos",
    "Sin imports prohibidos",
    "Sin dependencias de implementación",
    "Cobertura del registro de acciones",
    "Todas las acciones implementadas",
    "Acciones sin efectos colaterales indebidos",
)


@dataclass
class Finding:
    level: str  # ERROR | WARNING | INFO
    message: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    findings: list[Finding] = field(default_factory=list)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _expr_text(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return " ".join(segment.split()) if segment else ""


def _is_command_debt(expr: str) -> bool:
    return any(marker in expr for marker in FLOW_ENGINE_COMMAND_DEBT)


def _discover_flow_paths() -> list[Path]:
    flows_dir = ROOT / "flows"
    if not flows_dir.is_dir():
        return []
    return sorted(path for path in flows_dir.glob("*.json") if path.is_file())


def _iter_flow_nodes(flow: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for state_name, state_def in (flow.get("states") or {}).items():
        for node_name, node in (state_def.get("nodes") or {}).items():
            if isinstance(node, dict):
                yield state_name, node_name, node


def _collect_json_actions() -> set[str]:
    actions: set[str] = set()
    for path in _discover_flow_paths():
        try:
            flow = json.loads(_read(path))
        except (json.JSONDecodeError, OSError):
            continue
        for _state, _node, node in _iter_flow_nodes(flow):
            for key in ("action", "action_on_input"):
                value = node.get(key)
                if value:
                    actions.add(str(value))
    return actions


def _cyclomatic_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Assert)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, (ast.ExceptHandler, ast.comprehension)):
            score += 1
    return score


def _method_span(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end = getattr(node, "end_lineno", None)
    if end is not None:
        return end - node.lineno + 1
    if not node.body:
        return 0
    last = node.body[-1]
    last_end = getattr(last, "end_lineno", last.lineno)
    return last_end - node.lineno + 1


def _iter_actions_registry(tree: ast.AST) -> Iterable[ast.Dict]:
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None or not isinstance(value, ast.Dict):
            continue
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "_actions":
                yield value
            elif isinstance(target, ast.Name) and target.id == "_actions":
                yield value


def _registered_actions(tree: ast.AST) -> set[str]:
    actions: set[str] = set()
    for actions_dict in _iter_actions_registry(tree):
        for key in actions_dict.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                actions.add(key.value)
    return actions


def _action_method_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_action_"):
            names.add(node.name.removeprefix("_action_"))
    return names


def _flow_engine_class(tree: ast.AST) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "FlowEngine":
            return node
    return None


def _class_methods(class_node: ast.ClassDef) -> list[ast.FunctionDef]:
    return [n for n in class_node.body if isinstance(n, ast.FunctionDef)]


def _containing_function(tree: ast.AST, lineno: int) -> str | None:
    best: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        if node.lineno <= lineno <= end:
            if best is None or node.lineno > best.lineno:
                best = node
    return best.name if best else None


class MotorAuditor:
    def __init__(self) -> None:
        if not FLOW_ENGINE_PATH.exists():
            raise FileNotFoundError(f"FlowEngine no encontrado: {FLOW_ENGINE_PATH}")
        self.source = _read(FLOW_ENGINE_PATH)
        self.tree = ast.parse(self.source)
        self.class_node = _flow_engine_class(self.tree)
        self.results: list[CheckResult] = []
        self.all_findings: list[Finding] = []

    def _add(self, bucket: list[Finding], level: str, message: str) -> None:
        bucket.append(Finding(level, message))

    def _register(self, name: str, findings: list[Finding]) -> CheckResult:
        passed = not any(f.level == "ERROR" for f in findings)
        result = CheckResult(name=name, passed=passed, findings=findings)
        self.results.append(result)
        self.all_findings.extend(findings)
        return result

    def run(self) -> int:
        for name, method in (
            (CHECK_NAMES[0], self._check_motor_interpreta_json),
            (CHECK_NAMES[1], self._check_sin_estados_hardcodeados),
            (CHECK_NAMES[2], self._check_sin_nodos_hardcodeados),
            (CHECK_NAMES[3], self._check_sin_referencias_hardcodeadas),
            (CHECK_NAMES[4], self._check_sin_comandos_hardcodeados),
            (CHECK_NAMES[5], self._check_registro_acciones_consistente),
            (CHECK_NAMES[6], self._check_referencias_centralizadas),
            (CHECK_NAMES[7], self._check_transiciones_centralizadas),
            (CHECK_NAMES[8], self._check_separacion_action_transition),
            (CHECK_NAMES[9], self._check_sin_logica_negocio),
            (CHECK_NAMES[10], self._check_sin_copy_ux),
            (CHECK_NAMES[11], self._check_sin_persistencia_directa),
            (CHECK_NAMES[12], self._check_sin_acceso_sql),
            (CHECK_NAMES[13], self._check_sin_mutacion_directa_estado),
            (CHECK_NAMES[14], self._check_state_manager_unica_fuente),
            (CHECK_NAMES[15], self._check_services_unica_logica),
            (CHECK_NAMES[16], self._check_parser_desacoplado),
            (CHECK_NAMES[17], self._check_carga_unica_json),
            (CHECK_NAMES[18], self._check_sin_duplicacion_navegacion),
            (CHECK_NAMES[19], self._check_multi_tenant),
            (CHECK_NAMES[20], self._check_gateway_entrypoint),
            (CHECK_NAMES[21], self._check_sin_dependencias_circulares),
            (CHECK_NAMES[22], self._check_tamano_metodos),
            (CHECK_NAMES[23], self._check_complejidad_ciclomatica),
            (CHECK_NAMES[24], self._check_sin_codigo_muerto),
            (CHECK_NAMES[25], self._check_sin_todo_criticos),
            (CHECK_NAMES[26], self._check_sin_imports_prohibidos),
            (CHECK_NAMES[27], self._check_sin_deps_implementacion),
            (CHECK_NAMES[28], self._check_cobertura_registro_acciones),
            (CHECK_NAMES[29], self._check_todas_acciones_implementadas),
            (CHECK_NAMES[30], self._check_acciones_sin_efectos_colaterales),
        ):
            self._register(name, method())
        return self._report()

  # ── checks ────────────────────────────────────────────────────────────────

    def _check_motor_interpreta_json(self) -> list[Finding]:
        f: list[Finding] = []
        required = ("_load_flow", "_normalize_flow", "_apply_flow", "reload_flow")
        if self.class_node is None:
            self._add(f, "ERROR", "No se encontró class FlowEngine.")
            return f
        method_names = {m.name for m in _class_methods(self.class_node)}
        for name in required:
            if name not in method_names:
                self._add(f, "ERROR", f"FlowEngine no define {name}().")
        if "json.load" not in self.source:
            self._add(f, "ERROR", "FlowEngine no carga JSON con json.load.")
        if "states" not in self.source or "_normalize_flow" not in self.source:
            self._add(f, "ERROR", "FlowEngine no normaliza states → nodes planos.")
        if "self.nodes" not in self.source:
            self._add(f, "ERROR", "FlowEngine no expone self.nodes desde el JSON.")
        return f

    def _check_sin_estados_hardcodeados(self) -> list[Finding]:
        f: list[Finding] = []
        pattern = re.compile(
            r"""['"](?:order|reservation|menu|home)['"]"""
        )
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Compare):
                expr = _expr_text(self.source, node)
                for op, comparator in zip(node.ops, node.comparators):
                    if not isinstance(comparator, ast.Constant):
                        continue
                    if not isinstance(comparator.value, str):
                        continue
                    if comparator.value in DOMAIN_FLOW_NAMES:
                        if isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                            self._add(
                                f,
                                "ERROR",
                                f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} ramifica por estado "
                                f"hardcodeado '{comparator.value}': {expr}",
                            )
        return f

    def _check_sin_nodos_hardcodeados(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if value.endswith("_node") and "." not in value:
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{getattr(node, 'lineno', '?')} "
                    f"nodo hardcodeado '{value}'.",
                )
        return f

    def _check_sin_referencias_hardcodeadas(self) -> list[Finding]:
        f: list[Finding] = []
        ref_pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if not ref_pattern.match(value):
                continue
            state, _step = value.split(".", 1)
            if state in GENERIC_FLOW_DEFAULTS:
                self._add(
                    f,
                    "WARNING",
                    f"{_rel(FLOW_ENGINE_PATH)}:{getattr(node, 'lineno', '?')} "
                    f"referencia hardcodeada '{value}' (fallback permitido con deuda).",
                )
            else:
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{getattr(node, 'lineno', '?')} "
                    f"referencia hardcodeada '{value}'.",
                )
        return f

    def _check_sin_comandos_hardcodeados(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If):
                continue
            expr = _expr_text(self.source, node.test)
            if "command ==" not in expr and "command in" not in expr and "intent_command" not in expr:
                continue
            if _is_command_debt(expr):
                self._add(
                    f,
                    "WARNING",
                    f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} deuda de routing conocida: {expr}",
                )
            else:
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} comando hardcodeado fuera de deuda: {expr}",
                )
        return f

    def _check_registro_acciones_consistente(self) -> list[Finding]:
        f: list[Finding] = []
        registered = _registered_actions(self.tree)
        implemented = _action_method_names(self.tree)
        if not registered:
            self._add(f, "ERROR", "No se encontró FlowEngine._actions.")
            return f
        orphan_registry = registered - implemented
        orphan_methods = implemented - registered
        for action in sorted(orphan_registry):
            self._add(f, "ERROR", f"_actions['{action}'] sin método _action_{action}.")
        for action in sorted(orphan_methods):
            self._add(f, "ERROR", f"_action_{action} sin entrada en _actions.")
        if registered == implemented:
            self._add(f, "INFO", f"Registro simétrico: {len(registered)} acciones.")
        return f

    def _check_referencias_centralizadas(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "split":
                if (
                    isinstance(func.value, ast.Constant)
                    and isinstance(func.value.value, str)
                    and "." in func.value.value
                ):
                    continue
                parent_fn = _containing_function(self.tree, node.lineno)
                if parent_fn != "_parse_ref":
                    self._add(
                        f,
                        "ERROR",
                        f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} usa .split() fuera de _parse_ref "
                        f"(en {parent_fn}).",
                    )
        if "_goto_ref" not in self.source or "_parse_ref" not in self.source:
            self._add(f, "ERROR", "Faltan _parse_ref o _goto_ref como API de navegación.")
        return f

    def _check_transiciones_centralizadas(self) -> list[Finding]:
        f: list[Finding] = []
        if "_resolve_transition" not in self.source:
            self._add(f, "ERROR", "Falta _resolve_transition().")
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Subscript):
                continue
            base = node.value
            if not isinstance(base, ast.Attribute) or base.attr != "transitions":
                continue
            parent = _containing_function(self.tree, node.lineno)
            if parent != "_resolve_transition":
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} accede transitions fuera de "
                    f"_resolve_transition (en {parent}).",
                )
        return f

    def _check_separacion_action_transition(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_action_"):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr in {"set_step", "_goto_ref", "_process_node"}:
                    self._add(
                        f,
                        "ERROR",
                        f"{node.name}:{child.lineno} navega directamente ({func.attr}); "
                        "las acciones solo devuelven (mensaje, outcome).",
                    )
        return f

    def _check_sin_logica_negocio(self) -> list[Finding]:
        f: list[Finding] = []
        business_tokens = (
            "INSERT INTO",
            "SELECT ",
            "UPDATE ",
            "DELETE FROM",
            "create_engine",
            "Session(",
        )
        for token in business_tokens:
            if token in self.source:
                self._add(f, "ERROR", f"FlowEngine contiene lógica de persistencia/negocio: {token!r}.")
        if re.search(r"\bre\.compile\(", self.source):
            self._add(
                f,
                "WARNING",
                "FlowEngine define regex propio; confirmar que no duplique parser/Services.",
            )
        allowed_service_attrs = {
            "menu_service", "order_service", "reservation_service",
            "user_service", "admin_service", "state_manager",
        }
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Attribute):
                continue
            if node.value.attr not in allowed_service_attrs:
                continue
            if node.attr.startswith("_"):
                continue
            if node.attr in {"get", "patch_data", "set_step", "reset", "update"}:
                continue
        return f

    def _check_sin_copy_ux(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value.strip()
            if len(value) < 45:
                continue
            lower = value.lower()
            if any(word in lower for word in DOMAIN_WORDS):
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{getattr(node, 'lineno', '?')} "
                    "contiene copy UX/dominio; pertenece al JSON.",
                )
        return f

    def _check_sin_persistencia_directa(self) -> list[Finding]:
        f: list[Finding] = []
        for token in ("json.dump", "pickle.dump", "open(", "STATE_PERSIST_PATH"):
            if token in self.source and token != "open(":
                self._add(f, "ERROR", f"FlowEngine usa persistencia directa ({token}).")
            elif token == "open(" and "json.load" in self.source:
                opens = self.source.count("open(")
                loads = self.source.count("json.load")
                if opens > loads:
                    self._add(f, "WARNING", "FlowEngine abre archivos además del JSON del flujo.")
        return f

    def _check_sin_acceso_sql(self) -> list[Finding]:
        f: list[Finding] = []
        patterns = (
            re.compile(r"\bexecute\s*\("),
            re.compile(r"\bcursor\s*\("),
            re.compile(r"\bsqlalchemy\b"),
            re.compile(r"\braw_connection\b"),
        )
        for pattern in patterns:
            match = pattern.search(self.source)
            if match:
                self._add(f, "ERROR", f"FlowEngine accede SQL directamente ({match.group(0)}).")
        return f

    def _check_sin_mutacion_directa_estado(self) -> list[Finding]:
        f: list[Finding] = []
        forbidden = (
            re.compile(r"\bstate\s*\[\s*['\"]step['\"]\s*\]\s*="),
            re.compile(r"\bstate\s*\[\s*['\"]flow['\"]\s*\]\s*="),
            re.compile(r"\bstate\s*\[\s*['\"]data['\"]\s*\]\s*="),
        )
        for pattern in forbidden:
            match = pattern.search(self.source)
            if match:
                self._add(
                    f,
                    "ERROR",
                    f"FlowEngine muta estado conversacional directamente: {match.group(0)}",
                )
        return f

    def _check_state_manager_unica_fuente(self) -> list[Finding]:
        f: list[Finding] = []
        if "state_manager" not in self.source:
            self._add(f, "ERROR", "FlowEngine no usa state_manager.")
            return f
        mutators = ("set_step", "patch_data", "reset", "update", "set_data")
        found = [m for m in mutators if f"state_manager.{m}" in self.source]
        if not found:
            self._add(f, "ERROR", "FlowEngine no delega mutaciones a state_manager.")
        else:
            self._add(f, "INFO", f"Mutaciones vía state_manager: {', '.join(found)}.")
        return f

    def _check_services_unica_logica(self) -> list[Finding]:
        f: list[Finding] = []
        required = (
            "menu_service", "order_service", "reservation_service", "user_service",
        )
        for svc in required:
            if svc not in self.source:
                self._add(f, "WARNING", f"FlowEngine no referencia {svc}.")
        if "order_service.save_order" in self.source or "reservation_service.save_reservation" in self.source:
            self._add(f, "INFO", "Persistencia delegada a Services.")
        return f

    def _check_parser_desacoplado(self) -> list[Finding]:
        f: list[Finding] = []
        if "infer_user_intent" not in self.source:
            self._add(f, "ERROR", "FlowEngine no usa infer_user_intent del parser.")
        if "from app.core.parser import" not in self.source:
            self._add(f, "ERROR", "FlowEngine no importa parser como módulo desacoplado.")
        if PARSER_PATH.exists() and "flow_engine" in _read(PARSER_PATH):
            self._add(f, "ERROR", "parser.py importa flow_engine (acoplamiento circular).")
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "infer_user_intent":
                self._add(f, "ERROR", "FlowEngine redefine infer_user_intent; usar parser.")
        return f

    def _check_carga_unica_json(self) -> list[Finding]:
        f: list[Finding] = []
        load_sites: list[int] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "load":
                if isinstance(func.value, ast.Name) and func.value.id == "json":
                    load_sites.append(node.lineno)
        if not load_sites:
            self._add(f, "ERROR", "FlowEngine no carga JSON.")
        elif len(load_sites) > 1:
            self._add(
                f,
                "ERROR",
                f"json.load aparece {len(load_sites)} veces (líneas {load_sites}); debe ser única.",
            )
        else:
            self._add(f, "INFO", f"json.load centralizado en línea {load_sites[0]}.")
        return f

    def _check_sin_duplicacion_navegacion(self) -> list[Finding]:
        f: list[Finding] = []
        helpers = ("_goto_ref", "_resolve_global_command", "_resolve_transition", "_process_node")
        for helper in helpers:
            if helper not in self.source:
                self._add(f, "ERROR", f"Falta helper de navegación {helper}().")
        if self.source.count("self._process_node(") < 2:
            self._add(f, "WARNING", "_process_node poco reutilizado; revisar duplicación.")
        return f

    def _check_multi_tenant(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If):
                continue
            expr = _expr_text(self.source, node.test)
            if "business_id" in expr:
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} ramifica por business_id: {expr}",
                )
        return f

    def _check_gateway_entrypoint(self) -> list[Finding]:
        f: list[Finding] = []
        if not GATEWAY_PATH.exists():
            self._add(f, "ERROR", f"No existe {_rel(GATEWAY_PATH)}.")
            return f
        gw = _read(GATEWAY_PATH)
        if "handle_incoming_message" not in gw:
            self._add(f, "ERROR", "gateway no expone handle_incoming_message.")
        if "flow_engine.process_message" not in gw:
            self._add(f, "ERROR", "gateway no delega a flow_engine.process_message.")
        if API_WHATSAPP_PATH.exists():
            api = _read(API_WHATSAPP_PATH)
            if "FlowEngine" in api or "flow_engine import" in api.replace(" ", ""):
                self._add(f, "ERROR", "api/routes/whatsapp importa FlowEngine; usar gateway.")
            if "handle_incoming_message" not in api:
                self._add(f, "ERROR", "api/routes/whatsapp no usa handle_incoming_message.")
        return f

    def _check_sin_dependencias_circulares(self) -> list[Finding]:
        f: list[Finding] = []
        pairs = (
            (FLOW_ENGINE_PATH, "gateway"),
            (FLOW_ENGINE_PATH, "from chatbot.gateway"),
            (PARSER_PATH, "flow_engine"),
            (STATE_MANAGER_PATH, "flow_engine"),
        )
        for path, forbidden in pairs:
            if path.exists() and forbidden in _read(path):
                self._add(
                    f,
                    "ERROR",
                    f"{_rel(path)} importa {forbidden!r} (riesgo circular).",
                )
        return f

    def _check_tamano_metodos(self) -> list[Finding]:
        f: list[Finding] = []
        if self.class_node is None:
            return f
        for method in _class_methods(self.class_node):
            span = _method_span(method)
            if span > MAX_METHOD_LINES:
                self._add(
                    f,
                    "ERROR",
                    f"{method.name} tiene {span} líneas (máx {MAX_METHOD_LINES}).",
                )
        return f

    def _check_complejidad_ciclomatica(self) -> list[Finding]:
        f: list[Finding] = []
        if self.class_node is None:
            return f
        for method in _class_methods(self.class_node):
            cc = _cyclomatic_complexity(method)
            if cc > MAX_CYCLOMATIC:
                self._add(
                    f,
                    "ERROR",
                    f"{method.name} CC={cc} (máx {MAX_CYCLOMATIC}).",
                )
        return f

    def _check_sin_codigo_muerto(self) -> list[Finding]:
        f: list[Finding] = []
        if self.class_node is None:
            return f
        private_methods = [
            m.name for m in _class_methods(self.class_node)
            if m.name.startswith("_") and not m.name.startswith("__")
        ]
        for name in private_methods:
            if name.startswith("_action_"):
                continue
            occurrences = self.source.count(name)
            if occurrences <= 1:
                self._add(f, "WARNING", f"{name} parece no usarse (aparece {occurrences} vez).")
        return f

    def _check_sin_todo_criticos(self) -> list[Finding]:
        f: list[Finding] = []
        for lineno, line in enumerate(self.source.splitlines(), start=1):
            upper = line.upper()
            if "FIXME" in upper or "HACK" in upper:
                self._add(f, "ERROR", f"{_rel(FLOW_ENGINE_PATH)}:{lineno} marcador crítico: {line.strip()}")
            elif "TODO" in upper:
                self._add(f, "WARNING", f"{_rel(FLOW_ENGINE_PATH)}:{lineno} TODO pendiente: {line.strip()}")
        return f

    def _check_sin_imports_prohibidos(self) -> list[Finding]:
        f: list[Finding] = []
        for token in PROHIBITED_IMPORT_TOKENS:
            if token in self.source:
                self._add(f, "ERROR", f"Import prohibido en FlowEngine: {token!r}.")
        return f

    def _check_sin_deps_implementacion(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr.startswith("_") and not node.attr.startswith("__"):
                if isinstance(node.value, ast.Attribute):
                    owner = node.value.attr
                    if owner.endswith("_service") or owner == "admin_service":
                        self._add(
                            f,
                            "ERROR",
                            f"{_rel(FLOW_ENGINE_PATH)}:{node.lineno} usa API privada "
                            f"{owner}.{node.attr}.",
                        )
        return f

    def _check_cobertura_registro_acciones(self) -> list[Finding]:
        f: list[Finding] = []
        registered = _registered_actions(self.tree)
        json_actions = _collect_json_actions()
        if not json_actions:
            self._add(f, "WARNING", "No se encontraron acciones en flows/*.json.")
            return f
        missing = json_actions - registered
        for action in sorted(missing):
            self._add(f, "ERROR", f"Acción JSON '{action}' no está en FlowEngine._actions.")
        coverage = (len(json_actions) - len(missing)) / len(json_actions) * 100.0
        self._add(f, "INFO", f"Cobertura registro: {coverage:.0f}% ({len(json_actions) - len(missing)}/{len(json_actions)}).")
        return f

    def _check_todas_acciones_implementadas(self) -> list[Finding]:
        f: list[Finding] = []
        registered = _registered_actions(self.tree)
        implemented = _action_method_names(self.tree)
        for action in sorted(registered - implemented):
            self._add(f, "ERROR", f"_actions['{action}'] sin implementación _action_{action}.")
        if registered and registered <= implemented:
            self._add(f, "INFO", f"{len(registered)} acciones con implementación.")
        return f

    def _check_acciones_sin_efectos_colaterales(self) -> list[Finding]:
        f: list[Finding] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_action_"):
                continue
            body_source = ast.get_source_segment(self.source, node) or ""
            for token in PROHIBITED_SIDE_EFFECT_IMPORTS:
                if token in body_source:
                    self._add(
                        f,
                        "ERROR",
                        f"{node.name} importa/llama {token!r}; efecto colateral fuera de Services.",
                    )
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if isinstance(func, ast.Name) and func.id == "print":
                    self._add(f, "WARNING", f"{node.name}:{child.lineno} usa print().")
        return f

  # ── report ────────────────────────────────────────────────────────────────

    def _print_checklist(self) -> None:
        for result in self.results:
            tag = "PASS" if result.passed else "FAIL"
            print(f"[{tag}] {result.name}")

    def _report(self) -> int:
        sep = "=" * SEP_WIDTH
        errors = [f for f in self.all_findings if f.level == "ERROR"]
        warnings = [f for f in self.all_findings if f.level == "WARNING"]
        infos = [f for f in self.all_findings if f.level == "INFO"]

        print()
        print(sep)
        print("AUDITORÍA DEL MOTOR")
        print(sep)
        print()
        self._print_checklist()

        if infos:
            print()
            print("-" * SEP_WIDTH)
            print("INFOS:")
            for item in infos:
                print(f"  - {item.message}")

        if warnings:
            print()
            print("-" * SEP_WIDTH)
            print("WARNINGS:")
            for item in warnings:
                print(f"  - {item.message}")

        if errors:
            print()
            print("-" * SEP_WIDTH)
            print("ERRORES:")
            for item in errors:
                print(f"  [X] {item.message}")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        coverage = (passed / total * 100.0) if total else 0.0

        print()
        print(sep)
        print("RESULTADO FINAL")
        print(sep)
        print()
        self._print_checklist()
        print()
        if errors:
            print(f"[FAIL] Auditoría fallida -- {len(errors)} error(s) encontrado(s).")
        else:
            print("[OK] Auditoría completada correctamente.")
        print()
        print(f"Cobertura:          {coverage:.0f}%")
        print(f"Pruebas ejecutadas: {total}")
        print(f"Pruebas superadas:  {passed}")
        if failed:
            print(f"Pruebas fallidas:   {failed}")
        print(f"Warnings:           {len(warnings)}")
        print(f"Errores:            {len(errors)}")
        print()

        return 1 if errors else 0


def main() -> None:
    if not FLOW_ENGINE_PATH.exists():
        print(f"ERROR: FlowEngine no encontrado: {FLOW_ENGINE_PATH}")
        sys.exit(1)
    try:
        auditor = MotorAuditor()
        sys.exit(auditor.run())
    except SyntaxError as exc:
        print(f"ERROR: sintaxis inválida en FlowEngine: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)


if __name__ == "__main__":
    main()
