# ARCHITECTURE_RULES.md

## 🧠 PRINCIPIOS

- JSON define flujo
- Python ejecuta lógica
- Services contienen negocio
- StateManager controla sesión
- No hardcode de nodos
- Multi-tenant obligatorio
- Flujo declarativo



# WhatsBot — Tecnologías + Arquitectura (solo lo importante)

## 🧱 Backend
- FastAPI → API REST + webhook de WhatsApp
- Python → motor principal del bot
- Uvicorn (implícito) → servidor ASGI

---

## 🗄️ Base de datos
- SQLAlchemy → ORM
- Alembic → migraciones
- SQLite (dev)
- PostgreSQL (prod)

---

## 🤖 Motor conversacional
- FlowEngine (Python) → ejecuta flujo conversacional
- StateManager → manejo de estado por usuario
- JSON (Flow DSL) → definición del flujo

Archivo clave:
- flows/restaurant_flow.json (único flujo global)

---

## 📩 Integración WhatsApp
- Twilio API → envío y recepción de mensajes

---

## 🧠 NLP / Procesamiento lenguaje
- RapidFuzz → fuzzy matching
- parser.py → detección de pedidos e intents (dominio restaurante)

---

## 🔐 Autenticación
- JWT → autenticación multi-tenant (business_id)
- bcrypt → hashing PIN / seguridad

---

## 🏢 Multi-tenant
- contextvars → aislamiento por business_scope
- business_id → clave principal de tenant

---

## ⚙️ Tiempo real
- WebSockets → panel admin
- Redis pub/sub (opcional)
- In-memory event bus (default)

---

## 🧩 Arquitectura de servicios
- services/ → CRUD puro SQLAlchemy (BD)
- chatbot/app/services/ → capa puente para el motor
- DBStore → adaptador legacy (motor ↔ BD)

---

## 🧠 Componentes clave del sistema
- gateway.py → única entrada del bot
- FlowEngine → ejecución del flujo
- StateManager → estado conversacional
- Services → lógica de negocio
- DBStore → persistencia unificada

---

## 📦 Persistencia
- JSON file → estado de conversación (StateManager)
- PostgreSQL → datos de negocio
- SQLite → desarrollo local

---

## 🧭 Flujo del sistema
Twilio → FastAPI → gateway.py → FlowEngine → StateManager → Services → DB

---

## ⚠️ Dependencias críticas del diseño
- JSON como fuente de flujo
- Gateway como único entrypoint
- State fuera de BD (archivo local)
- Servicios separados del motor
- Multi-tenant por contexto (no por instancia)

---

## 🧨 Puntos importantes de arquitectura
- FlowEngine acoplado al dominio restaurante
- Flujo único global (no por tenant)
- Acciones hardcodeadas en Python
- Parser grande y específico
- Prompts duplicados (JSON + BD + config)



--


## Resumen Ejecutivo

WhatsBot es una **plataforma multi-tenant** para bots de WhatsApp orientada hoy al dominio restaurante (pedidos, menú, reservas, confirmación admin). La arquitectura real combina:

- **Backend SaaS**: FastAPI + SQLAlchemy + Alembic (SQLite dev / PostgreSQL prod)
- **Motor conversacional**: JSON declarativo + `FlowEngine` imperativo
- **Integraciones**: Twilio (WhatsApp), WebSocket/FCM (tiempo real), JWT+bcrypt (auth dueño)

### Stack y capas

| Capa | Tecnología / Ubicación |
|------|------------------------|
| API REST + webhook | FastAPI — `api/` |
| Motor del bot | Python — `chatbot/app/core/` |
| Puerta única del bot | `chatbot/gateway.py` |
| Estado conversacional | `StateManager` → JSON en disco (`data/user_states.json`) |
| Definición del flujo | `flows/restaurant_flow.json` (único archivo global) |
| Negocio / persistencia | `services/` + `models/` + `infrastructure/` |
| Adaptador bot→BD | `chatbot/app/integrations/db_store.py` |
| Config tenant | BD: `businesses`, `business_intents`, `business_prompts`, `menu_items` |
| Config global / semilla | `config/` (.env, intents, prompts, settings) |
| Tiempo real | `services/realtime_service.py` (WS in-memory; Redis pub/sub opcional) |
| NLP pedidos | RapidFuzz + `chatbot/app/core/parser.py` (~2900 LOC) |
| Validación de flujos | `scripts/validate_flow.py` |
| Tests arquitectura flujo | `tests/test_flow_transitions.py` |

### Filosofía detectada (ya presente en el código)

1. **JSON describe, Python ejecuta** — Migración Fase 1–4 cerrada: textos UX, opciones, transiciones y comandos globales viven en el JSON; Python devuelve `(mensaje, outcome)` y el JSON decide el destino.
2. **Gateway único** — Todo mensaje WhatsApp entra por `handle_incoming_message()`; la API no reimplementa el parser.
3. **Multi-tenant por contexto** — `business_scope(business_id)` activa menú, intents y prompts por negocio vía `contextvars`.
4. **BD como fuente de verdad operativa** — Google Sheets eliminado; `DBStore` mantiene la interfaz legacy del bot.
5. **Evolución por configuración primero** — Cambiar copy o rutas del flujo restaurante no debería tocar Python si la acción ya existe.

### Reglas más importantes para futuras modificaciones

| # | Regla |
|---|-------|
| R1 | El JSON describe el flujo; el motor solo navega, compone mensajes y ejecuta acciones registradas. |
| R2 | Toda lógica de dominio (pedido, menú, reserva, cliente) va en Services — no en routing del motor. |
| R3 | El estado conversacional (`flow`, `step`, `data`) solo lo muta `StateManager`. |
| R4 | Cada tenant se activa con `business_scope`; nunca asumir un solo negocio en código nuevo. |
| R5 | Agregar copy o transiciones = JSON + `validate_flow.py`. Agregar acción = registro explícito + validador + test. |
| R6 | No hardcodear nombres de nodos (`step == "order_start"`) ni strings UX en Python. |
| R7 | No duplicar rutas de navegación fuera del JSON del flujo (`global_commands` en `meta` es la fuente para el motor). |
| R8 | Terminología nueva: `business` / `negocio`, no `restaurant`. |

### Estado de madurez arquitectónica

El sistema **funciona y es mantenible** para un dominio restaurante con múltiples negocios que comparten el mismo flujo. La deuda principal no es estructural sino de **generalización**: el motor, las acciones y el JSON están acoplados al caso restaurante; menú/intents/prompts ya son multi-tenant pero el flujo y el admin legacy no lo son por completo.

---

## Arquitectura Actual

### Visión general

```
Cliente WhatsApp
    → Twilio POST /webhook
    → api/routes/whatsapp.py
        → resolve_business_id_for_webhook(To) → business_id
        → conversation_service (persiste mensaje en BD)
        → chatbot/gateway.handle_incoming_message()
            → business_scope(business_id)
            → FlowEngine.process_message(wa_id, body)
                → StateManager (lee/escribe flow/step/data)
                → JSON nodes (options, transitions, meta)
                → Services via acciones _action_*
            → client_message_log (audit, no afecta respuesta)
        → conversation_service (persiste respuesta)
        → Twilio TwiML / REST
```

Paralelamente, el dueño del negocio usa la **API REST + WebSocket** (`api/routes/whatsbot.py`, `realtime.py`) con JWT scoped por `business_id`.

### Pipeline del motor (`FlowEngine`)

Orden fijo en `_process_message_body`:

```
input normalizado
  → abandon confirm (meta)
  → options del nodo actual
  → global_commands (meta.global_commands)
  → infer_user_intent (parser + intents del tenant)
  → intercept_products / order_greeting_on_greeting (flags de nodo)
  → action_on_input (free_text)
  → fallback del nodo
```

Composición de salida en un solo `str`:

```
message → resultado action → message_after_action → message_secondary (si dual_message)
```

Las transiciones se resuelven exclusivamente por `outcome` en el JSON (`transitions` del nodo).

### Formato del flujo JSON

Estructura actual (obligatoria; el formato plano `nodes` raíz ya no se soporta):

```json
{
  "meta": { "global_commands": {}, "...textos UX..." },
  "states": {
    "idle": { "initial": "start", "nodes": { "start": { ... } } },
    "order": { "nodes": { ... } },
    "reservation": { "nodes": { ... } }
  }
}
```

`_normalize_flow()` aplana `states.*.nodes` a un dict interno `self.nodes` con campo `flow` por nodo.

### Wiring del bot (`chatbot/runtime.py`)

Singleton lazy `BotContext`:

- `StateManager` (JSON persistido)
- `DBStore` → delega a `services/*` con `business_id` activo
- Facades: `MenuService`, `OrderService`, `ReservationService`, `UserService`, `AdminService`
- `FlowEngine` (carga un único `FLOWS_PATH` al init)
- `BlockedUsersCache` (TTL sobre BD)

### Capas de servicios (realidad dual)

Existen **dos capas** con responsabilidades solapadas pero distintas:

| Capa | Rol | Consumidor |
|------|-----|------------|
| `chatbot/app/services/*` | Facade del motor; interfaz orientada a acciones del flujo | `FlowEngine`, `AdminService` |
| `services/*` | CRUD SQLAlchemy puro | API REST, `DBStore`, notificaciones |

`DBStore` es el **puente** que mantiene la superficie legacy (`self.sheets` en varios servicios) mientras escribe en BD multi-tenant.

### Multi-tenant en runtime

Por cada mensaje:

1. Webhook resuelve `business_id` desde `Business.twilio_whatsapp_from`.
2. `business_scope(business_id)` carga prompts, menú e índice de intents del tenant.
3. `StateManager._resolve_key()` usa clave `{business_id}:{wa_id}`.
4. `DBStore._active_business_id()` scopea lecturas/escrituras.

Configurable por tenant hoy: **nombre**, **menú**, **intents**, **prompts gateway**.  
**No** configurable por tenant hoy: **archivo de flujo**, **acciones del motor**, **número admin legacy**, **NAV_HINT global**.

---

## Mapa de Responsabilidades

| Responsabilidad | Fuente de verdad primaria | Componente ejecutor | Duplicaciones / notas |
|-----------------|---------------------------|---------------------|------------------------|
| Definición del flujo (estados, nodos, transiciones) | `flows/restaurant_flow.json` | `FlowEngine` | Un solo archivo global (`FLOWS_PATH`). No hay `business_flows` en BD. |
| Comandos globales de navegación (runtime) | `meta.global_commands` en JSON | `FlowEngine._resolve_global_command` | `config/intents.GLOBAL_COMMAND_ROUTES` existe como semilla BD, no lo lee el motor en runtime. |
| Frases/tokens de intents NL | `business_intents.config_json` (BD) | `parser.infer_user_intent` | Semilla en `config/intents.py`. `_routes` en BD no usado por motor. |
| Textos UX del flujo (captura, confirmación, etc.) | `meta.*` en JSON del flujo | `FlowEngine._resolve_ux_text` | Duplicados legacy en `config/prompts.py` y `business_prompts` (gateway). |
| Textos gateway (error, empty body) | `business_prompts` → fallback `config/prompts.py` | `gateway`, `business_context.get_prompt` | Tres capas posibles para el mismo copy. |
| Estado conversacional (`flow`, `step`, `data`) | `StateManager` → `user_states.json` | Solo `StateManager` | Perfil cliente (nombre, dirección) también en tabla `customers`. |
| Carrito / reserva en curso | `state.data.cart`, `state.data.reservation` | Acciones + `StateManager.patch_data` | Flags implícitos: `awaiting_abandon_confirm`, `shown_steps`. |
| Menú disponible | `menu_items` (BD) | `MenuService` → `DBStore` | Override por request vía `business_context`. |
| Parseo de pedido NL | `parser.OrderParser` | `OrderService.parse_order_text` | Lógica de dominio en `core/`, no en `services/`. |
| Persistencia pedidos | Tabla `orders` (BD) | `services/order_service` vía `DBStore` | `_action_save_order` también llama `notification_service.on_order_pending` (segunda escritura defensiva). |
| Persistencia reservas | Tabla `reservations` (BD) | `DBStore.create_reservation` | Sin API REST dedicada aún. |
| Historial chat (app dueño) | `conversations` + `messages` (BD) | `conversation_service` | Independiente del estado del motor. |
| Identificación tenant | `businesses.twilio_whatsapp_from` | `resolve_business_id_for_webhook` | Fallback a negocio default si no hay match. |
| Auth dueño | JWT (`business_id` en token) | `api/middleware/auth.py` | PIN bcrypt por negocio en `businesses.pin_hash`. |
| Admin WhatsApp legacy | `.env ADMIN_WHATSAPP_NUMBER` | `AdminService.is_admin` | **Ignora** `Business.admin_whatsapp_number` en runtime. |
| Branding nombre negocio | `business_prompts.restaurant_name` → `.env RESTAURANT_NAME` | `FlowEngine._render` | Variable legacy `restaurant_name` en templates. |
| Bloqueo usuarios | `customers.blocked` (BD) | `BlockedUsersCache` + `AdminService` | Cache TTL in-memory por worker. |
| Tiempo real | WS hub + opcional Redis | `realtime_service` | In-memory por defecto; multi-worker requiere Redis. |
| Validación integridad flujo | `scripts/validate_flow.py` | CI / manual | `ACTION_OUTCOMES` duplica contrato acción↔outcome del motor. |

---

## Decisiones Arquitectónicas Detectadas

Estas decisiones **ya están implementadas** y no son aspiracionales:

### D1. Gateway como única puerta del bot
`chatbot/gateway.py` concentra admin vs cliente, bloqueos, errores y logging. La API delega en threadpool para no bloquear el event loop.

### D2. Flujo JSON con capas `meta` + `states`
Separación explícita entre configuración conversacional (`meta`) y topología (`states`). Documentada en `tutoriales/editar-flujo-restaurant.md`.

### D3. Acciones devuelven `(mensaje, outcome)`; JSON decide transición
Contrato estable post-migración. El validador `ACTION_OUTCOMES` lo formaliza.

### D4. `contextvars` para aislamiento multi-tenant
Reemplazo de mutación global de intents (problema histórico documentado en README). `business_scope` es obligatorio en el camino del webhook.

### D5. `DBStore` como adaptador Sheets→BD
Permite migrar persistencia sin reescribir facades del chatbot. Atributo `self.sheets` conservado por compatibilidad.

### D6. Semilla de config en onboarding
`onboard_business.py` / `create_business(seed_from_config=True)` copia `config/intents.py` y `config/prompts.py` a BD. El tenant editable vive en BD; archivos `config/*` son defaults.

### D7. Singleton del bot por proceso
Un `FlowEngine` y un `StateManager` por worker. Recarga de flujo vía `reload_flow()` (tests); no hot-reload por tenant.

### D8. Estado conversacional en JSON local, no en BD
`StateManager` persiste en disco con debounce. La BD guarda historial y entidades de negocio, no el `step` actual del bot.

### D9. Parser como motor de inteligencia de pedidos
`OrderParser` con fuzzy matching (RapidFuzz) es componente de dominio centralizado, invocado desde `OrderService`.

### D10. Doble canal admin: WhatsApp legacy + app REST/WS
Confirmación de pedidos puede llegar por WhatsApp admin o por API; `notification_service` sincroniza estado en BD.

---

## Principios Arquitectónicos Oficiales

Reglas permanentes recomendadas para toda modificación futura.

### Regla 1 — El JSON describe. El motor ejecuta.
- **Válido en JSON**: mensajes, fallbacks, `options`, `transitions`, `global_commands`, flags de nodo (`dual_message`, `intercept_products`, etc.).
- **Válido en motor**: mecanismos genéricos de navegación, composición, render de templates, dispatch de acciones.
- **Prohibido en motor**: strings UX de negocio, routing por nombre de nodo hardcodeado, copy de menú fuera de `_action_show_menu`.

### Regla 2 — FlowEngine es producto. Los negocios son configuración.
- Menú, intents, prompts y branding deben variar por tenant sin fork del motor.
- Hoy el flujo JSON es global: **aceptado como limitación conocida** hasta existir `flow_config` por tenant.
- Nuevas acciones genéricas (ej. `capture_field`, `confirm`) preferibles a acciones por vertical (`capture_persons`).

### Regla 3 — La lógica de negocio pertenece a Services.
- Persistencia, validación de dominio, formateo de entidades → `services/` o facades en `chatbot/app/services/`.
- `FlowEngine._action_*` solo orquesta: lee estado, llama servicio, devuelve outcome.
- Excepción aceptada: `parser.py` es dominio de pedidos pero vive en `core/` por historia; no agregar más parsers de dominio ahí.

### Regla 4 — El estado pertenece al StateManager.
- Mutaciones de `flow`, `step`, `data` solo vía API pública de `StateManager`.
- Datos de perfil duradero (nombre, dirección) → BD vía `UserService`; datos de sesión (carrito, reserva parcial) → `state.data`.
- Nuevos flags conversacionales → `state.data` con nombre documentado; evitar variables sueltas en servicios.

### Regla 5 — Una responsabilidad, un lugar.
- Navegación → JSON (`options`, `transitions`, `global_commands`).
- Intents NL → BD (`business_intents`).
- Copy gateway → BD (`business_prompts`); copy de flujo → JSON `meta`.
- No reintroducir `GLOBAL_COMMAND_ROUTES` como routing runtime paralelo.

### Regla 6 — Agregar tenant no debe modificar FlowEngine.
- Alta de negocio = script/API + filas BD + Twilio. **Cumplido hoy.**
- Si un tenant necesita flujo distinto, solución futura = config de flujo por tenant, no `if business_id` en el motor.

### Regla 7 — Agregar flujos = principalmente configuración.
- Mismo set de acciones: solo JSON + validación + tests de transición.
- Acción nueva: registrar en `_actions`, `ACTION_OUTCOMES`, test, documentar outcomes.

### Regla 8 — Sin decisiones de negocio hardcodeadas en el motor.
- Prohibido: lógica específica de `pedido`/`reservar`/`cart` en routing genérico salvo mecanismos declarativos (meta flags).
- Preferir mover semántica a meta (`active_order_command_targets`) o a servicios.

### Regla 9 — `business_scope` en todo camino que toque datos de tenant.
Obligatorio antes de `FlowEngine`, `DBStore`, o lectura de menú/intents.

### Regla 10 — Validar antes de desplegar cambios de flujo.
```bash
python scripts/validate_flow.py
```
Reiniciar worker del bot tras cambiar JSON (singleton carga al init).

---

## Fortalezas

Aspectos que funcionan bien y **deben preservarse**:

1. **Separación API ↔ motor** — Webhook delgado; lógica conversacional aislada en `chatbot/`.
2. **Modelo outcome→transition** — Desacopla decisión (Python) de navegación (JSON). Tests en `test_flow_transitions.py` lo protegen.
3. **Migración JSON Fase 1–4** — Copy y rutas fuera del motor; tutorial operativo existente.
4. **Multi-tenant runtime con contextvars** — Patrón correcto para concurrencia async + threadpool.
5. **DBStore** — Migración incremental Sheets→BD sin big-bang en el motor.
6. **Validador de flujo standalone** — Stdlib only; útil en CI y edición manual del JSON.
7. **Modelo de datos multi-tenant** — FK `business_id` en órdenes, conversaciones, menú, clientes.
8. **Auth JWT por negocio** — Aislamiento en API bien aplicado (`_require_same_tenant`).
9. **Gateway resiliente** — Errores capturados; respuesta genérica al usuario; log estructurado.
10. **Documentación operativa existente** — `docs/ARCHITECTURE.md`, tutoriales de flujo, guía negocios.

---

## Violaciones Detectadas

Lugares donde la implementación **contradice** la arquitectura deseada.

### V1. Motor acoplado al dominio restaurante
`FlowEngine._actions` enumera 15 acciones restaurante-specific (`capture_order`, `save_reservation`, etc.). Agregar un vertical distinto (ej. citas médicas) **requiere modificar el motor**.

**Evidencia**: registro cerrado en `flow_engine.py` líneas 55–71; `validate_flow.py` `ACTION_OUTCOMES` espejo.

### V2. Routing imperativo en `_resolve_global_command`
Lógica de negocio embebida en el motor:
- `_has_active_order()` conoce `cart` + `flow == "order"`
- Comportamiento especial de `pedido`, `inicio`, `cancelar` con confirmación de abandono
- Reset de `cart`/`reservation` al cambiar de flujo vía comando

Parte está mitigada por `meta.active_order_command_targets`, pero la semántica de abandono vive en Python.

### V3. Flujo JSON único para todos los tenants
`FLOWS_PATH` → `flows/restaurant_flow.json` global. No existe columna ni tabla de flujo por negocio. Multi-tenant parcial en configuración, no en topología conversacional.

### V4. Triplicación de textos
El mismo copy puede existir en:
1. `flows/restaurant_flow.json` → `meta`
2. `config/prompts.py` → `DEFAULT_PROMPTS`
3. `business_prompts.config_json` (BD)

`_seed_config_rows` sobrescribe BD desde `config/prompts.py`, no desde el JSON del flujo → riesgo de divergencia.

### V5. Admin legacy no multi-tenant
`AdminService.is_admin()` compara contra `ADMIN_WHATSAPP_NUMBER` global (.env). El campo `Business.admin_whatsapp_number` existe en modelo pero **no se usa** para identificar admin en runtime.

### V6. Duplicación de capa de servicios
`chatbot/app/services/order_service.py` vs `services/order_service.py` — misma entidad, dos APIs. Confusión para nuevos contribuidores; riesgo de lógica divergente.

### V7. Parser de dominio en `core/`
`parser.py` (~2900 LOC) es lógica de negocio de pedidos, no infraestructura del motor. Violación de separación Services vs Core.

### V8. Doble persistencia defensiva de pedidos
`DBStore.create_order` ya escribe en BD; `_action_save_order` además invoca `notification_service.on_order_pending` que puede re-persistir. Funciona pero contradice SSOT estricto.

### V9. Nomenclatura legacy `restaurant` / `sheets`
- `RESTAURANT_NAME`, `restaurant_flow.json`, `{{restaurant_name}}`
- `self.sheets` en servicios ya conectados a BD
- Docstrings obsoletos (`models/order.py` menciona Sheets)

### V10. Intents: rutas en dos mundos
`config/intents.GLOBAL_COMMAND_ROUTES` define rutas que el motor **no consume** (usa `meta.global_commands` del JSON). La semilla BD incluye `_routes` redundante.

### V11. `ensure_default_business` pisa config en cada arranque
Sincroniza nombre, Twilio y admin desde `.env` al negocio default — puede sobrescribir cambios hechos en BD.

### V12. Flags de nodo con semántica de dominio en motor
`intercept_products`, `order_greeting_on_greeting` — nombres y comportamiento restaurante en el loop genérico de `_process_message_body`.

---

## Deuda Técnica

### Alta prioridad

| ID | Problema | Impacto |
|----|----------|---------|
| DT-H1 | Admin global vs `Business.admin_whatsapp_number` | Segundo negocio no puede tener admin WA propio en legacy |
| DT-H2 | Flujo JSON global | Tenants no pueden tener conversaciones estructuralmente distintas |
| DT-H3 | Registro cerrado de acciones en FlowEngine | Cada nuevo dominio toca el motor |
| DT-H4 | Triplicación prompts (JSON / config / BD) | Ediciones inconsistentes entre canales |
| DT-H5 | Routing abandon/pedido en Python | Cambios UX de abandono requieren deploy de código |

### Media prioridad

| ID | Problema | Impacto |
|----|----------|---------|
| DT-M1 | Dual layer services (chatbot vs root) | Mantenimiento, imports confusos |
| DT-M2 | Parser en `core/` | Límite difuso motor vs dominio |
| DT-M3 | Estado en JSON file vs BD | Escalado horizontal, backup, consistencia multi-worker |
| DT-M4 | WS in-memory sin Redis por defecto | Eventos perdidos con múltiples workers |
| DT-M5 | `_build_intent_index_for_business` muta `GLOBAL_COMMAND_INTENTS` temporalmente | Fragilidad bajo tests paralelos |
| DT-M6 | `on_order_pending` doble escritura | Complejidad, posibles race conditions |
| DT-M7 | Perfil cliente duplicado (state vs customers) | Inconsistencia teórica nombre/dirección |
| DT-M8 | Docstrings y comentarios obsoletos (Sheets, Fase X) | Onboarding engañoso |

### Baja prioridad

| ID | Problema | Impacto |
|----|----------|---------|
| DT-L1 | Typo fix `pedid`→`pedido` hardcodeado en motor | Debería ser normalización en parser |
| DT-L2 | `NAV_HINT` solo en `config/bot_config.py` | No personalizable por tenant |
| DT-L3 | Client message log en archivos planos | Operacional, no arquitectónico |
| DT-L4 | `GREETING_PHRASES` / comandos en múltiples módulos | Drift menor |
| DT-L5 | Menu empty message hardcodeado en `MenuService.format_menu` | Copy fuera de JSON/prompts |

---

## Recomendaciones

### Hacer ahora

1. **Tratar `meta.global_commands` como única fuente de routing runtime** — No añadir rutas en `config/intents.py` esperando que el motor las lea.
2. **Todo cambio de flujo restaurante** → editar JSON + `python scripts/validate_flow.py` + test existente o caso nuevo en `test_flow_transitions.py`.
3. **Nuevo copy de flujo** → solo `meta` o `node.fallback` en JSON; no Python.
4. **Código nuevo multi-tenant** → siempre dentro de `business_scope`; leer admin/twilio desde BD cuando se extienda admin legacy.
5. **Documentar en PR** qué capa de prompts se editó (JSON vs BD vs config) para evitar divergencia.
6. **Usar terminología `business`** en código y docs nuevos.

### Hacer después

1. **Admin por tenant** — `AdminService.is_admin` debe consultar `Business.admin_whatsapp_number` del contexto activo (fallback .env solo para default).
2. **Flujo por tenant** — Columna `flow_json` o path en BD; `FlowEngine` carga bajo `business_scope` (cache LRU por `business_id`).
3. **Registro de acciones extensible** — Dict inyectable o entrypoints; separar acciones genéricas de vertical restaurante.
4. **Unificar prompts** — Una sola fuente: JSON `meta` para flujo; BD para gateway; eliminar duplicados en `config/prompts.py` gradualmente.
5. **Mover OrderParser** a `services/order_parser.py` o similar — `core/parser.py` solo inferencia de intents.
6. **Estado conversacional en BD** (opcional) — Tabla `conversation_state` por `(business_id, wa_id)` si se escala multi-worker.
7. **Consolidar servicios** — Facades del chatbot delegan sin reenvolver lógica; una sola implementación CRUD.
8. **Meta-driven abandon flow** — Reducir lógica hardcodeada de `_resolve_global_command` a flags declarativos.

### No hacer

1. **No reescribir FlowEngine** como framework genérico desde cero — evolucionar registro de acciones y carga de flujo.
2. **No reintroducir Google Sheets** ni segunda fuente de verdad para pedidos.
3. **No añadir `if business_id == "x"`** en el motor — es configuración mal ubicada.
4. **No duplicar transiciones** en Python y JSON.
5. **No mutar globals de módulo** para multi-tenant (patrón ya corregido con contextvars — no regresar).
6. **No crear acciones `_action_*` por cada frase UX** — eso es `meta`.
7. **No bypass de `gateway.py`** para procesar mensajes WhatsApp.

---

## Riesgos de Escalabilidad

### R1. Múltiples negocios con flujos distintos
**Qué rompe**: Un solo JSON; el segundo vertical fuerza fork del repo o condicionales en motor.  
**Señal**: Cliente pide flujo sin reservas o con pasos extra.

### R2. Múltiples workers / instancias API
**Qué rompe**: `StateManager` en JSON local no se comparte; usuarios saltan de paso entre workers. WS sin Redis no fan-out entre procesos.  
**Señal**: Load balancer con >1 réplica.

### R3. Volumen de conversaciones simultáneas
**Qué rompe**: Lock global en `StateManager`; rebuild de `OrderParser` por mensaje (CPU).  
**Señal**: Latencia webhook > Twilio timeout.

### R4. Crecimiento del catálogo de acciones
**Qué rompe**: `FlowEngine` monolítico; cada acción aumenta acoplamiento y superficie de test.  
**Señal**: >20 acciones o acciones por tenant.

### R5. Edición de config desde app sin validación
**Qué rompe**: Intents/prompts inválidos en BD sin equivalente a `validate_flow.py`.  
**Señal**: API PATCH de intents sin schema.

### R6. Onboarding masivo de tenants
**Qué rompe**: Semilla desde `config/*` identical para todos; diferenciación solo menú/prompts, no flujo.  
**Señal**: Franquicias con procesos conversacionales distintos.

### R7. Dependencia admin WhatsApp global
**Qué rompe**: Segundo restaurante no recibe alertas admin correctas en canal legacy.  
**Señal**: Multi-negocio en producción usando confirmación WA.

---

## Apéndice: Checklist para cambios

### Cambio solo de copy o rutas (mismo restaurante)
- [ ] Editar `flows/restaurant_flow.json`
- [ ] `python scripts/validate_flow.py`
- [ ] Probar camino feliz + abandon + cancelar
- [ ] Reiniciar bot / worker

### Nueva acción conversacional
- [ ] Implementar `_action_*` delgada (orquestación)
- [ ] Lógica en Service existente o nuevo en `services/`
- [ ] Registrar en `_actions` + `ACTION_OUTCOMES`
- [ ] Nodos JSON con `transitions` completos
- [ ] Tests de transición

### Nuevo tenant
- [ ] `scripts/onboard_business.py` o API superadmin
- [ ] Twilio `To` apunta a `twilio_whatsapp_from` del negocio
- [ ] Menú + intents + prompts en BD
- [ ] Verificar `business_scope` en webhook (automático)
- [ ] No tocar `FlowEngine`

### Cambio en API REST
- [ ] Filtrar por `business_id` del JWT
- [ ] No duplicar lógica del parser/flow en routes

---

*Documento generado por auditoría arquitectónica del repositorio WhatsBot. Refleja el estado del código y la migración JSON Fase 1–4. Revisar cuando se implemente flujo por tenant o registro extensible de acciones.*
