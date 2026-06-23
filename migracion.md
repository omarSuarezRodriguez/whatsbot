# Migración FlowEngine → MAPA (JSON) + MOTOR (Python)

Guía por fases para refactor estructural. Cada fase = chat(s) independiente(s).  
**Idea intacta:** `flows/restaurant_flow.json` = mapa (mensajes, transitions, options, meta); `flow_engine.py` = motor (leer nodo → action → outcome → transition → estado → un `str`).  
**No tocar** `StateManager`, servicios (`OrderService`, `MenuService`, etc.) ni formato `states` del JSON.

---

## Estado implementado (runtime actual)

### Checklist general de ejecución

| Fase | Estado |
|------|--------|
| 1 | DONE |
| 2 | DONE |
| Parche intermedio | DONE (fuera de fases) |
| 3A | PENDING |
| 3B | PENDING |
| 3C | PENDING |
| 4 | PENDING |

| Fase / bloque | Estado | Resumen verificado en código |
|---------------|--------|------------------------------|
| **Fase 1** — Motor puro | ✅ **DONE** | `process_message` siempre `str`; composición genérica en `_process_node`; menú solo vía `_action_show_menu`; `hola` en idle = bienvenida + CTA JSON sin catálogo |
| **Fase 2** — UX estática al JSON | ✅ **DONE** | `_resolve_ux_text` solo para claves meta explícitas; fallback genérico vía `node.fallback` (L402); `meta` no participa en fallback genérico; `validate_flow.py` 0 errores; 9/9 tests |
| **Parche intermedio crítico** — idle.start estable | ✅ **DONE (fuera de fases)** | `start_seen` transitorio en runtime; B1/B2/B3 hardcode en Python; `meta.start_fallback` en JSON y usado correctamente; **no** es Fase 2 ni Fase 3 |
| **Fase 3A** — Eliminación hardrouting | ❌ **PENDING** | Steps hardcode (`start`, `menu_node`, `order_start`, `order_modify`) en routing |
| **Fase 3B** — Declaratizar idle.start | ❌ **PENDING** | Eliminar `start_seen` + ramas B1/B2/B3; reemplazar por flags JSON |
| **Fase 3C** — Limpieza final motor | ❌ **PENDING** | `_process_message_body` mínimo; 0 lógica de flujo por step |
| **Fase 4** — Cierre y docs | ❌ **PENDING** | `validate_flow.py` ampliado; tutorial con sección arquitectura motor |

**Tests:** `pytest tests/test_flow_transitions.py -q` → **9 passed** (verificado).

### Parche intermedio crítico (fuera de fases)

Parche aplicado directo en `flow_engine.py`. **No pertenece a Fase 2 ni a Fase 3.** Objetivo: `idle.start` estable sin re-bienvenida en self-loop ni en input no reconocido.

**Estado real de componentes:**

| Componente | Estado real |
|------------|-------------|
| `start_seen` | activo en runtime (estado transitorio en `data`; `reset()` lo borra) |
| B1/B2/B3 routing | hardcode en Python (L336–340, L399–400, L349–351) |
| `start_fallback` | JSON `meta` (L18); usado vía `_resolve_ux_text("start_fallback", node)` |
| objetivo | eliminar en Fase 3 |

**Componentes en código:**

| Símbolo | Ubicación | Rol |
|---------|-----------|-----|
| `meta.start_fallback` | JSON L18 | Texto fallback B1/B2 (sin `NAV_HINT`); leído vía `_resolve_ux_text("start_fallback", node)` |
| `start_seen` en `data` | `_process_node` L472–473 | `True` tras primer render exitoso de `start`; estado transitorio real; `reset()` borra `data` |
| Ramas B1/B2/B3 | `_process_message_body` | Routing hardcode en Python; **no** declarativizado aún |
| `_action_welcome_customer` | L504–505 | No-op (`"", None`); no lee `last_order_items` |
| `welcome_customer` | JSON + `_actions` | Permanece por compatibilidad; sin lógica de repetición |

**Texto exacto (`meta.start_fallback` en JSON):**

> Disculpa, no logré entenderte. ¿Podrías intentarlo de nuevo? También puedes escribir menu, pedido o reservar.

**Comportamiento crítico `idle.start` (runtime verificado):**

| Rama | Condición (código) | Efecto |
|------|-------------------|--------|
| **B1** | `current_step=="start"` + `start_seen=True` + input no enrutado antes (L399–400) | Fallback directo; **no** `_process_node`; step sin cambio; **sin** `NAV_HINT` |
| **B2** | `options[normalized]` self-loop (`hola`/`buenas`/`hey` → `start`) + `start_seen=True` (L336–340) | Mismo fallback; **no** re-ejecuta nodo → **no** re-bienvenida |
| **B3** | `is_greeting` + `flow=="idle"` + `current_step!="start"` (L349–351) | Navega a `idle.start` con bienvenida (ej. saludo desde `menu_node`) |

**1er `hola` en `start`:** `_process_node(start)` → bienvenida + CTA JSON (`dual_message`).  
**2º `hola` / `no` / `ok` en `start`:** B1 o B2 → fallback, no catálogo, no re-bienvenida.  
**`menu` / `pedido` / `reservar` en `start`:** routing normal vía `options` o `global_commands`.

Tests de regresión existentes: `test_idle_start_ignores_last_order_items`, `test_idle_start_no_menu_catalog`, `test_idle_start_returns_single_string`.  
**Pendiente:** `test_idle_start_second_hola_fallback` (2º hola → B1/B2) — documentado en Fase 4, aún no implementado.

---

## Decisiones removidas del sistema

### Decisión irreversible del sistema — repeat-order

**Repeat-order eliminado completamente del sistema.**

- No forma parte de ninguna fase futura (1, 2, 3A, 3B, 3C ni 4).
- No debe reintroducirse en prompts, código ni JSON.
- `last_order_items` en perfil **no** dispara prompt de repetición.

Antes existía flujo “¿repetir tu pedido anterior?” (`_handle_repeat_order`, `awaiting_repeat_order`, `skip_repeat_order_once`, claves `repeat_order_*`). Borrado en el parche intermedio idle.start. Motivo: re-bienvenida / UX inconsistente. Hoy: `welcome_customer` = no-op.

---

## Estado actual vs objetivo

| Capa | Hoy (runtime real) | Objetivo |
|------|-------------------|----------|
| `flows/restaurant_flow.json` | Nodos, transitions, options, mensajes; `meta` con UX estática (abandon, greeting, cancel, welcome, start_fallback); `fallback` por nodo (Fase 2 ✅) | Igual + flags declarativos de routing (Fase 3A–3B) |
| `flow_engine.py` | Motor + routing con steps hardcode + parche `start_seen`; UX abandon/greeting/cancel en JSON (Fase 2 ✅); fallback genérico vía `node.fallback` | Solo: input → intent → action → transition → compose → **un** `str` |
| `StateManager` | `flow`, `step`, `data` (incl. `start_seen`, `awaiting_abandon_confirm` transitorios) | Sin cambios de contrato |
| `gateway.py` | Acepta `str \| list[str]` | Sigue funcionando; motor solo devuelve `str` |
| `parser.py` | `infer_user_intent` | Sin cambios de negocio |
| `scripts/validate_flow.py` | Valida refs, transitions, outcomes de acciones | Ampliar en Fase 4 (claves meta Fase 2 + campos Fase 3B) |

### Deuda conocida en `flow_engine.py`

| Problema | Ubicación (método / símbolo) | Estado | Qué hacer |
|----------|------------------------------|--------|-----------|
| `Reply = Union[str, List[str]]` / `_as_reply` | — | ✅ Resuelto (Fase 1) | — |
| Menú inyectado en `start` desde Python | — | ✅ Resuelto (Fase 1) | `format_menu` solo en `_action_show_menu` |
| Repeat-order | — | ✅ Eliminado (parche) | No reintroducir |
| UX abandonar pedido | `_handle_abandon_confirm`; `_resolve_global_command` `inicio`+carrito | ✅ Fase 2 | `meta.abandon_confirm_*` vía `_resolve_ux_text` |
| Greeting durante pedido — texto | `_resolve_ux_text("order_greeting_while_ordering")` | ✅ Fase 2 | Texto en meta; sin hardcode UX |
| Greeting durante pedido — routing | `_process_message_body` L388–390 | ❌ Fase 3A | Quitar step filter; flag JSON en nodo |
| `pedido_implicito` con steps fijos | `_process_message_body` L375–386 | ❌ Fase 3A | `intercept_products` en nodos idle; lógica intermedia, no step filter |
| Salto hardcode `idle.start` en greeting idle | `_process_message_body` L352–354 | ❌ Fase 3A | `options` JSON + helper `_goto_ref` |
| Parche `start_seen` + ramas B1/B2/B3 | L336–340, L399–400, L472–473 | ❌ **Fase 3B** | `node.self_loop_behavior`, `node.fallback`, `node.suppress_repeat_message` |
| `step == "start"` para `start_seen` | `_process_node` L472 | ❌ **Fase 3B** | Sin nombre de step hardcode en Python |
| `_process_message_body` con lógica de flujo | varios bloques | ❌ **Fase 3C** | Pipeline mínimo: intent → action → transition |
| Mensajes estáticos en `_action_*` | varios `_action_*` | ❌ Fase 3C–4 | Estáticos → JSON; dinámicos (carrito, totales, errores con datos) quedan en action |
| `cancel_message` | `_resolve_global_command` | ✅ Fase 2 | Lee `meta.cancel_message` vía `_resolve_ux_text` |

### Pipeline del motor

**Pipeline actual** (Fase 1 ✅ + Fase 2 ✅ + parche intermedio ✅):

```
process_message(text) → str
  → _handle_abandon_confirm          # solo meta + is_confirmation/is_rejection (Fase 2)
  → action_on_input (si aplica)
  → global_commands                  # inicio+carrito: meta.abandon_confirm_prompt (Fase 2)
  → options[normalized]              # B2: self-loop start + start_seen → meta.start_fallback
  → greeting idle → _parse_ref idle.start   # B3: skip si ya en start
  → intent (parser) + pedido_implicito      # current_step in {start, menu_node} hardcode
  → free_text action
  → greeting order_start/order_modify       # meta.order_greeting_while_ordering (Fase 2)
  → B1: start + start_seen → meta.start_fallback
  → fallback del nodo
  → compose en _process_node: message + action + message_after_action + message_secondary
  → start_seen=True si step==start y response (parche)
  → append NAV_HINT si meta lo permite
```

**Pipeline objetivo** (post Fase 3A–3C + Fase 4):

```
process_message(text) → str
  → handlers meta (abandon)          # solo leen JSON + StateManager
  → options[normalized]              # self-loop / fallback desde JSON (Fase 3B)
  → global_commands                  # refs + reglas mínimas de estado
  → intent (parser)                  # intercept_products por nodo, sin steps hardcode (Fase 3A)
  → action_on_input / free_text        # outcome → transitions JSON
  → fallback del nodo                  # node.fallback; meta no participa
  → compose: message + action_msg + message_after_action + message_secondary
  → append NAV_HINT si meta lo permite
  → return str
```

---

## Arquitectura real (post Fase 2)

Estado verificado del sistema tras Fase 1 + Fase 2 + parche intermedio:

| Capa | Responsabilidad | Prohibido |
|------|-----------------|-----------|
| **JSON** (`restaurant_flow.json`) | Flujo: nodos, `transitions`, `options`, `meta` (UX estática), `node.fallback` | Lógica de ejecución |
| **Python** (`flow_engine.py`) | Ejecución: leer nodo → intent → action → outcome → transition → compose → `str` | Lógica de flujo por nombre de step |
| **Estado** (`StateManager`) | Solo contexto: `flow`, `step`, `data` (flags transitorios como `start_seen`, `awaiting_abandon_confirm`) | Decisiones de routing de negocio |

**Separación de fallback (sin ambigüedad):**

- Fallback genérico de nodo → `node.fallback` exclusivamente (L402).
- `meta` → solo claves explícitas vía `_resolve_ux_text` (abandon, greeting, cancel, welcome, `start_fallback` en B1/B2 del parche).
- `meta` **no** participa en el path de fallback genérico.

**Deuda explícita (Fase 3A–3C):** routing por step name, `start_seen`, B1/B2/B3, `pedido_implicito` con step filter — todo hardcode Python pendiente de declarativización.

### Capas que intervienen (no romper)

```
gateway.handle_incoming_message
  └─ business_scope
  └─ FlowEngine.process_message
       ├─ StateManager (step/flow/data)
       ├─ restaurant_flow.json (nodos, transitions, options, meta)
       ├─ _actions → services (menu, order, reservation, user, admin)
       ├─ parser.infer_user_intent
       └─ validators (is_confirmation, parse_date, …)
```

---

## Fase 1 — Motor puro: output único y composición genérica

**Estado:** ✅ **IMPLEMENTADA**

**Meta:** `FlowEngine` compone mensajes igual para todos los nodos. Cero ramas `step == "…"` para menú. Cero `List[str]` en retornos.

**Verificado:** `Reply` / `_as_reply` ausentes; `format_menu` solo en `_action_show_menu`; tests `test_idle_start_no_menu_catalog`, `test_idle_start_returns_single_string`, `test_menu_shows_catalog`.

### Prompt 1A (referencia histórica — ya aplicado)

> **Nota:** Fase 1 cerrada. Usar solo como referencia si hay regresión.

```
Ejecuta ÚNICAMENTE Fase 1 de @migracion.md (Motor puro).

ARCHIVOS:
- chatbot/app/core/flow_engine.py
- tests/test_flow_transitions.py (añadir/ajustar si hace falta)

IMPLEMENTAR:

1. Eliminar tipo Reply / List[str] en flow_engine.py:
   - process_message y métodos internos retornan siempre str.
   - _join_reply puede quedarse como helper interno; no exportar listas.

2. Eliminar _as_reply() o reducirla a composición declarativa SIN:
   - if step == "start"
   - menu_service.format_menu() fuera de _action_show_menu
   - ramas por nombre de nodo

3. Pipeline único en _process_node (orden fijo):
   - message (render templates)
   - resultado de action (si hay y no es input pendiente)
   - message_after_action
   - message_secondary (solo si node.dual_message es true; cualquier nodo, no solo start)
   Unir con "\n\n". Un solo str final.

4. idle.start:
   - NO inyectar menú desde Python.
   - Salida = welcome_line + message_secondary del JSON (como está en restaurant_flow.json).
   - dual_message sigue siendo flag JSON, no lógica especial por step.

RESTRICCIONES:
- No cambiar StateManager ni services.
- No cambiar restaurant_flow.json en esta fase.
- No mover textos de abandon aún (Fase 2).

COMPROBACIÓN DE CIERRE (tabla PASS/FAIL):
- pytest tests/test_flow_transitions.py -q
- python -c "from chatbot.runtime import get_bot_context; e=get_bot_context(start_background=False).flow_engine; r=e.process_message('573009998877','hola'); assert isinstance(r,str); assert 'Bienvenido' in r or 'bienvenido' in r.lower()"
- rg 'step == "start"|List\[str\]|Reply = Union' chatbot/app/core/flow_engine.py  → 0 matches (salvo parche start_seen posterior)
- rg 'format_menu' chatbot/app/core/flow_engine.py  → solo en _action_show_menu
- Confirmar: hola NO incluye bloque de menú completo (solo bienvenida + CTA JSON); menu sí muestra menú vía show_menu

NO empezar Fase 2.
```

### Comprobación manual Fase 1

| Prueba | Esperado | Estado |
|--------|----------|--------|
| `hola` | Un string: bienvenida + opciones menu/pedido/reservar (sin catálogo de productos) | ✅ |
| `menu` | Menú formateado + message_after_action del nodo | ✅ |
| `pedido` → productos → flujo completo | Sin regresión en tests existentes | ✅ |

---

## Fase 2 — UX estática al JSON (meta)

**Estado:** ✅ **COMPLETA** (contractual fixes aplicados) — cero string UX visible en `flow_engine.py` (salvo `_action_*` dinámicos y `NAV_HINT`); fallback por nodo en JSON; L402 usa `node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK)`; `validate_flow.py` 0 errores; 9/9 tests.

**Meta:** Motor cero copy estático de usuario. Todo texto UX viene del JSON (`meta` o `node.fallback`). Python solo decide **qué clave leer** y **cuándo**; nunca redacta mensajes de negocio.

### Rol de `meta` (definición canónica)

`meta` en `restaurant_flow.json`:

- **SOLO** textos UX estáticos (abandon, greeting, cancel, welcome, start_fallback, address)
- **NO** routing — las transiciones van en `transitions`/`options`
- **NO** fallback genérico — el fallback por nodo va en `node.fallback`
- **NO** lógica de flujo — ninguna clave de meta controla qué nodo sigue

### Definición canónica de fallback

Única forma válida en `flow_engine.py` (L402):

```python
fallback = node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK)
return self._append_navigation(fallback, node)
```

- `node.fallback` = fuente **exclusiva** del fallback genérico por nodo (definido en JSON por nodo)
- `_SYSTEM_TECHNICAL_FALLBACK` = solo si el nodo no tiene `fallback` (error de configuración)
- `meta` **no participa** en el path de fallback genérico (L402)
- `_resolve_ux_text` aplica **solo** a claves meta explícitas nombradas en el código (abandon, greeting, cancel, welcome, `start_fallback`, address)
- Excepción temporal del parche: B1/B2 usan `meta.start_fallback` vía `_resolve_ux_text` — routing Python, deuda Fase 3B (no es fallback genérico de nodo)

### Reglas de resolución de UX (obligatorias)

**Origen del texto** — orden de prioridad único, sin excepciones:

| Prioridad | Fuente | Cuándo |
|-----------|--------|--------|
| 1 | `flow.meta[<clave>]` | Clave explícita para el caso (abandon, greeting order, cancel, etc.) |
| 2 | `node.fallback` | Clave meta ausente o vacía en el nodo actual |
| 3 | `_SYSTEM_TECHNICAL_FALLBACK` | Solo error técnico de configuración; **prohibido** como UX de negocio |

**Implementación:** helper `_resolve_ux_text(meta_key, node)` en `flow_engine.py`. Un solo punto de resolución para claves meta **explícitas**; prohibido usarlo como proxy de fallback genérico. Prohibido `self.meta.get(key, "texto…")` con default UX en Python.

**Qué NO es UX estática (queda en `_action_*`):** mensajes con datos dinámicos (carrito, totales, dirección, resumen reserva, errores de validación con contexto). Esos strings son salida de acción, no meta.

**Qué SÍ es UX estática (debe estar en JSON):**

| Caso | Clave `meta` | Lógica Python permitida |
|------|--------------|-------------------------|
| `inicio` con carrito activo | `abandon_confirm_prompt` | `patch_data(awaiting_abandon_confirm=True)` + `_resolve_ux_text` |
| Respuesta inválida en abandon | `abandon_confirm_invalid` | `is_confirmation` / `is_rejection` → elegir clave |
| Rechazo abandon (seguir pedido) | `abandon_confirm_continue` | idem |
| Saludo en `order_start` / `order_modify` | `order_greeting_while_ordering` | `is_greeting` + step in set → `_resolve_ux_text` |
| `cancelar` | `cancel_message` | reset + compose con start |

### Reemplazo obligatorio del hardcode existente

Al cerrar Fase 2, **eliminar** de `flow_engine.py` (no dejar híbrido):

| String / patrón hardcode (antes) | Destino JSON | Handler |
|----------------------------------|--------------|---------|
| `"Tienes un pedido en curso…"` | `meta.abandon_confirm_prompt` | `_resolve_global_command("inicio")` |
| `"Perfecto, continuamos…"` | `meta.abandon_confirm_continue` | `_handle_abandon_confirm` (rama `is_rejection`) |
| `"Responde *sí* para volver…"` | `meta.abandon_confirm_invalid` | `_handle_abandon_confirm` (rama default) |
| `"¡Hola! Cuando quieras, cuéntame…"` | `meta.order_greeting_while_ordering` | `_process_message_body` greeting order |
| Default UX en `cancel_message` | `meta.cancel_message` (ya existe) | `_resolve_global_command("cancelar")` |
| Default UX en `node.fallback` | `node.fallback` en JSON por nodo | fallback genérico del nodo |

**`_handle_abandon_confirm` — contrato estricto:**

- ✅ Leer `meta` vía `_resolve_ux_text`
- ✅ Evaluar `is_confirmation` / `is_rejection`
- ✅ Decidir qué clave meta usar (`abandon_confirm_continue` vs `abandon_confirm_invalid`)
- ✅ Transiciones de estado (`reset`, `patch_data`)
- ❌ Cero strings UX literales en Python
- ❌ Cero lógica de lenguaje natural propia
- ❌ Cero fallback interno de mensaje

**`_resolve_global_command("inicio")` con carrito:**

- Si `_has_active_order` → devolver `_resolve_ux_text("abandon_confirm_prompt", current_node)`
- Si meta vacía → `current_node.fallback` → `_SYSTEM_TECHNICAL_FALLBACK`
- Prohibido string directo en Python

**Greeting `order_start` / `order_modify`:**

- Obligatorio: `_resolve_ux_text("order_greeting_while_ordering", node)`
- Si meta vacía → `node.fallback`
- Prohibido hardcode en Python

### Claves `meta` requeridas (`restaurant_flow.json`)

```json
"abandon_confirm_prompt": "...",
"abandon_confirm_continue": "...",
"abandon_confirm_invalid": "...",
"order_greeting_while_ordering": "...",
"welcome_with_name": "...",
"welcome_without_name": "...",
"cancel_message": "..."
```

Validadas por `scripts/validate_flow.py` (`PHASE2_META_KEYS`).

### Fuera de alcance Fase 2 (Fase 3A–3B)

- Routing `start_seen` + ramas B1–B3 en Python (texto `meta.start_fallback` ya en JSON — Fase 2 ✅)
- `pedido_implicito` con step filter, greeting idle → `idle.start` (Fase 3A)
- Declaratización idle.start (Fase 3B)
- Mensajes dinámicos en `_action_*` (Fase 3C–4)

### Prompt 2A (referencia — ya aplicado)

```
Ejecuta ÚNICAMENTE Fase 2 de @migracion.md (UX en JSON).

CONTEXTO: Fase 1 hecha. Parche crítico idle.start aplicado. repeat-order NO existe.

OBJETIVO: Fase 2 100% determinista — cero string UX visible en flow_engine.py
(salvo _action_* dinámicos, NAV_HINT, routing start_seen/B1-B2 del parche intermedio — Fase 3B).

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py

IMPLEMENTAR:

1. meta en restaurant_flow.json (textos que hoy están hardcode):
   - abandon_confirm_prompt
   - abandon_confirm_invalid
   - abandon_confirm_continue
   - order_greeting_while_ordering
   Mantener cancel_message.

2. flow_engine.py:
   - Añadir _resolve_ux_text(meta_key, node): meta → node.fallback → _SYSTEM_TECHNICAL_FALLBACK
   - _handle_abandon_confirm: SOLO meta + is_confirmation/is_rejection + estado
   - _resolve_global_command "inicio"+carrito: _resolve_ux_text("abandon_confirm_prompt", current_node)
   - greeting order_start/order_modify: _resolve_ux_text("order_greeting_while_ordering", node)
   - cancelar: _resolve_ux_text("cancel_message", …) sin default UX en Python
   - fallback nodo: node.fallback o _SYSTEM_TECHNICAL_FALLBACK (sin default UX en Python)

3. validate_flow.py: PHASE2_META_KEYS obligatorias.

RESTRICCIONES:
- No nuevas fases ni arquitectura paralela de fallback
- No lógica híbrida (parte meta + parte Python)
- No cambiar transitions/outcomes/services/StateManager

COMPROBACIÓN DE CIERRE (Fase 2 completa ⇔ todo PASS):
- python scripts/validate_flow.py
- pytest tests/test_flow_transitions.py -q
- rg 'Tienes un pedido|Cuando quieras|Bienvenido|cuéntame' chatbot/app/core/flow_engine.py → 0 matches
- rg 'Perfecto, continuamos|Responde \*sí\* para volver' chatbot/app/core/flow_engine.py → 0 matches
- Manual: pedido a medias → inicio → meta.abandon_confirm_prompt; hola en order_start → meta.order_greeting_while_ordering
```

### Prompt 2B (referencia — ya aplicado)

```
Continúo Fase 2 @migracion.md. Busca strings UX restantes en flow_engine.py
(fuera de _action_* dinámicos, NAV_HINT, routing start_seen/B1-B2).
Muévelos a meta o node.fallback. Tabla strings movidos. Misma comprobación de cierre.
```

### Comprobación manual Fase 2

| Prueba | Esperado | Estado |
|--------|----------|--------|
| Pedido iniciado → `inicio` | `meta.abandon_confirm_prompt` (vía `_resolve_ux_text`) | ✅ |
| `inicio` + carrito → `sí` | Reset + bienvenida `idle.start` | ✅ |
| `inicio` + carrito → `no` | `meta.abandon_confirm_continue` | ✅ |
| Input inválido en abandon | `meta.abandon_confirm_invalid` | ✅ |
| `hola` con `last_order_items` | Bienvenida normal, sin “repetir” | ✅ |
| `hola` durante `order_start` | `meta.order_greeting_while_ordering` | ✅ |
| `cancelar` mid-order | `meta.cancel_message` + start | ✅ |
| Input basura en `menu_node` | `node.fallback` del nodo (no `"Error interno..."`) | ✅ |

---

### Fase 2 — Fixes contractuales (APLICADOS Y VERIFICADOS)

> Referencia histórica. Todos los ítems aplicados. Usar solo si hay regresión.

#### Regla única de fallback

- `node.fallback` es la **única** fuente oficial de fallback por nodo.
- `meta.fallback` **no existe** y nunca se usa como fallback genérico.
- Prohibido: `self.meta.get("fallback", "texto…")` o cualquier default de string UX en Python para el path de fallback.

#### Regla de cobertura de nodos

Todo nodo del JSON **debe** definir `fallback`, **excepto** nodos action-only determinísticos (nodos que siempre transicionan vía `outcome` y nunca pueden recibir input no enrutado — e.g. `order_saved`, `reservation_saved`).

Nodos que requieren `fallback` obligatorio:

| Nodo | Motivo |
|------|--------|
| `start` | Recibe input libre (cubierto por `meta.start_fallback` vía `_resolve_ux_text`) |
| `menu_node` | Sin `input_mode: free_text`; input no reconocido llega a L402 |
| `order_start` | `free_text` pero puede recibir input sin productos |
| `order_review` | Input no confirmación/rechazo llega a fallback |
| `order_modify` | Igual que `order_start` |
| `order_delivery` | Input no reconocido por `parse_delivery_type` |
| `order_address` | Input vacío o inválido |
| `order_customer_name` | Input < 2 chars llega al action, no al fallback; definir por cobertura |
| `reservation_start` | Input inválido para `parse_persons` |
| `reservation_date` | Input inválido para `parse_date` |
| `reservation_time` | Input inválido para `parse_time` |
| `reservation_review` | Input no confirmación/rechazo |

#### Contrato de implementación en `flow_engine.py`

Única forma válida de resolver fallback genérico (actualmente L402):

```python
fallback = node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK)
return self._append_navigation(fallback, node)
```

**Prohibido** en el path de fallback genérico:
- `self._resolve_ux_text("fallback", node)` con clave `"fallback"` inexistente en meta.
- Cualquier string UX literal en Python como default.

> **Nota:** `_resolve_ux_text` sigue siendo el mecanismo correcto para claves meta explícitas (abandon, greeting, cancel, welcome, address). El fallback genérico de nodo es la excepción: su fuente es `node.fallback`, no meta.

#### Validación — ampliar `PHASE2_META_KEYS`

En `scripts/validate_flow.py`, `PHASE2_META_KEYS` debe incluir:

```python
PHASE2_META_KEYS = (
    "cancel_message",
    "abandon_confirm_prompt",
    "abandon_confirm_continue",
    "abandon_confirm_invalid",
    "order_greeting_while_ordering",
    "welcome_with_name",
    "welcome_without_name",
    "start_fallback",        # añadir
    "address_prompt",        # añadir
    "address_prompt_saved",  # añadir
)
```

Opcional (warning, no error): nodo sin `input_mode: free_text` y sin `fallback` definido.

> **Separación Fase 2 / Fase 3B:** El **texto** de `start_fallback` ya está en `meta.start_fallback` (JSON, Fase 2 ✅). Lo que queda para **Fase 3B** es eliminar el **routing** (`start_seen`, ramas B1/B2/B3, `step == "start"` hardcode). No es deuda de Fase 2.

#### Comprobación de cierre contractual

```bash
python scripts/validate_flow.py          # 0 errores, incluye claves nuevas
pytest tests/test_flow_transitions.py -q # sin regresiones
```

Manual obligatorio:

| Prueba | Esperado |
|--------|----------|
| Input basura en `menu_node` | Texto de `node.fallback` del nodo, no `"Error interno..."` |
| Input basura en `order_review` | Texto de `node.fallback` del nodo |
| Input basura en `reservation_time` | Texto de `node.fallback` del nodo |

### Prompt 2C — Fixes contractuales de cierre (referencia — ya aplicado)

> **Nota:** Fase 2 contractual cerrada. Usar solo como referencia si hay regresión.

```
Ejecuta ÚNICAMENTE los fixes contractuales de cierre de Fase 2 descritos en @migracion.md
(sección "Fase 2 — Fixes contractuales").

CONTEXTO: Fase 1 ✅. Fase 2 core ✅ (abandon/cancel/greeting en meta). Parche idle.start ✅.
Aplicado: fallback por nodo en JSON, fix L402 → node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK), validador ampliado.

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py

IMPLEMENTAR:

1. flow_engine.py — fix L402 (fallback genérico):
   Reemplazar:
     fallback = self._resolve_ux_text("fallback", node)
   Por:
     fallback = node.get("fallback", _SYSTEM_TECHNICAL_FALLBACK)
   No tocar ningún otro uso de _resolve_ux_text.

2. restaurant_flow.json — añadir "fallback" a cada nodo de la tabla:
   - start: NO añadir (su fallback viene de meta.start_fallback vía _resolve_ux_text en B1/B2)
   - menu_node: "No entendí eso. Escribe *menu*, *pedido* o *reservar*."
   - order_start: "No logré identificar productos. Describe tu pedido, ej: *2 pizzas y 1 agua*."
   - order_review: "Responde *sí* para confirmar o *no* para modificar tu pedido."
   - order_modify: "No logré identificar productos. Dime qué quieres agregar, quitar o cambiar."
   - order_delivery: "Responde *1* o *domicilio*, o *2* o *recoger*."
   - order_address: "Necesito una dirección válida. Escríbela o responde *sí* para usar la guardada."
   - order_customer_name: "Escribe tu nombre (mínimo 2 caracteres)."
   - reservation_start: "Indícame un número válido de personas (entre 1 y 30)."
   - reservation_date: "Usa el formato *DD/MM/AAAA*, con una fecha igual o posterior a hoy."
   - reservation_time: "Prueba con *19:30* o *7:30 pm*."
   - reservation_review: "Responde *sí* para confirmar la reserva o *no* para modificarla."
   Textos ajustables siempre que sean UX consistente con el flujo.

3. scripts/validate_flow.py — ampliar PHASE2_META_KEYS:
   Añadir al tuple existente: "start_fallback", "address_prompt", "address_prompt_saved"

RESTRICCIONES:
- No tocar StateManager ni services.
- No tocar lógica de Fase 3A–3B (start_seen, ramas B1/B2, routing por step, pedido_implicito).
- No cambiar transitions, outcomes ni options existentes.
- No nuevas dependencias.

COMPROBACIÓN DE CIERRE (todo PASS antes de terminar):
- python scripts/validate_flow.py → 0 errores
- pytest tests/test_flow_transitions.py -q → sin regresiones
- rg '_resolve_ux_text\("fallback"' chatbot/app/core/flow_engine.py → 0 matches
- Manual: input basura en menu_node → node.fallback, no "Error interno..."
```

---

## Fase 3A — Eliminación de hardrouting (core decoupling)

**Estado:** ❌ **PENDING**

**Objetivo:** Eliminar toda dependencia de steps hardcode en Python para routing.

**Cambios:**

- Quitar:
  - `current_step == "start"`
  - `current_step == "menu_node"`
  - `current_step == "order_start"`
  - `current_step == "order_modify"`
- El routing debe depender **solo** de:
  - `node.options`
  - `node.transitions`
  - intent parser
- `pedido_implicito` sigue existiendo pero como lógica intermedia (ej. `intercept_products` en JSON), **no** como step filter.

**Sigue en Python hoy:** steps hardcode L340, L352, L378, L388, L399; greeting order ya resuelve texto vía meta (Fase 2 ✅).

### Prompt 3A (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 3A de @migracion.md (eliminación hardrouting).

CONTEXTO: Fase 1 ✅. Fase 2 ✅. Parche intermedio idle.start ✅ (start_seen + B1/B2/B3 — NO tocar en esta fase).

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- tests/test_flow_transitions.py

IMPLEMENTAR:

1. pedido_implicito sin step filter
   - Quitar current_step in {"start", "menu_node"}
   - Campo JSON en nodo idle (ej. intercept_products: true) en start y menu_node
   - Motor: si nodo tiene intercept_products y intent tiene productos → pedido

2. Greeting en order sin step hardcode
   - Quitar current_step in {"order_start", "order_modify"}
   - Campo JSON (ej. order_greeting_on_greeting: true) en nodos order
   - Texto ya en meta.order_greeting_while_ordering (Fase 2 ✅)

3. Greeting idle sin hardcode de step
   - Quitar condición current_step != "start" y _parse_ref suelto
   - Usar options JSON + helper _goto_ref(wa_id, ref) si reduce duplicación

RESTRICCIONES:
- NO tocar start_seen, B1/B2/B3 (Fase 3B)
- NO tocar StateManager ni services
- NO cambiar transitions/outcomes semántica

TEST DE CIERRE:
- rg '"start"|"menu_node"|"order_start"|"order_modify"' chatbot/app/core/flow_engine.py → 0 en _process_message_body (routing)
- pytest tests/test_flow_transitions.py -q
- menu/start/order siguen funcionando sin lógica por step name
```

### Comprobación manual Fase 3A

| Prueba | Esperado |
|--------|----------|
| `2 pizza hawaiana` sin decir pedido (desde idle) | Entra flujo order |
| `hola` en `order_modify` | Mensaje meta, no salto raro |
| `hola` desde `menu_node` | Navega a start con bienvenida (B3 intacto hasta 3B) |

---

## Fase 3B — Declaratizar idle.start (start_seen removal)

**Estado:** ❌ **PENDING**

**Objetivo:** Eliminar completamente el parche `start_seen` y ramas B1/B2/B3.

**Cambios:**

- Eliminar:
  - `start_seen` (flag en `data`)
  - ramas B1/B2/B3 en `_process_message_body`
  - `step == "start"` en `_process_node` para setear `start_seen`
- Reemplazar por lógica declarativa en JSON:
  - `node.self_loop_behavior`
  - `node.fallback`
  - `node.suppress_repeat_message`

**Comportamiento a preservar:**

| Input repetido | Resultado |
|----------------|-----------|
| hola (1º) | bienvenida |
| hola (2º) | fallback JSON (sin re-bienvenida) |
| no/ok | fallback JSON |

### Prompt 3B (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 3B de @migracion.md (declaratizar idle.start).

CONTEXTO: Fase 3A ✅. Parche start_seen + B1/B2/B3 aún en Python.

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- tests/test_flow_transitions.py
- scripts/validate_flow.py (si añades validación de campos nuevos)

IMPLEMENTAR:

1. Eliminar start_seen y ramas B1/B2/B3
   - Quitar patch start_seen en _process_node
   - Quitar ramas current_step=="start" + start_seen en _process_message_body
   - Quitar B2 self-loop hardcode (L336–343)

2. Declaratizar en JSON (nodo start):
   - node.self_loop_behavior
   - node.fallback (puede reutilizar texto de meta.start_fallback)
   - node.suppress_repeat_message

3. Motor: leer flags JSON para self-loop sin re-procesar nodo

RESTRICCIONES:
- NO reintroducir repeat-order
- NO tocar StateManager ni services
- Preservar comportamiento tabla Fase 3B

TEST DE CIERRE:
- rg 'start_seen' chatbot/app/core/flow_engine.py → 0
- 2º "hola" no re-dispara welcome
- no hay flags start_seen en StateManager/data
- pytest tests/test_flow_transitions.py -q
- Añadir test_idle_start_second_hola_fallback
```

### Comprobación manual Fase 3B

| Prueba | Esperado |
|--------|----------|
| `hola` (1ª vez) en start | Bienvenida + CTA |
| `hola` (2ª vez) en start | Fallback JSON, sin re-bienvenida |
| `no` / `ok` / `gracias` en start | Fallback JSON |
| `menu` / `pedido` / `reservar` en start | Routing normal |

---

## Fase 3C — Limpieza final del motor

**Estado:** ❌ **PENDING**

**Objetivo:** Dejar `FlowEngine` sin lógica de flujo residual.

**Cambios:**

- `_process_message_body` debe quedar mínimo:
  - intent parse
  - action execution
  - transition apply
- Eliminar:
  - cualquier referencia a step naming en routing
  - cualquier routing especial por nodo no cubierto por JSON
- `_goto_ref` es el único helper de navegación directa permitido
- Mensajes estáticos restantes en `_action_*` → meta/nodo donde sea estático

**Resultado final:**

```
FlowEngine = motor puro:
  input → intent → action → node transition → compose → return str
```

### Prompt 3C (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 3C de @migracion.md (limpieza final motor).

CONTEXTO: Fase 3A ✅. Fase 3B ✅. Sin start_seen ni B1/B2/B3.

ARCHIVOS:
- chatbot/app/core/flow_engine.py
- flows/restaurant_flow.json
- tests/test_flow_transitions.py

IMPLEMENTAR:

1. Adelgazar _process_message_body al pipeline mínimo:
   - handlers meta (abandon)
   - options[normalized]
   - global_commands
   - intent (parser)
   - action_on_input / free_text
   - fallback del nodo (node.fallback)

2. Eliminar routing especial residual por nombre de step o nodo

3. _goto_ref único helper de navegación directa

4. Mover mensajes estáticos restantes en _action_* a meta/nodo

RESTRICCIONES:
- NO tocar StateManager ni services
- NO reintroducir repeat-order

TEST FINAL:
- Todo el flujo restaurante funciona
- rg 'step ==|current_step ==' chatbot/app/core/flow_engine.py → 0 en routing
- 0 hardcoding de flujo
- pytest tests/test_flow_transitions.py -q
- python scripts/validate_flow.py
```

### Comprobación manual Fase 3C

| Prueba | Esperado |
|--------|----------|
| Flujo pedido domicilio completo | Sin regresión |
| Flujo reserva completo | Sin regresión |
| `cancelar` mid-order | `cancel_message` + idle.start |
| Input basura en cualquier nodo | `node.fallback` del nodo |

---

## Fase 4 — Cierre, regresión y documentación

**Estado:** ❌ **PENDIENTE**

**Meta:** Arquitectura estable, comprobaciones automáticas anti-regresión, docs al día.

### Prompt 4A (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 4 de @migracion.md (cierre).

CONTEXTO: Fases 1–2 completas. Fases 3A–3C completas. Parche idle.start eliminado en 3B.

ARCHIVOS:
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py
- tests/test_flow_transitions.py
- tutoriales/editar-flujo-restaurant.md (sección "Arquitectura motor")

IMPLEMENTAR:

1. validate_flow.py:
   - Si meta define claves Fase 2/3, validar que existen (lista documentada en script).
   - Opcional: warning si nodo tiene dual_message sin message_secondary.

2. Tests nuevos en test_flow_transitions.py:
   - test_process_message_always_returns_str (varios wa_id/mensajes)
   - test_cancelar_mid_order (si entorno lo permite)
   - test_abandon_confirm_reject_continues_order
   - test_idle_start_second_hola_fallback (2º hola en start)
   - test_idle_start_ignores_last_order_items (regresión: sin repetir)

3. Documentar en tutorial:
   - JSON = mapa (mensajes, transitions, options, meta)
   - Python = motor (actions devuelven outcome + datos dinámicos)
   - Prohibido: step hardcode, List[str], menú fuera de show_menu

4. Limpieza final flow_engine:
   - Eliminar código muerto
   - Una sola función _compose_message(node, parts) si aún no existe

COMPROBACIÓN DE CIERRE (migración completa):
- python scripts/validate_flow.py
- python scripts/validate_chatbot.py
- pytest tests/test_flow_transitions.py -q
- rg 'dual_message|step ==|List\[str\]|Reply = Union|format_menu|start_seen|_START_IDLE_FALLBACK' chatbot/app/core/flow_engine.py
  → format_menu solo _action_show_menu; resto 0
- rg 'return .*, "(order_|reservation_|menu_node|start)"' chatbot/app/core/flow_engine.py → 0 en _action_*
- Checklist manual abajo: todo probado

NO abrir nueva fase sin pedido explícito.
```

### Checklist manual final (Fase 4)

| # | Prueba | OK |
|---|--------|-----|
| 1 | `hola` (1ª vez) — bienvenida + CTA, sin catálogo | |
| 2 | `hola` (2ª vez) en start — fallback, sin re-bienvenida | |
| 3 | `menu` | |
| 4 | pedido domicilio completo | |
| 5 | pedido recoger (perfil con nombre) | |
| 6 | `cancelar` con pedido en curso | |
| 7 | `inicio` con pedido → abandon sí/no | |
| 8 | `hola` con `last_order_items` — bienvenida sin repetir | |
| 9 | reserva completa | |
| 10 | rechazo en `reservation_review` | |
| 11 | productos en texto libre desde idle (`2 pizza…`) | |

---

## Prompt de rescate (cualquier fase)

Si una comprobación FAIL y no sabes si es regresión de la fase o bug previo:

```
@migracion.md — Prompt rescate Fase N.

1. Ejecuta SOLO comprobación de cierre de Fase N-1 (si N>1).
2. Si Fase N-1 FAIL → arregla antes de seguir; no avances.
3. git diff chatbot/app/core/flow_engine.py flows/restaurant_flow.json
4. pytest tests/test_flow_transitions.py -v --tb=short
5. Reporta: causa raíz, fix mínimo, tabla PASS/FAIL actualizada.

RESTRICCIONES: no tocar StateManager ni services; no refactor extra.
```

---

## Orden de chats recomendado

| Chat | Fase | Estado | Prompt |
|------|------|--------|--------|
| 1 | 1 | ✅ DONE | 1A (referencia) |
| 2 | 2 core | ✅ DONE | 2A (referencia) |
| 2C | 2 contractual (fallback/nodos) | ✅ DONE | 2C (referencia) |
| — | Parche intermedio crítico | ✅ DONE (fuera de fases) | — |
| 3A | 3A — hardrouting | ❌ PENDING | **3A** |
| 3B | 3B — idle.start | ❌ PENDING | **3B** |
| 3C | 3C — limpieza motor | ❌ PENDING | **3C** |
| 4 | 4 | ❌ PENDING | 4A |

**Dependencias:** 2 requiere 1; 3A requiere 2 ✅; 3B requiere 3A; 3C requiere 3B; 4 requiere 3C.

---

## Qué NO es esta migración

- Multi-tenant / `business_id` en StateManager (otro roadmap).
- Cambiar formato `states` → otro schema.
- Mover lógica de `OrderService.parse_order_text` al JSON.
- Hot-reload de flujo sin reiniciar bot.
- Repeat-order (ver [Decisión irreversible](#decisión-irreversible-del-sistema--repeat-order)).

---

## Referencias

- Motor: `chatbot/app/core/flow_engine.py`
- Mapa: `flows/restaurant_flow.json`
- Tests flujo: `tests/test_flow_transitions.py`
- Validador: `scripts/validate_flow.py`
- Manual edición: `tutoriales/editar-flujo-restaurant.md`
- Migración anterior (states/transitions): `README_PROMPTS.md` v1.19–v1.23
