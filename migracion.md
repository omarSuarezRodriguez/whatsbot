# Migración FlowEngine → MAPA (JSON) + MOTOR (Python)

Guía por fases para refactor estructural. Cada fase = chat(s) independiente(s).  
**Idea intacta:** `flows/restaurant_flow.json` = mapa (mensajes, transitions, options, meta); `flow_engine.py` = motor (leer nodo → action → outcome → transition → estado → un `str`).  
**No tocar** `StateManager`, servicios (`OrderService`, `MenuService`, etc.) ni formato `states` del JSON.

---

## Estado implementado (runtime actual)

| Fase / bloque | Estado | Resumen verificado en código |
|---------------|--------|------------------------------|
| **Fase 1** — Motor puro | ✅ **IMPLEMENTADA** | `process_message` siempre `str`; composición genérica en `_process_node`; menú solo vía `_action_show_menu`; `hola` en idle = bienvenida + CTA JSON sin catálogo |
| **Fase 2** — UX estática al JSON | ⚠️ **PARCIAL** | Abandon/inicio y greeting en order siguen hardcode en Python; claves `abandon_confirm_*` / `order_greeting_while_ordering` **no** están en `restaurant_flow.json` |
| **Parche post-Fase 2** — idle.start estable | ✅ **APLICADO** | Fix runtime en `flow_engine.py`; **no** es fase nueva |
| **Fase 3** — Routing declarativo | ❌ **PENDIENTE** | Steps hardcode, parche `start_seen` / fallback en Python |
| **Fase 4** — Cierre y docs | ❌ **PENDIENTE** | `validate_flow.py` sin claves meta Fase 2/3; tutorial sin sección arquitectura motor |

**Tests:** `pytest tests/test_flow_transitions.py -q` → **9 passed** (verificado).

### Parche post-Fase 2 (detalle)

Aplicado directo en `flow_engine.py` tras Fase 2 parcial:

- **Repeat-order eliminado por completo** (ver [Decisiones removidas](#decisiones-removidas-del-sistema)).
- **`_action_welcome_customer`** → no-op (`"", None`); no lee `last_order_items`.
- **`welcome_customer`** sigue en `_actions` y en JSON por compatibilidad.
- **`data.start_seen`:** `True` tras primer render exitoso de `start` en `_process_node`; `reset()` lo borra (`data` vuelve a `{}`).
- **`_START_IDLE_FALLBACK`** (constante Python, texto exacto):
  > Disculpa, no logré entenderte. ¿Podrías intentarlo de nuevo? También puedes escribir menu, pedido o reservar.

| Rama | Comportamiento |
|------|----------------|
| **B1** | Input no enrutado en `step=="start"` con `start_seen=True` → fallback directo, sin `_process_node`, sin cambiar step, sin `NAV_HINT` (`suppress_navigation: true` en nodo) |
| **B2** | Options self-loop (`hola`/`buenas`/`hey` → `start`) con `start_seen=True` → mismo fallback (no re-bienvenida) |
| **B3** | Saludo idle (`is_greeting` + `flow=="idle"` + `current_step!="start"`) no re-ejecuta `_process_node(start)` si ya `current_step=="start"` |

Test de regresión: `test_idle_start_ignores_last_order_items` (usuario con `last_order_items` → bienvenida sin “repetir”).

---

## Decisiones removidas del sistema

**Repeat-order cancelado permanentemente.** No reimplementar.

El flujo “¿repetir tu pedido anterior?” (`_handle_repeat_order`, `awaiting_repeat_order`, `skip_repeat_order_once`, claves `repeat_order_*` en meta) fue **eliminado** en el parche post-Fase 2. Motivo: bug runtime (re-bienvenida / UX inconsistente en `idle.start`). `welcome_customer` permanece como action no-op por compatibilidad con el JSON; `last_order_items` en perfil de usuario no dispara ningún prompt de repetición.

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
| UX abandonar pedido | `_handle_abandon_confirm`, `_resolve_global_command` (`inicio` + carrito) | ⚠️ Fase 2 parcial | Textos → `meta` JSON (`abandon_confirm_prompt`, `abandon_confirm_invalid`) |
| Greeting durante pedido | `_process_message_body` (`order_start` / `order_modify`) | ⚠️ Fase 2 parcial | → `meta.order_greeting_while_ordering` o flag de nodo |
| `pedido_implicito` con steps fijos | `_process_message_body` | ❌ Fase 3 | `intercept_products` (o similar) en nodos idle |
| Salto hardcode `idle.start` en greeting idle | `_process_message_body` | ❌ Fase 3 | `options` JSON + helper `_goto_ref` |
| Parche `start_seen` + `_START_IDLE_FALLBACK` | `_process_message_body`, `_process_node`, constante L31 | ❌ Fase 3 | `node.fallback` + flag self-loop en JSON |
| `step == "start"` para `start_seen` | `_process_node` | ❌ Fase 3 | Declarativo (sin nombre de step en Python) |
| Mensajes estáticos en `_action_*` | varios `_action_*` | ❌ Fase 3–4 | Estáticos → JSON; dinámicos (carrito, totales, errores con datos) quedan en action |
| `cancel_message` | `_resolve_global_command` | ✅ Parcial | Ya lee `meta.cancel_message`; abandon prompt no |

### Pipeline del motor

**Pipeline actual** (Fase 1 ✅ + Fase 2 ⚠️ + parche ✅):

```
process_message(text) → str
  → _handle_abandon_confirm          # hardcode Python (Fase 2 pendiente)
  → action_on_input (si aplica)
  → global_commands                  # inicio+carrito: hardcode abandon (Fase 2 pendiente)
  → options[normalized]              # B2: self-loop start + start_seen → _START_IDLE_FALLBACK
  → greeting idle → _parse_ref idle.start   # B3: skip si ya en start
  → intent (parser) + pedido_implicito      # current_step in {start, menu_node} hardcode
  → free_text action
  → greeting order_start/order_modify       # hardcode Python (Fase 2 pendiente)
  → B1: start + start_seen → _START_IDLE_FALLBACK
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

**Estado:** ⚠️ **PARCIAL**

**Meta:** Motor no contiene copy de usuario; solo lee `meta` y campos de nodo.

**Hecho:** `cancel_message` en meta; `_resolve_global_command("cancelar")` lo usa.

**Pendiente:** textos abandon (`_handle_abandon_confirm`, `inicio`+carrito); `order_greeting_while_ordering`; claves meta correspondientes en JSON.

**Cancelado:** repeat-order (ver [Decisiones removidas](#decisiones-removidas-del-sistema)); parche post-Fase 2 lo eliminó del runtime.

### Prompt 2A (chat nuevo — completar Fase 2)

```
Ejecuta ÚNICAMENTE Fase 2 de @migracion.md (UX en JSON).

CONTEXTO: Fase 1 hecha. Parche post-Fase 2 aplicado (repeat-order eliminado; NO reintroducir).

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py (validar nuevas claves meta opcionales)

IMPLEMENTAR:

1. Añadir en meta (restaurant_flow.json) textos que hoy están hardcode en Python:
   - abandon_confirm_prompt (pedido en curso + sí/no)
   - abandon_confirm_invalid
   - order_greeting_while_ordering (hoy en order_start/order_modify greeting)
   Mantener cancel_message existente.

2. Refactor flow_engine:
   - _handle_abandon_confirm → solo lee meta + is_confirmation/is_rejection
   - _resolve_global_command "inicio" con carrito → usa meta.abandon_confirm_prompt
   - greeting en order_start/order_modify → usa meta.order_greeting_while_ordering

3. Fallback por nodo: seguir usando node.fallback del JSON (ya existe).

RESTRICCIONES:
- NO reintroducir repeat-order ni _handle_repeat_order.
- No cambiar transitions ni outcomes.
- No cambiar services.

COMPROBACIÓN DE CIERRE:
- python scripts/validate_flow.py
- pytest tests/test_flow_transitions.py -q
- rg 'Tienes un pedido en curso|Cuando quieras, cuéntame' chatbot/app/core/flow_engine.py → 0 matches
- Test manual: pedido a medias → inicio → mensaje meta; hola con last_order_items → bienvenida sin repetir (test_idle_start_ignores_last_order_items)
```

### Prompt 2B (solo si 2A dejó strings sueltos)

```
Continúo Fase 2 @migracion.md. Busca strings de UX restantes en flow_engine.py
(fuera de _action_* dinámicos y NAV_HINT). Muévelos a meta del JSON o a fallback de nodo.
NO tocar repeat-order. Reporta tabla de strings movidos. Misma comprobación de cierre Fase 2.
```

### Comprobación manual Fase 2

| Prueba | Esperado | Estado |
|--------|----------|--------|
| Pedido iniciado → `inicio` | Mensaje desde `meta.abandon_confirm_prompt` | ⚠️ hoy hardcode Python |
| `hola` con `last_order_items` | Bienvenida normal, sin “repetir” | ✅ (`test_idle_start_ignores_last_order_items`) |
| `hola` durante `order_start` | `meta.order_greeting_while_ordering` | ⚠️ hoy hardcode Python |

---

## Fase 3 — Routing declarativo y adelgazar `_process_message_body`

**Estado:** ❌ **PENDIENTE**

**Meta:** Decisiones de flujo solo vía JSON (`options`, `transitions`, `global_commands`, flags de nodo). Motor sin listas de steps hardcode ni parche `start_seen` en Python.

### Prompt 3A (chat nuevo — copiar tal cual)

```
Ejecuta ÚNICAMENTE Fase 3 de @migracion.md (routing declarativo).
CONTEXTO: Fase 1 hecha. Fase 2 parcial. Parche post-Fase 2 aplicado (repeat eliminado;
start_seen + fallback B1/B2 en Python). Esta fase declaratiza routing y el parche idle.start.
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
   - Quitar _START_IDLE_FALLBACK constante y ramas start_seen / current_step=="start" en _process_message_body
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
- NO reintroducir repeat-order
- NO tocar StateManager ni services
- NO cambiar transitions/outcomes semántica
- Formato states intacto
COMPROBACIÓN DE CIERRE:
- pytest tests/test_flow_transitions.py -q
- python scripts/validate_flow.py
- rg 'start_seen|_START_IDLE_FALLBACK|_handle_repeat_order|repeat_order|skip_repeat' chatbot/app/core/flow_engine.py → 0
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

CONTEXTO: Fases 1–3 completas. Repeat-order no existe. Parche idle.start ya declarativizado en Fase 3.

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
   - Prohibido: step hardcode, List[str], menú fuera de show_menu, repeat-order

4. Limpieza final flow_engine:
   - Eliminar código muerto
   - Una sola función _compose_message(node, parts) si aún no existe

COMPROBACIÓN DE CIERRE (migración completa):
- python scripts/validate_flow.py
- python scripts/validate_chatbot.py
- pytest tests/test_flow_transitions.py -q
- rg 'dual_message|step ==|List\[str\]|Reply = Union|format_menu|start_seen|_START_IDLE_FALLBACK|repeat_order' chatbot/app/core/flow_engine.py
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

RESTRICCIONES: no tocar StateManager ni services; no reintroducir repeat-order; no refactor extra.
```

---

## Orden de chats recomendado

| Chat | Fase | Estado | Prompt |
|------|------|--------|--------|
| 1 | 1 | ✅ Hecha | 1A (referencia) |
| 2 | 2 | ⚠️ Parcial | 2A (2B si hace falta) |
| 3 | 3 | ❌ Siguiente | **3A** |
| 4 | 4 | ❌ Pendiente | 4A |

**Dependencias:** 2 requiere 1; 3 requiere 2 (completar abandon/greeting meta); 4 requiere 3.

---

## Qué NO es esta migración

- Multi-tenant / `business_id` en StateManager (otro roadmap).
- Cambiar formato `states` → otro schema.
- Mover lógica de `OrderService.parse_order_text` al JSON.
- Hot-reload de flujo sin reiniciar bot.
- Reimplementar repeat-order.

---

## Referencias

- Motor: `chatbot/app/core/flow_engine.py`
- Mapa: `flows/restaurant_flow.json`
- Tests flujo: `tests/test_flow_transitions.py`
- Validador: `scripts/validate_flow.py`
- Manual edición: `tutoriales/editar-flujo-restaurant.md`
- Migración anterior (states/transitions): `README_PROMPTS.md` v1.19–v1.23
