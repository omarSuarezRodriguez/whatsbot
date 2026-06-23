# PROMPT MAESTRO — Migración flujo por estados (JSON declarativo)

> **Cuándo usar:** El bot ya funciona con `flows/restaurant_flow.json` + `chatbot/app/core/flow_engine.py`.  
> **Objetivo:** Todas las transiciones del flujo restaurante viven en JSON, agrupadas por estados (`idle`, `order`, `reservation`). Python solo ejecuta lógica de negocio y devuelve **outcomes**, no nombres de nodo destino.

**Fuente de contexto adicional:** `tutoriales/cambiar-flujo-chatbot.md` (se actualiza en cada fase).

---

## 0. CONTEXTO

### Situación actual

| Qué | Dónde |
|-----|-------|
| Textos, `options`, comandos globales | `flows/restaurant_flow.json` |
| Saltos tras acciones (sí/no, domicilio, etc.) | **Python** — `return "msg", "order_delivery"` en `_action_*` |
| Estado del usuario | `StateManager`: `flow`, `step`, `data` |

### Situación objetivo

```json
"states": {
  "idle": { "initial": "start", "nodes": { ... } },
  "order": { "initial": "order_start", "nodes": { ... } },
  "reservation": { "initial": "reservation_start", "nodes": { ... } }
}
```

Cada nodo con `transitions`: `{ "confirmed": "order_delivery", "rejected": "order_modify" }`.  
Referencias cruzadas: `"order.order_start"`, `"idle.start"`.  
`null` en transición = quedarse en el mismo nodo.

### Reglas de implementación

- Mínimo código, sin dependencias nuevas, sin abstracciones no pedidas.
- Comentarios `ponytail:` solo si hay atajo con techo conocido.
- Tras tocar código: `graphify update .`
- **No tocar:** menú en BD, multi-tenant BD, `config/prompts.py` salvo que tests lo exijan.

---

## 1. VOCABULARIO DE OUTCOMES (contrato fijo)

| Acción | Outcomes |
|--------|----------|
| `welcome_customer`, `show_menu`, `show_cart`, `show_reservation_summary` | `success` o quedarse (`null`) |
| `capture_order` | `success`, `empty_cart` |
| `handle_order_confirmation` | `confirmed`, `rejected`, `invalid` |
| `capture_delivery_type` | `domicilio`, `recoger_has_name`, `recoger_no_name`, `invalid` |
| `capture_address` | `success_has_name`, `success_no_name`, `invalid` |
| `capture_customer_name` | `success`, `invalid` |
| `save_order` | `success` → `idle.start`, `empty_cart` → `order.order_start` |
| `capture_persons` | `success`, `invalid` |
| `capture_date` | `success`, `invalid` |
| `capture_time` | `success`, `missing_date`, `invalid` |
| `handle_reservation_confirmation` | `confirmed`, `rejected`, `incomplete`, `invalid` |
| `save_reservation` | `success` → `idle.start`, `incomplete` → `reservation.reservation_start` |

---

## 2. MAPA DE TRANSICIONES (referencia)

```
idle: start, menu_node

order:
  order_start        →(success)→ order_review
  order_review       →(confirmed)→ order_delivery | (rejected)→ order_modify | (empty_cart)→ order_start
  order_modify       →(success)→ order_review
  order_delivery     →(domicilio)→ order_address | (recoger_has_name)→ order_saved | (recoger_no_name)→ order_customer_name
  order_address      →(success_has_name)→ order_saved | (success_no_name)→ order_customer_name
  order_customer_name→(success)→ order_saved
  order_saved        →(success)→ idle.start

reservation:
  reservation_start  →(success)→ reservation_date
  reservation_date   →(success)→ reservation_time
  reservation_time   →(success)→ reservation_review | (missing_date)→ reservation_date
  reservation_review →(confirmed)→ reservation_saved | (rejected|incomplete)→ reservation_start
  reservation_saved  →(success)→ idle.start
```

Comandos globales (refs): `menu` → `idle.menu_node`, `pedido` → `order.order_start`, `reservar` → `reservation.reservation_start`, `inicio`/`cancelar` → `idle.start`.

---

## 3. CÓMO USAR ESTE DOCUMENTO

| Paso | Acción |
|------|--------|
| 1 | **Un chat nuevo por fase** (recomendado). Evita contexto sucio y diffs gigantes. |
| 2 | Cada mensaje empieza con `@PROMPT_MIGRACION_FLUJO_ESTADOS.md` |
| 3 | Pega **solo un** prompt de fase (sección 5). No combines fases en un mensaje. |
| 4 | Al terminar la fase, el agente debe ejecutar la **comprobación de cierre** y reportar resultado. |
| 5 | Si todo OK → chat nuevo → siguiente prompt. Si falla → prompt utilidad U1 en el **mismo** chat. |

### ¿Chat independiente o mismo chat?

| Escenario | Qué hacer |
|-----------|-----------|
| Fase 1 → 2 → 3 feliz | **Chat nuevo** por cada fase |
| Algo falló en comprobación | **Mismo chat** + Prompt U1 |
| Retomas al día siguiente | **Chat nuevo** + Prompt U2 |
| Solo quieres validar sin migrar | Prompt V0 (solo lectura) |

### Mensaje típico para abrir fase

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Ejecuta ÚNICAMENTE la Fase 1 del plan de migración.
No avances a Fase 2 aunque parezca trivial.
Al final ejecuta TODA la comprobación de cierre y dime PASS/FAIL por ítem.
```

### Tras cada fase exitosa

```
Listo Fase N. Abro chat nuevo para Fase N+1.
```

(O pega directamente el Prompt de la siguiente fase en chat nuevo.)

---

## 4. ÍNDICE DE PROMPTS

| Prompt | Fase | Qué hace |
|--------|------|----------|
| **V0** | — | Verificación previa (sin tocar código) |
| **1** | Infraestructura | Loader dual, `_parse_ref`, `validate_flow.py`, tutorial nota |
| **2** | Migración core | JSON `states`, outcomes en acciones, tests, tutorial reescrito |
| **3** | Cierre | Quitar legacy, docs finales, regresión completa |
| **U1** | — | Corregir fase que falló comprobación |
| **U2** | — | Continuar en chat nuevo (resume) |

---

## 5. PROMPTS LISTOS (copiar y pegar)

### Prompt V0 — Verificación previa (opcional, sin código)

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Solo verificación previa a la migración. NO modifiques nada.

1. Lee flows/restaurant_flow.json y lista los 14 nodos con su campo flow.
2. En flow_engine.py, lista cada _action_* que hace return con segundo valor = nombre de nodo (no outcome).
3. ¿Existen tests de flujo conversacional? Si no, confirma que habrá que crearlos en Fase 2.
4. Resume en 5 líneas el gap entre JSON actual y formato states+transitions.

Di: "Listo para Prompt 1 (Fase 1)" o bloqueos encontrados.
```

---

### Prompt 1 — Fase 1: Infraestructura (sin cambiar comportamiento)

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Ejecuta ÚNICAMENTE la Fase 1. NO migres restaurant_flow.json aún.

IMPLEMENTAR:

1. chatbot/app/core/flow_engine.py
   - _normalize_flow(raw): si JSON tiene "states", aplanar a self.nodes + metadata; si tiene "nodes" plano, igual que hoy.
   - _parse_ref(ref, current_state) -> (state, step): "order.order_start" -> ("order","order_start"); "start" sin prefijo -> idle o estado actual.
   - _resolve_transition(node, outcome) -> Optional[str]: lee node.transitions[outcome]; si no hay transitions, fallback al segundo return de la acción (legacy).
   - Durante Fase 1 las acciones pueden seguir devolviendo next_step legacy; el resolver debe soportar ambos.

2. scripts/validate_flow.py (nuevo, stdlib)
   - Carga FLOWS_PATH.
   - Valida: options y global_commands apuntan a nodo existente.
   - Si hay transitions: destinos existen; outcomes cubren acciones del nodo.
   - Exit 0/1 con lista de errores.

3. tutoriales/cambiar-flujo-chatbot.md
   - Añadir al final sección "Migración en curso (formato por estados)" con nota de dual-format y comando validate_flow.py.
   - NO borrar aún la sección de transiciones en flow_engine.py.

COMPROBACIÓN DE CIERRE (ejecutar y reportar PASS/FAIL cada ítem):

- python scripts/validate_flow.py
- python scripts/validate_chatbot.py
- pytest tests/ -q --ignore=tests/test_realtime_ws.py
- Smoke: hola + menu vía FlowEngine (script inline o test mínimo)
- rg "_normalize_flow|_parse_ref|_resolve_transition" chatbot/app/core/flow_engine.py
- graphify update .

NO empezar Fase 2. Al final: tabla PASS/FAIL + archivos tocados.
```

---

### Prompt 2 — Fase 2: JSON por estados + outcomes

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Ejecuta ÚNICAMENTE la Fase 2. Asume Fase 1 ya pasó comprobación.

IMPLEMENTAR:

1. Reescribir flows/restaurant_flow.json al formato "states" (14 nodos, mismos textos).
   - transitions según mapa del maestro (sección 2).
   - meta.global_commands con refs: "pedido": "order.order_start", etc.

2. flow_engine.py — todas las _action_*:
   - Cambiar return "msg", "order_review" -> return "msg", "success" (outcome de la tabla del maestro).
   - _process_node usa _resolve_transition cuando el nodo tiene transitions.
   - _handle_repeat_order, _resolve_global_command: usar _parse_ref.

3. tests/test_flow_transitions.py (nuevo):
   - test_order_happy_path_domicilio
   - test_order_modify_then_confirm
   - test_reservation_full
   - test_reservation_rejected_restarts
   - test_global_menu_from_order

4. tutoriales/cambiar-flujo-chatbot.md — REESCRIBIR:
   - Tabla "qué archivo tocar": transiciones solo en JSON.
   - §1: añadir states, transitions, refs estado.nodo.
   - §2: renombrar a "Transiciones en JSON" con tabla action->outcomes; quitar returns Python.
   - Actualizar mapa, checklist, ejemplo de cambiar orden de pasos vía transitions.

COMPROBACIÓN DE CIERRE:

- python scripts/validate_flow.py  (JSON con states, 0 errores)
- pytest tests/ -q
- python scripts/validate_chatbot.py
- rg 'return .*, "(order_|reservation_|menu_node|start)"' chatbot/app/core/flow_engine.py
  -> 0 matches en _action_* (solo comentarios permitidos)
- Los 5 tests nuevos pasan
- graphify update .

NO empezar Fase 3. Tabla PASS/FAIL + diff resumido JSON.
```

---

### Prompt 3 — Fase 3: Limpieza y regresión final

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Ejecuta ÚNICAMENTE la Fase 3. Asume Fases 1 y 2 pasaron comprobación.

IMPLEMENTAR:

1. Quitar compatibilidad legacy en _normalize_flow / _resolve_transition (solo formato states).
2. Revisar _handle_repeat_order, _resolve_global_command, abandon confirm: sin strings sueltos de nodo; todo vía _parse_ref.
3. tutoriales/cambiar-flujo-chatbot.md — VERSIÓN FINAL:
   - Quitar sección "Migración en curso".
   - Ejemplo completo de nodo con transitions (order_review del JSON real).
   - Workflow "añadir paso nuevo" actualizado (JSON + outcome + validate_flow).
   - Checklist con validate_flow.py + pruebas manuales.

COMPROBACIÓN DE CIERRE:

- python scripts/validate_flow.py
- python scripts/validate_chatbot.py
- python scripts/validate_system.py  (si falla por entorno, documentar)
- pytest tests/ -q
- rg '"nodes":\s*\{' flows/restaurant_flow.json -> 0 (solo states)
- Tutorial sin instrucciones de editar Python para saltos sí/no/domicilio
- graphify update .

Checklist manual (reportar probado sí/no):
- hola, menu, pedido domicilio completo, pedido recoger con nombre en perfil,
  cancelar mid-order, reserva completa, rechazo en review, comandos globales.

Migración completa si todo PASS.
```

---

### Prompt U1 — Corregir fase que falló

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

La Fase N falló en comprobación. NO avances a la siguiente fase.

Fallos reportados:
[PEGA AQUÍ la tabla PASS/FAIL o el error exacto]

Arregla solo lo necesario para que pase TODA la comprobación de cierre de Fase N.
Re-ejecuta comprobación completa y reporta PASS/FAIL.
```

---

### Prompt U2 — Continuar en chat nuevo

```
@PROMPT_MIGRACION_FLUJO_ESTADOS.md

Continúo la migración flujo por estados. Fases 1..N-1 ya completadas en otro chat.

Antes de implementar Fase N:
1. Lee flows/restaurant_flow.json y confirma si ya está en formato states o legacy.
2. Ejecuta comprobación de cierre de Fase N-1 (comandos del maestro).
3. Si PASS -> ejecuta ÚNICAMENTE Fase N.
4. Si FAIL -> aplica Prompt U1 sobre lo que falte de la fase anterior; no avances.

Fase a ejecutar ahora: [1 | 2 | 3]
```

---

## 6. ENTREGABLES POR FASE

| Fase | Archivos | Verificación clave |
|------|----------|-------------------|
| 1 | `flow_engine.py`, `scripts/validate_flow.py`, tutorial (nota) | validate_flow + smoke + pytest |
| 2 | `restaurant_flow.json`, `flow_engine.py`, `tests/test_flow_transitions.py`, tutorial | 5 tests + grep sin destinos en Python |
| 3 | `flow_engine.py`, tutorial (final) | regresión + checklist manual |

---

## 7. COMMITS SUGERIDOS

```
feat(flow): phase 1 - dual loader and validate_flow script
feat(flow): phase 2 - states JSON and outcome transitions
feat(flow): phase 3 - remove legacy flow format
docs(flow): update cambiar-flujo-chatbot tutorial
```

Un commit por fase (docs puede ir en el mismo commit de la fase que toca el tutorial).
