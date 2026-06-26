#!/usr/bin/env python3
"""
pruebas/validar_json.py

Auditor de consistencia lógica del flujo conversacional JSON.

NO valida arquitectura Python ni el FlowEngine.
Valida únicamente la máquina de estados definida en flows/*.json.

Fuente de verdad:
    ARCHITECTURE_LAW.md
    chatbot/app/core/flow_engine.py  (para entender _normalize_flow y _parse_ref)
    flows/*.json

Uso:
    python pruebas/validar_json.py
    python pruebas/validar_json.py flows/mi_flow.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).parent.parent
DEFAULT_FLOW = ROOT / "flows" / "restaurant_flow.json"

# ponytail: límite de profundidad en trazado de caminos; upgrade path: configurable via CLI arg
MAX_PATH_DEPTH = 60


# ─── Tipos ────────────────────────────────────────────────────────────────────


@dataclass
class Finding:
    level: str  # ERROR | WARNING | INFO
    check: str
    message: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    findings: List[Finding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.level == "ERROR" for f in self.findings)


# ─── Resolución de referencias (espeja FlowEngine._parse_ref) ─────────────────


def resolve_step(ref: str) -> str:
    """'state.node' → 'node'; 'node' → 'node'."""
    return ref.split(".", 1)[1] if "." in ref else ref


def resolve_state_from_ref(ref: str, flat_nodes: Dict[str, Any], fallback: str = "idle") -> str:
    if "." in ref:
        return ref.split(".", 1)[0]
    return flat_nodes.get(ref, {}).get("flow", fallback)


# ─── Carga y normalización (espeja FlowEngine._normalize_flow) ───────────────


def load_flow(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def normalize_flow(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Retorna (flat_nodes, node_to_state).
    flat_nodes: node_name → node_dict (con 'flow' inyectado como en FlowEngine).
    node_to_state: node_name → state_name del JSON original.
    """
    flat_nodes: Dict[str, Any] = {}
    node_to_state: Dict[str, str] = {}
    for state_name, state_def in raw.get("states", {}).items():
        for step, node in state_def.get("nodes", {}).items():
            flat = dict(node)
            flat.setdefault("flow", state_name)
            flat_nodes[step] = flat
            node_to_state[step] = state_name
    return flat_nodes, node_to_state


# ─── Construcción del grafo ───────────────────────────────────────────────────


def build_graph(flat_nodes: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Adyacencia: node_name → set de nodos destino (solo los que existen)."""
    graph: Dict[str, Set[str]] = {n: set() for n in flat_nodes}
    for node_name, node in flat_nodes.items():
        for ref in node.get("options", {}).values():
            if ref:
                step = resolve_step(ref)
                if step in flat_nodes:
                    graph[node_name].add(step)
        for ref in (node.get("transitions") or {}).values():
            if ref:
                step = resolve_step(ref)
                if step in flat_nodes:
                    graph[node_name].add(step)
    return graph


def collect_all_refs(
    flat_nodes: Dict[str, Any],
    global_commands: Dict[str, Any],
    active_order_targets: Dict[str, Any],
) -> List[Tuple[str, str]]:
    """[(source_label, ref_string), ...] para todas las referencias del flujo."""
    refs: List[Tuple[str, str]] = []
    for cmd, ref in global_commands.items():
        if ref:
            refs.append((f"global_commands.{cmd}", ref))
    for cmd, ref in active_order_targets.items():
        if ref:
            refs.append((f"active_order_command_targets.{cmd}", ref))
    for node_name, node in flat_nodes.items():
        for opt, ref in node.get("options", {}).items():
            if ref:
                refs.append((f"{node_name}.options.{opt}", ref))
        for outcome, ref in (node.get("transitions") or {}).items():
            if ref:
                refs.append((f"{node_name}.transitions.{outcome}", ref))
    return refs


def compute_entry_points(
    states: Dict[str, Any],
    global_commands: Dict[str, Any],
    active_order_targets: Dict[str, Any],
    flat_nodes: Dict[str, Any],
) -> Set[str]:
    entries: Set[str] = set()
    for ref in global_commands.values():
        if ref:
            s = resolve_step(ref)
            if s in flat_nodes:
                entries.add(s)
    for ref in active_order_targets.values():
        if ref:
            s = resolve_step(ref)
            if s in flat_nodes:
                entries.add(s)
    for state_def in states.values():
        initial = state_def.get("initial")
        if initial and initial in flat_nodes:
            entries.add(initial)
    return entries


def compute_reachable(entry_points: Set[str], graph: Dict[str, Set[str]]) -> Set[str]:
    visited: Set[str] = set()
    queue = deque(entry_points)
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


# ─── SCCs (Tarjan iterativo) ──────────────────────────────────────────────────


def find_sccs(graph: Dict[str, Set[str]], nodes: Set[str]) -> List[Set[str]]:
    """Tarjan iterativo. Retorna lista de SCCs (conjuntos de nodos)."""
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    stack: List[str] = []
    sccs: List[Set[str]] = []
    counter = [0]

    # ponytail: iterativo para evitar RecursionError en flujos grandes (recursivo = O(n) stack frames)
    def _visit(start: str) -> None:
        # Emula la recursión con una pila explícita de (node, iterator_state)
        call_stack: List[Tuple[str, Any]] = [(start, iter(sorted(graph.get(start, set()) & nodes)))]
        index[start] = lowlink[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack[start] = True

        while call_stack:
            v, children = call_stack[-1]
            try:
                w = next(children)
                if w not in nodes:
                    continue
                if w not in index:
                    index[w] = lowlink[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    call_stack.append((w, iter(sorted(graph.get(w, set()) & nodes))))
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            except StopIteration:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
                if lowlink[v] == index[v]:
                    scc: Set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        scc.add(w)
                        if w == v:
                            break
                    sccs.append(scc)

    for v in sorted(nodes):
        if v not in index:
            _visit(v)

    return sccs


# ─── Auditor principal ────────────────────────────────────────────────────────


class FlowAuditor:
    def __init__(self, flow_path: Path) -> None:
        self.flow_path = flow_path
        self.raw = load_flow(flow_path)
        self.meta: Dict[str, Any] = self.raw.get("meta", {})
        self.states: Dict[str, Any] = self.raw.get("states", {})
        self.global_commands: Dict[str, Any] = self.meta.get("global_commands", {})
        self.active_order_targets: Dict[str, Any] = self.meta.get("active_order_command_targets", {})
        self.flat_nodes, self.node_to_state = normalize_flow(self.raw)
        self.graph = build_graph(self.flat_nodes)
        self.entry_points = compute_entry_points(
            self.states, self.global_commands, self.active_order_targets, self.flat_nodes
        )
        self.reachable = compute_reachable(self.entry_points, self.graph)
        self.all_refs = collect_all_refs(
            self.flat_nodes, self.global_commands, self.active_order_targets
        )
        self.results: List[CheckResult] = []
        self._coverage_stats: Dict[str, Any] = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _label(self, node_name: str) -> str:
        state = self.node_to_state.get(node_name, "?")
        return f"{state}.{node_name}"

    def _register(self, name: str, findings: List[Finding]) -> CheckResult:
        has_errors = any(f.level == "ERROR" for f in findings)
        result = CheckResult(name=name, passed=not has_errors, findings=findings)
        self.results.append(result)
        return result

    def _outgoing_refs(self, node: Dict[str, Any]) -> List[str]:
        refs = list(node.get("options", {}).values())
        refs += list((node.get("transitions") or {}).values())
        return [r for r in refs if r is not None]

    def _non_null_transitions(self, node: Dict[str, Any]) -> List[str]:
        return [r for r in (node.get("transitions") or {}).values() if r is not None]

    # ── 1. Estados definidos ──────────────────────────────────────────────────

    def check_states_defined(self) -> CheckResult:
        findings: List[Finding] = []
        if not self.states:
            findings.append(Finding("ERROR", "Estados definidos", "El JSON no define 'states'."))
            return self._register("Estados definidos", findings)
        for state_name, state_def in self.states.items():
            if not state_def.get("nodes"):
                findings.append(Finding("ERROR", "Estados definidos", f"Estado '{state_name}' no tiene nodos."))
        return self._register("Estados definidos", findings)

    # ── 2. initial válido ─────────────────────────────────────────────────────

    def check_initial_valid(self) -> CheckResult:
        findings: List[Finding] = []
        for state_name, state_def in self.states.items():
            initial = state_def.get("initial")
            if not initial:
                findings.append(Finding("ERROR", "initial válido", f"Estado '{state_name}': falta campo 'initial'."))
                continue
            state_nodes = set(state_def.get("nodes", {}).keys())
            if initial not in state_nodes:
                findings.append(Finding(
                    "ERROR", "initial válido",
                    f"Estado '{state_name}': initial='{initial}' no pertenece a sus nodos. "
                    f"Nodos disponibles: {sorted(state_nodes)}",
                ))
            elif initial not in self.reachable:
                findings.append(Finding(
                    "WARNING", "initial válido",
                    f"Estado '{state_name}': initial='{initial}' no es alcanzable desde ningún punto de entrada.",
                ))
        return self._register("initial válido", findings)

    # ── 3. Nodos alcanzables ──────────────────────────────────────────────────

    def check_nodes_reachable(self) -> CheckResult:
        findings: List[Finding] = []
        orphans = sorted(set(self.flat_nodes.keys()) - self.reachable)
        for node_name in orphans:
            findings.append(Finding("ERROR", "Nodos alcanzables", f"Nodo huérfano: '{self._label(node_name)}' nunca puede alcanzarse."))
        return self._register("Nodos alcanzables", findings)

    # ── 4. Estados alcanzables ────────────────────────────────────────────────

    def check_states_reachable(self) -> CheckResult:
        findings: List[Finding] = []
        for state_name, state_def in self.states.items():
            state_nodes = set(state_def.get("nodes", {}).keys())
            if not (state_nodes & self.reachable):
                findings.append(Finding("ERROR", "Estados alcanzables", f"Estado huérfano: '{state_name}' — ningún nodo es alcanzable."))
        return self._register("Estados alcanzables", findings)

    # ── 5. Referencias válidas ────────────────────────────────────────────────

    def check_refs_valid(self) -> CheckResult:
        findings: List[Finding] = []
        seen: Set[str] = set()
        for source, ref in self.all_refs:
            key = f"{source}->{ref}"
            if key in seen:
                continue
            seen.add(key)
            step = resolve_step(ref)
            if step not in self.flat_nodes:
                findings.append(Finding("ERROR", "Referencias válidas", f"Referencia rota: '{source}' -> '{ref}' (nodo '{step}' no existe)."))
        return self._register("Referencias válidas", findings)

    # ── 6. Options válidas ────────────────────────────────────────────────────

    def check_options_valid(self) -> CheckResult:
        findings: List[Finding] = []
        for node_name, node in self.flat_nodes.items():
            label = self._label(node_name)
            for opt, ref in node.get("options", {}).items():
                if not ref:
                    findings.append(Finding("WARNING", "Options válidas", f"'{label}': opción '{opt}' tiene valor null/vacío."))
                    continue
                step = resolve_step(ref)
                if step not in self.flat_nodes:
                    findings.append(Finding("ERROR", "Options válidas", f"'{label}': opcion '{opt}' -> '{ref}' (nodo '{step}' no existe)."))
                elif step == node_name:
                    behavior = node.get("self_loop_behavior")
                    level = "INFO" if behavior == "fallback" else "WARNING"
                    findings.append(Finding(level, "Options válidas", f"'{label}': opción '{opt}' apunta al mismo nodo (self-loop). self_loop_behavior={behavior!r}."))
        return self._register("Options válidas", findings)

    # ── 7. Transitions válidas ────────────────────────────────────────────────

    def check_transitions_valid(self) -> CheckResult:
        findings: List[Finding] = []
        for node_name, node in self.flat_nodes.items():
            label = self._label(node_name)
            for outcome, ref in (node.get("transitions") or {}).items():
                if ref is None:
                    findings.append(Finding("INFO", "Transitions válidas", f"'{label}': transition '{outcome}' = null (el nodo permanece en su posicion)."))
                    continue
                step = resolve_step(ref)
                if step not in self.flat_nodes:
                    findings.append(Finding("ERROR", "Transitions válidas", f"'{label}': transition '{outcome}' -> '{ref}' (nodo '{step}' no existe)."))
                elif step == node_name:
                    findings.append(Finding("WARNING", "Transitions válidas", f"'{label}': transition '{outcome}' apunta al mismo nodo (self-loop en transition)."))
        return self._register("Transitions válidas", findings)

    # ── 8. Global commands válidos ────────────────────────────────────────────

    def check_global_commands_valid(self) -> CheckResult:
        findings: List[Finding] = []
        if not self.global_commands:
            findings.append(Finding("WARNING", "Global commands válidos", "meta.global_commands está vacío o ausente."))
            return self._register("Global commands válidos", findings)
        for cmd, ref in self.global_commands.items():
            if not ref:
                findings.append(Finding("WARNING", "Global commands válidos", f"global_commands.{cmd} tiene valor vacío."))
                continue
            step = resolve_step(ref)
            if step not in self.flat_nodes:
                findings.append(Finding("ERROR", "Global commands válidos", f"global_commands.{cmd} -> '{ref}' (nodo '{step}' no existe)."))
        # Verificar que exista 'inicio' (usado como _start_ref por el FlowEngine)
        if "inicio" not in self.global_commands:
            findings.append(Finding("WARNING", "Global commands válidos", "global_commands no define 'inicio'. FlowEngine usa 'idle.start' como fallback."))
        return self._register("Global commands válidos", findings)

    # ── 9. Active order command targets ───────────────────────────────────────

    def check_active_order_targets(self) -> CheckResult:
        findings: List[Finding] = []
        for cmd, ref in self.active_order_targets.items():
            if not ref:
                findings.append(Finding("WARNING", "Active order command targets", f"active_order_command_targets.{cmd} tiene valor vacío."))
                continue
            step = resolve_step(ref)
            if step not in self.flat_nodes:
                findings.append(Finding("ERROR", "Active order command targets", f"active_order_command_targets.{cmd} -> '{ref}' (nodo '{step}' no existe)."))
        return self._register("Active order command targets", findings)

    # ── 10. Cobertura del flujo ───────────────────────────────────────────────

    def check_coverage(self) -> CheckResult:
        findings: List[Finding] = []
        total_nodes = len(self.flat_nodes)
        total_states = len(self.states)
        reachable_nodes = len(self.reachable & set(self.flat_nodes))
        reachable_states = len({self.node_to_state[n] for n in self.reachable if n in self.node_to_state})

        node_pct = (reachable_nodes / total_nodes * 100) if total_nodes else 0.0
        state_pct = (reachable_states / total_states * 100) if total_states else 0.0
        coverage = (node_pct + state_pct) / 2

        total_refs = len(self.all_refs)
        broken_refs = sum(1 for _, ref in self.all_refs if resolve_step(ref) not in self.flat_nodes)
        valid_refs = total_refs - broken_refs

        total_transitions = sum(len(n.get("transitions") or {}) for n in self.flat_nodes.values())
        total_options = sum(len(n.get("options") or {}) for n in self.flat_nodes.values())

        self._coverage_stats = {
            "estados": total_states,
            "nodos": total_nodes,
            "referencias": total_refs,
            "referencias_validas": valid_refs,
            "transitions": total_transitions,
            "options": total_options,
            "estados_alcanzables": reachable_states,
            "nodos_alcanzables": reachable_nodes,
            "estados_pct": state_pct,
            "nodos_pct": node_pct,
            "cobertura": coverage,
        }

        if coverage < 100.0:
            level = "ERROR" if coverage < 80 else "WARNING"
            findings.append(Finding(
                level, "Cobertura del flujo",
                f"Cobertura {coverage:.1f}%: {reachable_nodes}/{total_nodes} nodos alcanzables, "
                f"{reachable_states}/{total_states} estados alcanzables.",
            ))
        return self._register("Cobertura del flujo", findings)

    # ── 11. Simulación completa ───────────────────────────────────────────────

    def check_simulation(self) -> CheckResult:
        """BFS que simula usuarios recorriendo todos los caminos posibles."""
        findings: List[Finding] = []
        visited_nodes: Set[str] = set()
        visited_edges: Set[Tuple[str, str]] = set()
        queue: deque = deque((ep, None) for ep in self.entry_points)

        while queue:
            node_name, prev = queue.popleft()
            if prev is not None:
                edge = (prev, node_name)
                if edge in visited_edges:
                    continue
                visited_edges.add(edge)

            if node_name in visited_nodes:
                continue
            visited_nodes.add(node_name)

            node = self.flat_nodes.get(node_name)
            if not node:
                findings.append(Finding("ERROR", "Simulación completa", f"Nodo '{node_name}' referenciado pero no existe en el flujo."))
                continue

            for ref in self._outgoing_refs(node):
                step = resolve_step(ref)
                if step in self.flat_nodes and step not in visited_nodes:
                    queue.append((step, node_name))

        never_visited = sorted(set(self.flat_nodes.keys()) - visited_nodes)
        for n in never_visited:
            findings.append(Finding(
                "WARNING", "Simulación completa",
                f"Nodo '{self._label(n)}' nunca visitado durante la simulación.",
            ))

        return self._register("Simulación completa", findings)

    # ── 12. Caminos completos ─────────────────────────────────────────────────

    def check_complete_paths(self) -> CheckResult:
        """Traza caminos desde cada entrada y verifica que cada salto sea válido."""
        findings: List[Finding] = []
        invalid_jumps: List[str] = []

        for node_name, node in self.flat_nodes.items():
            if node_name not in self.reachable:
                continue
            label = self._label(node_name)
            for opt, ref in node.get("options", {}).items():
                if not ref:
                    continue
                step = resolve_step(ref)
                if step not in self.flat_nodes:
                    invalid_jumps.append(f"{label} -[opcion '{opt}']-> '{ref}'")
            for outcome, ref in (node.get("transitions") or {}).items():
                if not ref:
                    continue
                step = resolve_step(ref)
                if step not in self.flat_nodes:
                    invalid_jumps.append(f"{label} -[transition '{outcome}']-> '{ref}'")

        for jump in invalid_jumps:
            findings.append(Finding("ERROR", "Caminos completos", f"Salto inválido en camino alcanzable: {jump}"))

        # Mostrar caminos representativos (INFO)
        sample_paths = self._trace_sample_paths()
        for path in sample_paths:
            findings.append(Finding("INFO", "Caminos completos", " -> ".join(path)))

        return self._register("Caminos completos", findings)

    def _trace_sample_paths(self) -> List[List[str]]:
        """
        DFS desde entradas. Retorna hasta MAX_SAMPLE_PATHS caminos representativos.
        Cada camino termina en un nodo terminal o en el primer ciclo detectado.
        """
        MAX_SAMPLE_PATHS = 8  # ponytail: suficiente para auditoría; upgrade path: CLI arg
        paths: List[List[str]] = []
        seen_ends: Set[str] = set()

        def dfs(node: str, path: List[str], in_path: Set[str]) -> None:
            if len(paths) >= MAX_SAMPLE_PATHS:
                return
            if len(path) > MAX_PATH_DEPTH:
                paths.append(path + ["...(limite)"])
                return
            neighbors = sorted(self.graph.get(node, set()))
            if not neighbors:
                end_key = "->".join(path)
                if end_key not in seen_ends:
                    seen_ends.add(end_key)
                    paths.append(list(path))
                return
            for n in neighbors:
                if len(paths) >= MAX_SAMPLE_PATHS:
                    return
                if n in in_path:
                    cycle_key = f"{path[-1]}->{n}"
                    if cycle_key not in seen_ends:
                        seen_ends.add(cycle_key)
                        paths.append(path + [f"(loop->{n})"])
                    continue
                dfs(n, path + [n], in_path | {n})

        for entry in sorted(self.entry_points):
            if len(paths) >= MAX_SAMPLE_PATHS:
                break
            dfs(entry, [entry], {entry})

        return paths

    # ── 13. Nodos terminales ──────────────────────────────────────────────────

    def check_terminal_nodes(self) -> CheckResult:
        """Nodos sin salida propia (sin opciones ni transiciones no-null)."""
        findings: List[Finding] = []
        for node_name, node in self.flat_nodes.items():
            if node_name not in self.reachable:
                continue
            has_options = bool(node.get("options"))
            has_non_null_trans = bool(self._non_null_transitions(node))
            if not has_options and not has_non_null_trans:
                action = node.get("action", "—")
                findings.append(Finding(
                    "INFO", "Nodos terminales",
                    f"'{self._label(node_name)}' es terminal (action={action}). "
                    "Sin opciones ni transiciones propias. Solo escapable vía global_commands.",
                ))
        return self._register("Nodos terminales", findings)

    # ── 14. Estados terminales ────────────────────────────────────────────────

    def check_terminal_states(self) -> CheckResult:
        """Estados cuyos nodos no tienen salida hacia otros estados (solo global_commands)."""
        findings: List[Finding] = []
        for state_name, state_def in self.states.items():
            state_node_names = set(state_def.get("nodes", {}).keys())
            has_cross_exit = False
            for node_name, node in state_def.get("nodes", {}).items():
                for ref in self._outgoing_refs(node):
                    step = resolve_step(ref)
                    if step not in state_node_names and step in self.flat_nodes:
                        has_cross_exit = True
                        break
                if has_cross_exit:
                    break
            if not has_cross_exit:
                findings.append(Finding(
                    "WARNING", "Estados terminales",
                    f"Estado '{state_name}' no tiene salidas directas a otros estados. "
                    "Solo escapa vía global_commands.",
                ))
        return self._register("Estados terminales", findings)

    # ── 15. Ciclos controlados ────────────────────────────────────────────────

    def check_cycles(self) -> CheckResult:
        """
        Usa SCCs de Tarjan.

        En un bot conversacional, todos los nodos forman naturalmente un gran SCC
        porque siempre existe un camino de regreso al inicio. Esto es CORRECTO.

        Criterios:
        - SCC con salida externa → INFO (ciclo controlado con escape).
        - SCC sin salida pero que contiene puntos de entrada globales (home, menu...)
          → INFO (bucle conversacional principal, diseño esperado).
        - SCC sin salida Y sin ningún punto de entrada global → ERROR (ciclo trampa).
        - Single-node SCCs → manejados por check_self_loops.
        """
        findings: List[Finding] = []
        sccs = find_sccs(self.graph, set(self.flat_nodes.keys()))

        for scc in sccs:
            if len(scc) < 2:
                continue
            if not (scc & self.reachable):
                continue

            has_exit = any(
                neighbor not in scc and neighbor in self.flat_nodes
                for node in scc
                for neighbor in self.graph.get(node, set())
            )
            # Si el SCC contiene al menos un punto de entrada global (home, menu...)
            # es el bucle conversacional principal: comportamiento esperado.
            has_global_anchor = bool(scc & self.entry_points)
            members = ", ".join(sorted(scc))

            if has_exit:
                findings.append(Finding("INFO", "Ciclos controlados", f"Ciclo con salida: [{members}]"))
            elif has_global_anchor:
                findings.append(Finding(
                    "INFO", "Ciclos controlados",
                    f"Bucle conversacional principal ({len(scc)} nodos). "
                    "Todos los caminos regresan a puntos de entrada globales. Correcto.",
                ))
            else:
                findings.append(Finding(
                    "ERROR", "Ciclos controlados",
                    f"Ciclo trampa sin salida ni punto de entrada global: [{members}]",
                ))

        return self._register("Ciclos controlados", findings)

    # ── 16. Self-loops válidos ────────────────────────────────────────────────

    def check_self_loops(self) -> CheckResult:
        findings: List[Finding] = []
        for node_name, node in self.flat_nodes.items():
            if node_name not in self.reachable:
                continue
            label = self._label(node_name)
            loop_via_opts = [opt for opt, ref in node.get("options", {}).items() if ref and resolve_step(ref) == node_name]
            loop_via_trans = [out for out, ref in (node.get("transitions") or {}).items() if ref and resolve_step(ref) == node_name]

            if not loop_via_opts and not loop_via_trans:
                continue

            via_parts = []
            if loop_via_opts:
                via_parts.append(f"options: {loop_via_opts}")
            if loop_via_trans:
                via_parts.append(f"transitions: {loop_via_trans}")
            via = ", ".join(via_parts)

            behavior = node.get("self_loop_behavior")
            if behavior == "fallback":
                findings.append(Finding("INFO", "Self-loops válidos", f"'{label}': self-loop intencional ({via}) con self_loop_behavior='fallback'."))
            else:
                # Si el nodo tiene otras salidas además del self-loop, no bloquea al usuario
                other_exits = [
                    ref for ref in self._outgoing_refs(node)
                    if resolve_step(ref) != node_name and resolve_step(ref) in self.flat_nodes
                ]
                if other_exits:
                    findings.append(Finding("INFO", "Self-loops válidos", f"'{label}': self-loop detectado ({via}) pero tiene otras salidas."))
                else:
                    findings.append(Finding("WARNING", "Self-loops válidos", f"'{label}': self-loop sin self_loop_behavior y sin otras salidas. Puede atrapar al usuario."))

        return self._register("Self-loops válidos", findings)

    # ── 17. Sin caminos muertos ───────────────────────────────────────────────

    def check_dead_ends(self) -> CheckResult:
        """Nodos alcanzables sin ninguna salida propia."""
        findings: List[Finding] = []
        for node_name, node in self.flat_nodes.items():
            if node_name not in self.reachable:
                continue
            label = self._label(node_name)
            real_exits = [
                ref for ref in self._outgoing_refs(node)
                if resolve_step(ref) != node_name and resolve_step(ref) in self.flat_nodes
            ]
            is_free_text = node.get("input_mode") == "free_text"
            has_transitions = bool(self._non_null_transitions(node))

            if not real_exits:
                if is_free_text and has_transitions:
                    # Free_text con transiciones válidas que se auto-resuelven: ok
                    pass
                elif is_free_text:
                    findings.append(Finding(
                        "WARNING", "Sin caminos muertos",
                        f"'{label}': free_text sin salidas no-self. Usuario depende exclusivamente de global_commands.",
                    ))
                else:
                    findings.append(Finding(
                        "ERROR", "Sin caminos muertos",
                        f"'{label}': nodo alcanzable sin salida (sin opciones, sin transiciones, sin free_text). Camino muerto.",
                    ))

        return self._register("Sin caminos muertos", findings)

    # ── 18. Sin estados aislados ──────────────────────────────────────────────

    def check_isolated_states(self) -> CheckResult:
        """Estados que ningún nodo del flujo referencia directamente (fuera de global_commands)."""
        findings: List[Finding] = []
        state_has_inbound: Dict[str, bool] = {s: False for s in self.states}

        # Entradas desde global_commands / active_order_targets
        for ref in list(self.global_commands.values()) + list(self.active_order_targets.values()):
            if ref:
                step = resolve_step(ref)
                to_state = self.node_to_state.get(step)
                if to_state:
                    state_has_inbound[to_state] = True

        # Entradas desde nodos de otros estados
        for node_name, node in self.flat_nodes.items():
            from_state = self.node_to_state.get(node_name, "")
            for ref in self._outgoing_refs(node):
                step = resolve_step(ref)
                to_state = self.node_to_state.get(step, "")
                if to_state and to_state != from_state:
                    state_has_inbound[to_state] = True

        for state_name, has_in in state_has_inbound.items():
            if not has_in:
                findings.append(Finding(
                    "ERROR", "Sin estados aislados",
                    f"Estado '{state_name}' está aislado: nadie lo referencia (ni siquiera global_commands).",
                ))

        return self._register("Sin estados aislados", findings)

    # ── 19. Sin nodos huérfanos ───────────────────────────────────────────────

    def check_orphan_nodes(self) -> CheckResult:
        """Nodos que no aparecen en ninguna referencia del flujo (nunca son destino de nada)."""
        findings: List[Finding] = []
        referenced_steps: Set[str] = set()

        for _, ref in self.all_refs:
            referenced_steps.add(resolve_step(ref))
        for ep in self.entry_points:
            referenced_steps.add(ep)

        for node_name in sorted(self.flat_nodes.keys()):
            if node_name not in referenced_steps:
                findings.append(Finding(
                    "ERROR", "Sin nodos huérfanos",
                    f"Nodo '{self._label(node_name)}' no es destino de ninguna referencia en el flujo.",
                ))

        return self._register("Sin nodos huérfanos", findings)

    # ── 20. Sin duplicidad lógica ─────────────────────────────────────────────

    def check_duplicate_logic(self) -> CheckResult:
        """Nodos con action + options + transitions idénticos."""
        findings: List[Finding] = []
        signatures: Dict[str, List[str]] = defaultdict(list)

        for node_name, node in self.flat_nodes.items():
            action = node.get("action", "")
            options_key = json.dumps(node.get("options") or {}, sort_keys=True)
            transitions_key = json.dumps(node.get("transitions") or {}, sort_keys=True)
            sig = f"{action}|{options_key}|{transitions_key}"
            signatures[sig].append(node_name)

        for sig, names in signatures.items():
            if len(names) > 1:
                labels = ", ".join(f"'{self._label(n)}'" for n in names)
                findings.append(Finding("WARNING", "Sin duplicidad lógica", f"Nodos con lógica idéntica (action+options+transitions): {labels}"))

        return self._register("Sin duplicidad lógica", findings)

    # ─── Runner ────────────────────────────────────────────────────────────────

    def run(self) -> int:
        _checks = [
            self.check_states_defined,
            self.check_initial_valid,
            self.check_nodes_reachable,
            self.check_states_reachable,
            self.check_refs_valid,
            self.check_options_valid,
            self.check_transitions_valid,
            self.check_global_commands_valid,
            self.check_active_order_targets,
            self.check_coverage,
            self.check_simulation,
            self.check_complete_paths,
            self.check_terminal_nodes,
            self.check_terminal_states,
            self.check_cycles,
            self.check_self_loops,
            self.check_dead_ends,
            self.check_isolated_states,
            self.check_orphan_nodes,
            self.check_duplicate_logic,
        ]

        for fn in _checks:
            fn()

        return self._report()

    def _report(self) -> int:
        W = 62
        SEP = "=" * W
        DIV = "-" * W

        def out(line: str = "") -> None:
            # Encode to stdout safely; replace unmappable chars on narrow terminals.
            sys.stdout.buffer.write((line + "\n").encode(sys.stdout.encoding or "utf-8", errors="replace"))

        out()
        out(SEP)
        out("AUDITORIA DEL FLUJO")
        out(f"Archivo: {self.flow_path.name}")
        out(SEP)
        out()

        all_errors: List[str] = []
        all_warnings: List[str] = []
        all_infos: List[str] = []

        for result in self.results:
            tag = "PASS" if result.passed else "FAIL"
            out(f"[{tag}] {result.name}")
            for f in result.findings:
                if f.level == "ERROR":
                    all_errors.append(f.message)
                elif f.level == "WARNING":
                    all_warnings.append(f.message)
                else:
                    all_infos.append(f.message)

        # Estadísticas
        s = self._coverage_stats
        if s:
            out()
            out(DIV)
            out("ESTADISTICAS")
            out(DIV)
            out(f"  Estados:              {s['estados']}")
            out(f"  Nodos:                {s['nodos']}")
            out(f"  Referencias totales:  {s['referencias']}  (validas: {s['referencias_validas']})")
            out(f"  Transitions:          {s['transitions']}")
            out(f"  Options:              {s['options']}")
            out()
            out(f"  Estados alcanzables:  {s['estados_alcanzables']}/{s['estados']}  ({s['estados_pct']:.0f}%)")
            out(f"  Nodos alcanzables:    {s['nodos_alcanzables']}/{s['nodos']}  ({s['nodos_pct']:.0f}%)")
            out(f"  Cobertura del flujo:  {s['cobertura']:.0f}%")

        if all_warnings:
            out()
            out(DIV)
            out("WARNINGS:")
            for w in all_warnings:
                out(f"  - {w}")

        if all_infos:
            out()
            out(DIV)
            out("INFOS:")
            for i in all_infos:
                out(f"  - {i}")

        if all_errors:
            out()
            out(DIV)
            out("ERRORES:")
            for e in all_errors:
                out(f"  [X] {e}")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        out()
        out(SEP)
        out("RESULTADO FINAL")
        out(SEP)
        if not all_errors:
            out()
            out("[OK] Auditoria completada correctamente.")
            out()
        else:
            out()
            out(f"[FAIL] Auditoria fallida -- {len(all_errors)} error(s) encontrado(s).")
            out()

        coverage = s.get("cobertura", 0.0) if s else 0.0
        out(f"Cobertura:          {coverage:.0f}%")
        out(f"Pruebas ejecutadas: {total}")
        out(f"Pruebas superadas:  {passed}")
        if failed:
            out(f"Pruebas fallidas:   {failed}")
        out(f"Warnings:           {len(all_warnings)}")
        out(f"Errores:            {len(all_errors)}")
        out()

        return 1 if all_errors else 0


# ─── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    flow_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FLOW
    if not flow_path.exists():
        print(f"ERROR: Archivo de flujo no encontrado: {flow_path}")
        sys.exit(1)
    try:
        auditor = FlowAuditor(flow_path)
        sys.exit(auditor.run())
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON inválido en {flow_path}: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        raise


if __name__ == "__main__":
    main()
