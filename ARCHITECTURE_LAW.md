# ARCHITECTURE_LAW.md

Ley de arquitectura vigente (incremental).

```text
v1 = ARCHITECTURE_LAW.md (base; no editar en tareas normales)
v2 = transport WhatsApp agregado
v3 = v1+v2 compactados; misma sustancia; sin scripts de selfcheck en la ley
```

Si hay conflicto entre versiones, prevalece la decision central de capas. Este archivo no reemplaza v1 como historico; es el contrato a obedecer cuando se cite v3.

```text
JSON = mapa conversacional
Python = motor de ejecucion
Services = negocio
StateManager = estado conversacional
business_scope = aislamiento multi-tenant
Transport = entrega WhatsApp (no mapa, no negocio)
```

## Politica de solo lectura

Contrato de solo lectura para implementacion normal. Se lee y se obedece; no se edita para acomodar feature, bugfix, refactor, tests o flujo.

```text
ARCHITECTURE_LAW.md / architecture_law_v2.md / architecture_law_v3.md
se leen; no se modifican salvo solicitud explicita del usuario.
```

Autorizacion explicita tipica: "modifica/actualiza la ley de arquitectura", "cambia las reglas", "propongo cambiar la arquitectura", "revisa y mejora ARCHITECTURE_LAW…".

Misma regla para **tests existentes**: no modificarlos en tareas normales. Solo si el usuario pide explicitamente modificar/actualizar tests, agregar tests, o corregir tests rotos. Si el codigo nuevo rompe tests, se corrige el codigo — no el contrato de tests.

Si una tarea exige violar esta ley: detenerse y explicar (1) regla rota, (2) por que, (3) alternativa que la preserve, (4) decision arquitectonica necesaria si no hay alternativa. No editar la ley para hacer pasar el cambio.

## Decision central

```text
Twilio -> FastAPI webhook -> gateway.py -> business_scope
  -> FlowEngine -> StateManager -> Services -> DB
```

Outbound:

```text
gateway (respuesta + actions/list del JSON)
  -> API webhook -> infrastructure/twilio_client (transport)
  -> Twilio Content / Messages
```

```text
El flujo se configura.
El motor orquesta.
El estado lo administra StateManager.
El negocio vive en Services.
El tenant siempre viene por business_scope.
El transport solo entrega; no resuelve destinos de flujo.
```

## Invariantes

No son preferencias.

### 1. JSON = mapa

Define: estados, nodos, opciones, transiciones, comandos globales, mensajes, fallbacks, outcomes, y UI declarativa (`buttons` / `list` / `options`).

Python no duplica ese mapa.

**Prohibido:** rutas hardcodeadas; `if step == "..."`; transiciones duplicadas fuera del JSON; segundo mapa en config/BD/codigo; `GLOBAL_COMMAND_ROUTES` como routing runtime paralelo; inventar botones/ids/destinos en Python "para arreglar" WhatsApp.

**Permitido:** cargar/validar/resolver JSON; ejecutar acciones y templates declarados; adaptar presentacion de transport (p. ej. strip emoji leading en titles al enviar) **sin** cambiar ids ni destinos del JSON.

### 2. Python = motor

`FlowEngine` orquesta; no es negocio.

**Debe:** leer estado/nodo; ejecutar accion; recibir `(mensaje, outcome)`; resolver transicion JSON; componer respuesta; exponer `buttons`/`list` del nodo al gateway sin reinterpretar el mapa.

**No debe:** reglas por tenant; negocio profundo; BD directa / modelos/sesiones; copy largo de UX; casos especiales por nodo; logica Twilio Content SID, cache HX, anti-stack o probe.

### 3. Acciones delgadas

`_action_*` solo orquesta: leer StateManager, llamar Service, guardar datos conversacionales, devolver `(mensaje, outcome)`.

**No:** calculos/persistencia/validaciones de dominio complejas (van a Services); rutas nuevas fuera del JSON.

### 4. Services = negocio

Pedidos, menu, reservas, usuarios, clientes, admin, notificaciones, persistencia, validaciones de dominio. Capacidad de negocio nueva → Services (o dominio equivalente), no el motor.

### 5. StateManager = estado conversacional

Solo StateManager muta: `flow`, `step`, `data`, carrito/reserva temporal, flags, confirmaciones pendientes. Datos duraderos → BD via Services.

**Prohibido:** mutar `state["step"|"flow"|"data"]` fuera de StateManager.

### 6. Multi-tenant siempre

Datos de negocio bajo `business_scope` o `business_id` explicito y validado.

**Prohibido:** asumir un solo restaurante; `if business_id == "..."`; comportamiento especial por tenant en FlowEngine; config global si existe por tenant; menu/prompts/intents/admin/pedidos sin contexto de negocio; hardcodear un solo sender/tenant en transport.

Flujo distinto por tenant → configuracion de flujo por tenant, no ifs en el motor.

**Transport multi-tenant:** anti-stack quick-reply por digitos de `to`; cache HX por fingerprint + namespace `TWILIO_ACCOUNT_SID`; From pinneado al sender del negocio / env — no phantom `+1555`.

### 7. Gateway unico

Todo WhatsApp inbound pasa por `gateway.py`.

**API puede:** webhook, resolver tenant, auditoria, llamar gateway, responder via transport, loguear campos Twilio de interactive.

**API no:** parser/motor propios; mutar estado conversacional; decidir rutas; saltar bloqueos admin/cliente.

Gateway prefiere `ButtonPayload` / list reply sobre `Body` cuando existan; pasa ese input al motor sin inventar rutas.

### 8. Una fuente de verdad por responsabilidad

| Responsabilidad | Fuente |
|-----------------|--------|
| Navegacion | JSON |
| Comandos globales runtime | `meta.global_commands` |
| Copy de flujo | JSON |
| Copy configurable gateway | BD |
| `config/*` | semillas; no runtime si ya hay BD |
| UI interactive (`buttons`/`list`) | JSON |
| Higiene entrega WhatsApp (HX, probe, anti-stack, shape) | `infrastructure/twilio_client.py` |

No duplicar la misma decision en dos sitios.

### 9. Incrementos solo en la capa correcta

Mejora incremental = comportamiento en la capa correcta. No editar esta ley ni tests existentes salvo autorizacion explicita. Tests = contrato, no material de ajuste.

**Validos:** helper Service; parser sin cambiar routing; endpoint con `business_id`; validacion/campo BD en Services; copy/transicion/accion delgada en JSON; higiene transport sin tocar mapa; tests solo si el usuario los pidio.

**Invalidos:** ruta por `if current_step`; tenant por `if business_id`; copy largo en FlowEngine; BD desde FlowEngine; estado sin StateManager; convertir `buttons`→list-picker en Python "porque fallan chips"; twin `twilio/text`+`twilio/quick-reply`; CREATE HX en cada send identico; destinos de flujo en `twilio_client`; ablandar/borrar assertions o fixtures para esconder regresion.

### 10. Deuda aceptada no crece

Deuda conocida: flujo JSON global; acciones restaurante-specific en FlowEngine; parser grande en `core`; admin WhatsApp legacy global; estado en archivo JSON local; prompts duplicados JSON/config/BD; nombres legacy (`restaurant`, `sheets`, `RESTAURANT_NAME`).

Al tocar deuda: reducirla, dejarla igual, o documentar por que no se puede reducir aun. Nunca ampliarla en silencio.

### 11. Transport WhatsApp entrega; no es mapa

Capa: `infrastructure/twilio_client.py` (+ webhook/gateway: entrega y logs).

**No reintroducir:** flood HX identicos; chips/burbujas viejas (✓✓ local sin inbound); twin text+quick-reply; cache→HX 404 sin probe; buttons→list-picker como atajo de UX.

**Reglas:**

1. JSON declara; transport entrega. `buttons`→`twilio/quick-reply`; `list`→`twilio/list-picker`. Ids/destinos del JSON. No inventar botones/rutas en Python.
2. Un tipo interactive por mensaje WhatsApp. Nodo con list+buttons → dos mensajes (list, luego buttons). No fusionar types en un Content.
3. Sin twin text: body dentro de `twilio/quick-reply`; no `twilio/text` en el mismo `types`.
4. Reuse HX por fingerprint (kind+body+actions + `TWILIO_ACCOUNT_SID`). No CREATE en cada hola identico.
5. Probe antes de reusar: GET; 404/error claro → drop cache + recreate. Nunca SID muerto.
6. Anti-stack: mismo quick-reply al mismo `to` (digitos) dentro de ~5 min → no reenviar.
7. Titles al enviar: se pueden simplificar (sin emoji leading). Ids ASCII del JSON intactos. JSON puede seguir con emoji.
8. From pinneado (`TWILIO_WHATSAPP_FROM` / sender negocio). No remap phantom `+1555`.
9. Cache `data/twilio_content_cache.json` (gitignored via `data/`). Tras purga Contents en Twilio: invalidar cache o confiar en probe. No borrar cache en cada `.\start` (recrea flood).
10. Logs (webhook y/o gateway): `Body`, `ButtonPayload`, `ButtonText`, `InteractiveData` (si/no), `MessageSid`. Sin `ButtonPayload` tras tap → fallo Meta/chip; no se "arregla" con rutas en FlowEngine.
11. Prueba: welcome fresco; tap mensaje mas nuevo. HX huerfanos al cambiar copy no se auto-borran; no rompen el tap del mensaje nuevo solos. Fallos de chips no justifican violar invariantes 1–8.

## Proceso obligatorio

**Antes:** (1) leer este archivo; (2) capas tocadas; (3) incremental vs arquitectonico; (4) si arquitectonico → aprobacion; (5) si tests → confirmacion explicita del usuario; (6) si buttons/list → cambio en transport o solo copy/ids en JSON, no rutas en motor.

**Despues:**

```bash
python scripts/validate_flow.py
python scripts/validate_architecture.py
pytest
```

Reportar fallos (comando, resultado, causa, correccion). No esconder. `validate_architecture.py` puede faltar: reportarlo, no inventar bypass.

Autorizacion de validador para editar ley/tests solo si el usuario lo pidio explicitamente.

## Checklist de revision

- Navegacion en JSON? Motor ≠ mapa? Negocio en Services? Estado solo via StateManager?
- Multi-tenant? Sin `if business_id == ...`? Sin rutas paralelas fuera del JSON?
- Sin copy largo de flujo en Python? `meta.global_commands`? Acciones delgadas? Outcomes con transiciones?
- Transport sin destinos de flujo? `buttons` = quick-reply (no list-picker en Python)?
- Sin twin `twilio/text`? HX reuse + probe? Anti-stack por destinatario si aplica?
- Tests intactos salvo pedido explicito? Validadores/tests ejecutados?

## Instruccion para asistentes AI / Cursor

1. No editar esta ley (ni v1/v2) salvo pedido explicito.
2. No editar tests existentes salvo pedido explicito.
3. No contradecir esta ley.
4. Ambiguo → opcion que preserve arquitectura.
5. Implementacion que rompe regla → detenerse y alternativa.
6. Tras cambios relevantes → validadores y tests; si no se pueden ejecutar, decirlo.
7. Chips/taps fantasma → transport + inbound primero; nunca atajo de mapa en FlowEngine.

Prompt recomendado:

```text
Antes de implementar, lee architecture_law_v3.md.
No modifiques ARCHITECTURE_LAW.md ni architecture_law_v3.md.
No modifiques tests existentes salvo que yo lo pida explicitamente.
Implementa respetando:
JSON = mapa (buttons/list/options),
Python = motor,
Services = negocio,
StateManager = estado,
business_scope = tenant,
Transport = entrega (quick-reply/list-picker, reuse HX, sin twin text).

Al final:
python scripts/validate_flow.py
python scripts/validate_architecture.py
pytest

Si una regla se rompe, no fuerces el cambio. Explica y propone alternativa.
```
