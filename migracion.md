# Migración FlowEngine → MAPA (JSON) + MOTOR (Python)

Guía por fases para refactor estructural. Cada fase = chat(s) independiente(s).  
**No tocar** `StateManager`, servicios (`OrderService`, `MenuService`, etc.) ni formato `states` del JSON.

---

## Estado actual vs objetivo

| Capa | Hoy | Objetivo |
|------|-----|----------|
| `flows/restaurant_flow.json` | Nodos, transitions, options, mensajes | Igual + **toda** UX estática (incl. confirmaciones globales) |
| `flow_engine.py` | Motor + routing + UX hardcode + casos por step | Solo: leer nodo → action → outcome → transition → estado → **un** `str` |
| `StateManager` | `flow`, `step`, `data` | Sin cambios |
| `gateway.py` | Acepta `str \| list[str]` | Sigue funcionando; motor solo devuelve `str` |
| `parser.py` | `infer_user_intent` | Sin cambios de negocio; motor solo lo invoca |
| `scripts/validate_flow.py` | Valida refs y transitions | Ampliar en Fase 4 |

### Deuda conocida en `flow_engine.py` (líneas ~151–463)

| Problema | Ubicación | Qué hacer |
|----------|-----------|-----------|
| `Reply = Union[str, List[str]]` | L31, retornos | Eliminar; siempre `str` |
| `dual_message` + `step == "start"` + menú Python | `_as_reply` L158–168 | Pipeline genérico; menú solo vía `show_menu` en JSON |
| UX abandonar pedido | `_handle_abandon_confirm` L187–197 | Textos → `meta` JSON |
| UX repetir pedido | `_handle_repeat_order` L199–224 | Textos → `meta` JSON |
| UX cancelar + carrito activo | `_resolve_global_command` L243–254 | Textos → `meta` JSON |
| Salto hardcode `idle.start` en greetings | `_process_message_body` L409–411, L452–457 | `options` / `fallback` JSON |
| `pedido_implicito` con steps fijos | L432–443 | `meta` flag o nodo intermedio |
| Mensajes de validación en `_action_*` | L577+ | Fase 3: estáticos → JSON; dinámicos (carrito, resumen) quedan en action |

### Pipeline objetivo del motor

```
process_message(text)
  → handlers meta (abandon/repeat)     # solo leen JSON + StateManager
  → options[normalized]                # JSON
  → global_commands                    # JSON refs + reglas mínimas de estado
  → intent (parser)                    # sin cambiar parser
  → action_on_input / free_text        # outcome → transitions JSON
  → fallback del nodo                  # JSON
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

**Meta:** `FlowEngine` compone mensajes igual para todos los nodos. Cero ramas `step == "…"`. Cero menú en Python.

### Prompt 1A (chat nuevo)

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
- No mover textos de abandon/repeat aún (Fase 2).

COMPROBACIÓN DE CIERRE (tabla PASS/FAIL):
- pytest tests/test_flow_transitions.py -q
- python -c "from chatbot.runtime import get_bot_context; e=get_bot_context(start_background=False).flow_engine; r=e.process_message('573009998877','hola'); assert isinstance(r,str); assert 'Bienvenido' in r or 'bienvenido' in r.lower()"
- rg 'step == "start"|List\[str\]|Reply = Union' chatbot/app/core/flow_engine.py  → 0 matches
- rg 'format_menu' chatbot/app/core/flow_engine.py  → solo en _action_show_menu
- Confirmar: hola NO incluye bloque de menú completo (solo bienvenida + CTA JSON); menu sí muestra menú vía show_menu

NO empezar Fase 2.
```

### Comprobación manual Fase 1

| Prueba | Esperado |
|--------|----------|
| `hola` | Un string: bienvenida + opciones menu/pedido/reservar (sin catálogo de productos) |
| `menu` | Menú formateado + message_after_action del nodo |
| `pedido` → productos → flujo completo | Sin regresión en tests existentes |

---

## Fase 2 — UX estática al JSON (meta)

**Meta:** Motor no contiene copy de usuario; solo lee `meta` y campos de nodo.

### Prompt 2A (chat nuevo)

```
Ejecuta ÚNICAMENTE Fase 2 de @migracion.md (UX en JSON).

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py (validar nuevas claves meta opcionales)

IMPLEMENTAR:

1. Añadir en meta (restaurant_flow.json) textos que hoy están hardcode en Python:
   - abandon_confirm_prompt (pedido en curso + sí/no)
   - abandon_confirm_invalid
   - repeat_order_prompt
   - repeat_order_invalid
   - repeat_order_not_found
   - order_greeting_while_ordering (hoy en order_start/order_modify greeting)
   Mantener cancel_message existente.

2. Refactor flow_engine:
   - _handle_abandon_confirm → solo lee meta + is_confirmation/is_rejection
   - _handle_repeat_order → solo lee meta + lógica de estado (sin strings sueltos)
   - _resolve_global_command "inicio" con carrito → usa meta.abandon_confirm_prompt
   - greeting en order_start/order_modify → usa meta.order_greeting_while_ordering

3. Fallback por nodo: seguir usando node.fallback del JSON (ya existe).

RESTRICCIONES:
- No cambiar transitions ni outcomes.
- No cambiar services.

COMPROBACIÓN DE CIERRE:
- python scripts/validate_flow.py
- pytest tests/test_flow_transitions.py -q
- rg 'Tienes un pedido en curso|repetir tu pedido|Cuando quieras, cuéntame' chatbot/app/core/flow_engine.py → 0 matches
- Test manual documentado: pedido a medias → inicio → mensaje meta; hola con last_order → repetir sí/no
```

### Prompt 2B (solo si 2A dejó strings sueltos)

```
Continúo Fase 2 @migracion.md. Busca strings de UX restantes en flow_engine.py
(fuera de _action_* y NAV_HINT). Muévelos a meta del JSON o a fallback de nodo.
Reporta tabla de strings movidos. Misma comprobación de cierre Fase 2.
```

### Comprobación manual Fase 2

| Prueba | Esperado |
|--------|----------|
| Pedido iniciado → `inicio` | Mensaje desde meta.abandon_confirm_prompt |
| `hola` con pedido anterior → `no` | Bienvenida normal, sin strings viejos en Python |
| `hola` durante order_start | meta.order_greeting_while_ordering |

---

## Fase 3 — Routing declarativo y adelgazar `_process_message_body`

**Meta:** Decisiones de flujo solo vía JSON (`options`, `transitions`, `global_commands`). Motor sin listas de steps hardcode.

### Prompt 3A (chat nuevo)

```
Ejecuta ÚNICAMENTE Fase 3 de @migracion.md (routing declarativo).

ARCHIVOS:
- flows/restaurant_flow.json
- chatbot/app/core/flow_engine.py

IMPLEMENTAR:

1. Eliminar conjuntos hardcode de steps en _process_message_body:
   - current_step in {"start", "menu_node"} para pedido_implicito
   - current_step in {"order_start", "order_modify"} para greeting
   Reemplazar por campos JSON en nodo o meta, por ejemplo:
   - intercept_products: true en nodos idle que deben derivar a pedido
   - suppress_greeting_redirect: true donde no aplique
   (elegir nombres mínimos; documentar en comentario ponytail: si hace falta)

2. pedido_implicito:
   - Si usuario manda productos en nodo con intercept_products → _resolve_global_command("pedido")
   - Sin mencionar "start" ni "menu_node" en Python

3. Greeting en idle:
   - Usar options del nodo (hola/buenas/hey → start ya en JSON) o meta.idle_greeting_reprocess
   - Eliminar _parse_ref("idle.start") repetido: helper _goto_ref(wa_id, ref) único

4. _resolve_global_command:
   - Mantener solo reglas de ESTADO (carrito activo, reset data) — no copy UX (ya Fase 2)
   - Destinos solo vía global_commands + _parse_ref

5. Mensajes estáticos en _action_* (ej. "Responde *sí* para confirmar..."):
   - Mover a message / message_after_action del nodo destino o a meta.templates[outcome]
   - Dejar en action solo mensajes dinámicos (carrito formateado, totales, errores con datos)

RESTRICCIONES:
- Outcomes y services sin cambiar semántica.
- Formato states intacto.

COMPROBACIÓN DE CIERRE:
- pytest tests/test_flow_transitions.py -q
- python scripts/validate_flow.py
- rg '"start"|"menu_node"|"order_start"|"order_modify"' chatbot/app/core/flow_engine.py
  → 0 matches en _process_message_body (helpers _parse_ref con "idle.start" en reset OK)
- rg 'pedido_implicito' chatbot/app/core/flow_engine.py → 0 o solo en log_meta string
- Test: "2 pizza" en idle deriva a pedido igual que antes
```

### Comprobación manual Fase 3

| Prueba | Esperado |
|--------|----------|
| `2 pizza hawaiana` sin decir pedido | Entra flujo order |
| `hola` en order_modify | Mensaje meta, no salto raro |
| `cancelar` mid-order | cancel_message + idle.start |

---

## Fase 4 — Cierre, regresión y documentación

**Meta:** Arquitectura estable, comprobaciones automáticas anti-regresión, docs al día.

### Prompt 4A (chat nuevo)

```
Ejecuta ÚNICAMENTE Fase 4 de @migracion.md (cierre).

ARCHIVOS:
- chatbot/app/core/flow_engine.py
- scripts/validate_flow.py
- tests/test_flow_transitions.py
- tutoriales/editar-flujo-restaurant.md (sección "Arquitectura motor")

IMPLEMENTAR:

1. validate_flow.py:
   - Si meta define claves Fase 2, validar que existen (lista documentada en script).
   - Opcional: warning si nodo tiene dual_message sin message_secondary.

2. Tests nuevos en test_flow_transitions.py:
   - test_process_message_always_returns_str (varios wa_id/mensajes)
   - test_cancelar_mid_order (si entorno lo permite)
   - test_abandon_confirm_reject_continues_order

3. Documentar en tutorial:
   - JSON = mapa (mensajes, transitions, options, meta)
   - Python = motor (actions devuelven outcome + datos dinámicos)
   - Prohibido: step hardcode, List[str], menú fuera de show_menu

4. Limpieza final flow_engine:
   - Eliminar código muerto (_as_reply si absorbida, Reply alias)
   - Una sola función _compose_message(node, parts) si aún no existe

COMPROBACIÓN DE CIERRE (migración completa):
- python scripts/validate_flow.py
- python scripts/validate_chatbot.py
- pytest tests/test_flow_transitions.py -q
- rg 'dual_message|step ==|List\[str\]|Reply = Union|format_menu' chatbot/app/core/flow_engine.py
  → format_menu solo _action_show_menu; resto 0
- rg 'return .*, "(order_|reservation_|menu_node|start)"' chatbot/app/core/flow_engine.py → 0 en _action_*
- Checklist manual abajo: todo probado

NO abrir nueva fase sin pedido explícito.
```

### Checklist manual final

| # | Prueba | OK |
|---|--------|-----|
| 1 | hola | |
| 2 | menu | |
| 3 | pedido domicilio completo | |
| 4 | pedido recoger (perfil con nombre) | |
| 5 | cancelar con pedido en curso | |
| 6 | inicio con pedido → abandon sí/no | |
| 7 | repetir pedido sí/no | |
| 8 | reserva completa | |
| 9 | rechazo en reservation_review | |
| 10 | productos en texto libre desde idle | |

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

| Chat | Fase | Prompt |
|------|------|--------|
| 1 | 1 | 1A |
| 2 | 2 | 2A (2B si hace falta) |
| 3 | 3 | 3A |
| 4 | 4 | 4A |

**Dependencias:** 2 requiere 1; 3 requiere 2; 4 requiere 3.

---

## Qué NO es esta migración

- Multi-tenant / `business_id` en StateManager (otro roadmap).
- Cambiar formato `states` → otro schema.
- Mover lógica de `OrderService.parse_order_text` al JSON.
- Hot-reload de flujo sin reiniciar bot.

---

## Referencias

- Motor: `chatbot/app/core/flow_engine.py`
- Mapa: `flows/restaurant_flow.json`
- Tests flujo: `tests/test_flow_transitions.py`
- Manual edición: `tutoriales/editar-flujo-restaurant.md`
- Migración anterior (states/transitions): `README_PROMPTS.md` v1.19–v1.23
