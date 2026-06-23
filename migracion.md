# Migración FlowEngine → MAPA (JSON) + MOTOR (Python)

Guía por fases para refactor estructural. Cada fase = chat(s) independiente(s).  
**Idea intacta:** `flows/restaurant_flow.json` = mapa (mensajes, transitions, options, meta); `flow_engine.py` = motor (leer nodo → action → outcome → transition → estado → un `str`).  
**No tocar** `StateManager`, servicios (`OrderService`, `MenuService`, etc.) ni formato `states` del JSON.

---

## Estado implementado (runtime actual)

| Fase / bloque | Estado | Resumen verificado en código |
|---------------|--------|------------------------------|
| **Fase 1** — Motor puro | ✅ **IMPLEMENTADA** | `process_message` siempre `str`; composición genérica en `_process_node`; menú solo vía `_action_show_menu`; `hola` en idle = bienvenida + CTA JSON sin catálogo |
| **Fase 2** — UX estática al JSON | ⚠️ **PARCIAL** | `_resolve_ux_text`; claves meta abandon + greeting en JSON; cero UX hardcode en handlers Fase 2; pendiente: `node.fallback` por nodo + fix L402 + ampliar validador (ver fixes contractuales) |
| **Parche crítico** — idle.start estable | ✅ **APLICADO (fuera de fases)** | `start_seen` + `meta.start_fallback` (texto en JSON) + ramas B1/B2/B3 en `flow_engine.py`; **no** cuenta como fase completada |
| **Fase 3** — Routing declarativo | ❌ **PENDIENTE REAL** | Steps hardcode (`start`, `menu_node`, `order_start`, `order_modify`); parche idle.start aún en Python |
| **Fase 4** — Cierre y docs | ❌ **PENDIENTE** | `validate_flow.py` sin claves meta Fase 2/3; tutorial sin sección arquitectura motor |

**Tests:** `pytest tests/test_flow_transitions.py -q` → **9 passed** (verificado).

### Parche crítico aplicado fuera de fases

Aplicado directo en `flow_engine.py` (independiente de Fase 2/3). Objetivo: `idle.start` estable sin re-bienvenida en self-loop ni en input no reconocido.

**Componentes en código:**

| Símbolo | Ubicación | Rol |
|---------|-----------|-----|
| `meta.start_fallback` | JSON L18 | Texto fallback B1/B2 (sin `NAV_HINT`); leído vía `_resolve_ux_text("start_fallback", node)` |
| `start_seen` en `data` | `_process_node` L475–476 | `True` tras primer render exitoso de `start`; `reset()` borra `data` |
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

**Repeat-order:** eliminado del runtime. **No** forma parte de ninguna fase pendiente. **No** reimplementar.

Antes existía flujo “¿repetir tu pedido anterior?” (`_handle_repeat_order`, `awaiting_repeat_order`, `skip_repeat_order_once`, claves `repeat_order_*`). Borrado en el parche crítico idle.start. Motivo: re-bienvenida / UX inconsistente. Hoy: `welcome_customer` = no-op; `last_order_items` en perfil **no** dispara prompt de repetición.

---

## Estado actual vs objetivo

| Capa | Hoy (runtime real) | Objetivo |
|------|-------------------|----------|
| `flows/restaurant_flow.json` | Nodos, transitions, options, mensajes; `meta` con `cancel_message`, `global_commands`, `navigation_hint` | Igual + **toda** UX estática (abandon, greeting order, fallback idle.start declarativo) |
| `flow_engine.py` | Motor + routing con steps hardcode + parche `start_seen` + UX abandon/greeting en Python | Solo: leer nodo → action → outcome → transition → estado → **un** `str` |
| `StateManager` | `flow`, `step`, `data` (incl. `start_seen`, `awaiting_abandon_confirm` transitorios) | Sin cambios de contrato |
| `gateway.py` | Acepta `str \| list[str]` | Sigue funcionando; motor solo devuelve `str` |
| `parser.py` | `infer_user_intent` | Sin cambios de negocio |
| `scripts/validate_flow.py` | Valida refs, transitions, outcomes de acciones | Ampliar en Fase 4 (claves meta Fase 2/3) |

### Deuda conocida en `flow_engine.py`

| Problema | Ubicación (método / símbolo) | Estado | Qué hacer |
|----------|------------------------------|--------|-----------|
| `Reply = Union[str, List[str]]` / `_as_reply` | — | ✅ Resuelto (Fase 1) | — |
| Menú inyectado en `start` desde Python | — | ✅ Resuelto (Fase 1) | `format_menu` solo en `_action_show_menu` |
| Repeat-order | — | ✅ Eliminado (parche) | No reintroducir |
| UX abandonar pedido | `_handle_abandon_confirm`; `_resolve_global_command` `inicio`+carrito | ✅ Fase 2 | `meta.abandon_confirm_*` vía `_resolve_ux_text` |
| Greeting durante pedido | `_process_message_body` (`order_start` / `order_modify`) | ✅ Fase 2 | `meta.order_greeting_while_ordering` vía `_resolve_ux_text` |
| `pedido_implicito` con steps fijos | `_process_message_body` | ❌ Fase 3 | `intercept_products` (o similar) en nodos idle |
| Salto hardcode `idle.start` en greeting idle | `_process_message_body` | ❌ Fase 3 | `options` JSON + helper `_goto_ref` |
| Parche `start_seen` + texto `meta.start_fallback` | L336–340, L399–400, L475–476 (routing); texto ya en JSON | ❌ **Deuda Fase 3** | Declaratizar routing: `node.fallback` + flag self-loop en JSON |
| `step == "start"` para `start_seen` | `_process_node` L475 | ❌ **Deuda Fase 3** | Sin nombre de step hardcode en Python |
| Mensajes estáticos en `_action_*` | varios `_action_*` | ❌ Fase 3–4 | Estáticos → JSON; dinámicos (carrito, totales, errores con datos) quedan en action |
| `cancel_message` | `_resolve_global_command` | ✅ Fase 2 | Lee `meta.cancel_message` vía `_resolve_ux_text` |

### Pipeline del motor

**Pipeline actual** (Fase 1 ✅ + Fase 2 ⚠️ parcial + parche crítico ✅):

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

**Pipeline objetivo** (post Fase 3–4):

```
process_message(text) → str
  → handlers meta (abandon)          # solo leen JSON + StateManager
  → options[normalized]              # self-loop / fallback desde JSON
  → global_commands                  # refs + reglas mínimas de estado
  → intent (parser)                  # intercept_products por nodo, sin steps hardcode
  → action_on_input / free_text        # outcome → transitions JSON
  → fallback del nodo                  # incl. idle.start 2º hola
  → compose: message + action_msg + message_after_action + message_secondary
  → append NAV_HINT si meta lo permite
  → return str
```

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

**Estado:** ⚠️ **PARCIAL** — cerrada cuando **NO** existe string UX visible al usuario en `flow_engine.py` (salvo `_action_*` dinámicos, `NAV_HINT`, routing `start_seen`/B1–B2 de Fase 3) **y** los fixes contractuales de fallback están aplicados (ver sección al final de Fase 2).

**Meta:** Motor cero copy estático de usuario. Todo texto UX viene del JSON (`meta` o `node.fallback`). Python solo decide **qué clave leer** y **cuándo**; nunca redacta mensajes de negocio.

### Reglas de resolución de UX (obligatorias)

**Origen del texto** — orden de prioridad único, sin excepciones:

| Prioridad | Fuente | Cuándo |
|-----------|--------|--------|
| 1 | `flow.meta[<clave>]` | Clave explícita para el caso (abandon, greeting order, cancel, etc.) |
| 2 | `node.fallback` | Clave meta ausente o vacía en el nodo actual |
| 3 | `_SYSTEM_TECHNICAL_FALLBACK` | Solo error técnico de configuración; **prohibido** como UX de negocio |

**Implementación:** helper `_resolve_ux_text(meta_key, node)` en `flow_engine.py`. Un solo punto de resolución; prohibido `self.meta.get(key, "texto…")` con default UX en Python.

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

### Fuera de alcance Fase 2 (Fase 3)

- Routing `start_seen` + ramas B1–B3 en Python (texto `meta.start_fallback` ya en JSON)
- `pedido_implicito`, greeting idle → `idle.start`
- Mensajes dinámicos en `_action_*`

### Prompt 2A (referencia — ya aplicado)

```
Ejecuta ÚNICAMENTE Fase 2 de @migracion.md (UX en JSON).

CONTEXTO: Fase 1 hecha. Parche crítico idle.start aplicado. repeat-order NO existe.

OBJETIVO: Fase 2 100% determinista — cero string UX visible en flow_engine.py
(salvo _action_* dinámicos, NAV_HINT, routing start_seen/B1-B2 de Fase 3).

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

### Prompt 2B (solo si 2A dejó strings sueltos)

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
| Input basura en `menu_node` | `node.fallback` del nodo (no `"Error interno..."`) | ❌ Pendiente |

---

### Fase 2 — Fixes contractuales de cierre (obligatorio)

> Este bloque es parte del contrato de Fase 2. No es Fase 3 ni parche externo.
> Fase 2 queda **cerrada** cuando todos los ítems a continuación estén ✅.

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

#### Correcciones de coherencia del sistema

| Ítem | Acción | Archivo |
|------|--------|---------|
| L14: "Fase 2 IMPLEMENTADA" | Cambiar a **parcial** hasta cierre contractual de fallbacks | `migracion.md` |
| L92: pipeline dice "Fase 2 ⚠️ parcial" | Queda correcta; actualizar a ✅ al completar este bloque | `migracion.md` |
| L29–36 y L99–109: referencia a `_START_IDLE_FALLBACK` | Reemplazar por `meta.start_fallback`; la constante no existe en código actual | `migracion.md` |
| L366: referencia a `_START_IDLE_FALLBACK` en Fase 3 | Reemplazar por `meta.start_fallback` + parche `start_seen` | `migracion.md` |

> **Separación Fase 2 / Fase 3:** El **texto** de `start_fallback` ya está en `meta.start_fallback` (JSON). Lo que queda para Fase 3 es declaratizar el **routing** (`start_seen`, ramas B1/B2, `step == "start"` hardcode en Python). No son deuda de Fase 2.

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

### Prompt 2C — Fixes contractuales de cierre (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE los fixes contractuales de cierre de Fase 2 descritos en @migracion.md
(sección "Fase 2 — Fixes contractuales de cierre").

CONTEXTO: Fase 1 ✅. Fase 2 core ✅ (abandon/cancel/greeting en meta). Parche idle.start ✅.
Pendiente: fallback por nodo, fix L402, ampliar validador.

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
- No tocar lógica de Fase 3 (start_seen, ramas B1/B2, routing por step, pedido_implicito).
- No cambiar transitions, outcomes ni options existentes.
- No nuevas dependencias.

COMPROBACIÓN DE CIERRE (todo PASS antes de terminar):
- python scripts/validate_flow.py → 0 errores
- pytest tests/test_flow_transitions.py -q → sin regresiones
- rg '_resolve_ux_text\("fallback"' chatbot/app/core/flow_engine.py → 0 matches
- Manual: input basura en menu_node → node.fallback, no "Error interno..."
```

---

## Fase 3 — Routing declarativo y adelgazar `_process_message_body`

**Estado:** ❌ **PENDIENTE REAL** — no iniciada en código.

**Meta:** Decisiones de flujo solo vía JSON (`options`, `transitions`, `global_commands`, flags de nodo). Motor sin listas de steps hardcode ni routing `start_seen` / B1–B2 en Python (texto `meta.start_fallback` ya en JSON desde Fase 2).

**Sigue en Python hoy:** `pedido_implicito`, greeting idle → `idle.start`, parche B1/B2/B3, `step == "start"` para `start_seen`. Greeting order ya en meta (Fase 2 ✅).

### Prompt 3A (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 3 de @migracion.md (routing declarativo).
CONTEXTO: Fase 1 hecha. Fase 2 completa. Parche crítico idle.start
aplicado (start_seen + B1/B2/B3 en Python). Esta fase declaratiza routing y el parche idle.start.
ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- tests/test_flow_transitions.py
- scripts/validate_flow.py (si añades validación de campos nuevos)
IMPLEMENTAR:
1. pedido_implicito declarativo
   - Quitar current_step in {"start", "menu_node"}
   - Campo JSON en nodo idle (ej. intercept_products: true) en start y menu_node
   - Motor: si nodo tiene intercept_products y intent tiene productos → pedido
2. Greeting en order declarativo
   - Quitar current_step in {"order_start", "order_modify"} hardcode
   - Campo JSON (ej. order_greeting_on_greeting: true) o meta.order_greeting_while_ordering
   - Mover string hardcode a meta JSON (cierra deuda Fase 2 parcial si aplica)
3. idle.start parche → JSON
   - Quitar ramas start_seen / current_step=="start" en _process_message_body (constante `_START_IDLE_FALLBACK` ya eliminada; texto vive en `meta.start_fallback`)
   - Quitar patch start_seen en _process_node
   - Solución declarativa mínima, ejemplos:
     - node.fallback en nodo start con texto actual de B1
     - flag JSON tipo suppress_self_reprocess o equivalente para self-loop options sin re-bienvenida
   - Comportamiento a preservar (tabla):
     | Input | step | Esperado |
     | hola (1ª vez) | start | bienvenida + CTA |
     | hola (2ª vez) | start | fallback B1, sin re-bienvenida |
     | no/ok/gracias | start | fallback B1 |
     | menu/pedido/reservar | start | routing normal |
   - Añadir tests que cubran 2º hola y input no reconocido en start
4. Greeting idle sin hardcode de step
   - Quitar _parse_ref("idle.start") suelto en _process_message_body
   - Helper único _goto_ref(wa_id, ref) si reduce duplicación (mínimo)
5. Mensajes estáticos restantes en _action_* y abandon
   - Mover a meta/nodo donde sea estático
   - Dejar en action solo dinámicos (carrito, totales, errores con datos)
RESTRICCIONES:
- NO tocar StateManager ni services
- NO cambiar transitions/outcomes semántica
- Formato states intacto
COMPROBACIÓN DE CIERRE:
- pytest tests/test_flow_transitions.py -q
- python scripts/validate_flow.py
- rg 'start_seen|_START_IDLE_FALLBACK' chatbot/app/core/flow_engine.py → 0
- rg '"start"|"menu_node"|"order_start"|"order_modify"' chatbot/app/core/flow_engine.py → 0 en _process_message_body
- rg 'current_step == "start"' chatbot/app/core/flow_engine.py → 0
- Tests existentes PASS + nuevos tests idle.start fallback
```

### Comprobación manual Fase 3

| Prueba | Esperado |
|--------|----------|
| `2 pizza hawaiana` sin decir pedido (desde idle) | Entra flujo order |
| `hola` (1ª vez) en start | Bienvenida + CTA |
| `hola` (2ª vez) en start | Fallback B1, sin re-bienvenida |
| `no` / `ok` / `gracias` en start | Fallback B1 |
| `menu` / `pedido` / `reservar` en start | Routing normal |
| `hola` en `order_modify` | Mensaje meta, no salto raro |
| `cancelar` mid-order | `cancel_message` + idle.start |

---

## Fase 4 — Cierre, regresión y documentación

**Estado:** ❌ **PENDIENTE**

**Meta:** Arquitectura estable, comprobaciones automáticas anti-regresión, docs al día.

### Prompt 4A (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 4 de @migracion.md (cierre).

CONTEXTO: Fases 1–3 completas. Parche idle.start ya declarativizado en Fase 3.

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
| 1 | 1 | ✅ Hecha | 1A (referencia) |
| 2 | 2 | ✅ Hecha | 2A (referencia) |
| — | Parche crítico | ✅ Hecho (fuera de fases) | — |
| 3 | 3 | ❌ Pendiente real | **3A** |
| 4 | 4 | ❌ Pendiente | 4A |

**Dependencias:** 2 requiere 1; 3 requiere 2 (completar abandon/greeting meta); 4 requiere 3.

---

## Qué NO es esta migración

- Multi-tenant / `business_id` en StateManager (otro roadmap).
- Cambiar formato `states` → otro schema.
- Mover lógica de `OrderService.parse_order_text` al JSON.
- Hot-reload de flujo sin reiniciar bot.
- Repeat-order (ver [Decisiones removidas](#decisiones-removidas-del-sistema)).

---

## Referencias

- Motor: `chatbot/app/core/flow_engine.py`
- Mapa: `flows/restaurant_flow.json`
- Tests flujo: `tests/test_flow_transitions.py`
- Validador: `scripts/validate_flow.py`
- Manual edición: `tutoriales/editar-flujo-restaurant.md`
- Migración anterior (states/transitions): `README_PROMPTS.md` v1.19–v1.23
