# Guía incremental — registro por fase

> Una nota breve al cerrar cada fase. El bot en **raíz** no debe regresar hasta validar.

## Directriz — tests incrementales por incidencia

**Alcance:** solo cuenta lo que **tú pidas o reportes** explícitamente (bug, comportamiento nuevo, incidencia concreta). No se añaden tests ni notas aquí por hallazgos del agente, refactors internos ni mejoras no solicitadas.

Cada incidencia que **tú indiques** debe quedar **protegida por un test** antes de darla por cerrada. Los tests se van **añadiendo de forma incremental**; en cada corrida, `flutter test` y `pytest` ejecutan **toda** la suite acumulada, de modo que lo que ya pediste y arreglaste no regrese.

| Ámbito | Dónde añadir el test | Validar |
|--------|----------------------|---------|
| App Flutter | `whatsbot_app/test/` (p. ej. `test/screens/`, `test/repositories/`, `test/sync/`) | `cd whatsbot_app && flutter test` |
| Backend Python | `tests/test_*.py` | `python -m pytest tests/ -v` |

**Reglas al agregar una incidencia (solo si la pediste tú):**

1. **Escribir el test** que falle sin el fix y pase con él (reproduce el comportamiento que pediste).
2. **No borrar tests** al refactorizar salvo que el comportamiento deje de existir; si cambia la spec, actualizar el test.
3. **Nombrar el test** describiendo el comportamiento, no el bug: p. ej. `ChatScreen reordena al recibir message.new deduplicado (v1.18)`.
4. **Anotar aquí** (en la sección de la fase o versión correspondiente) qué test cubre la incidencia que pediste y el comando de validación.
5. **Un test por incidencia** que hayas reportado; agrupar en el archivo del módulo/pantalla, sin duplicar casos.

**Ubicación habitual (Flutter):**

| Archivo | Qué protege |
|---------|-------------|
| `test/screens/chat_screen_test.dart` | Apertura, scroll, mensajes en vivo, envío optimista, capitalización |
| `test/screens/chats_list_screen_test.dart` | Orden, reorden al enviar/recibir, caché, errores de refresh |
| `test/repositories/*` | SQLite, cola offline, deduplicación |
| `test/sync/sync_engine_test.dart` | Eventos WS → persistencia y preview de conversación |
| `test/models/message_test.dart` | Orden cronológico estable (`compareChronological`) |

Al cerrar una incidencia **que pediste**: fix mínimo + test nuevo + nota breve en esta guía. Criterio: la suite completa en verde (`flutter analyze` sin issues).

---

## Fase 0 — Análisis ✅

- Inventario completo del bot en raíz.
- Mapa de credenciales legacy → `final_system/.env`.
- Diagramas flujo cliente + admin.
- **Sin código** en `final_system/`.

## Fase 1 — Scaffold ✅

**Hecho:**

- Árbol `final_system/` según prompt maestro.
- `config/settings.py`, `bot_config.py`, `intents.py`, `prompts.py`, `sheets_config.py` (con GUÍA RÁPIDA).
- `.env.example` con todas las variables del mapa Fase 0.
- `.env` con valores **copiados** del bot en raíz (Twilio, Admin, Sheets, cachés, JWT desde `SECRET_KEY`).
- `credentials/google-service-account.json` copiado desde raíz.
- `docs/ARCHITECTURE.md`, `INCREMENTAL_GUIDE.md` (este archivo).
- `requirements.txt`, `.gitignore`, `README.md`.
- `whatsbot_app/README.md` — placeholder Fase 9.
- Stubs en `api/`, `services/`, `models/`, `infrastructure/`, `scripts/`, `tests/`, `chatbot/`.

**No hecho (intencional):**

- Copiar chatbot / `gateway.py` → Fase 2.
- FastAPI webhook operativo → Fase 4.
- PostgreSQL migraciones → Fase 5.
- Flutter UI → Fase 9.

**Validación:** el bot en raíz (`python run.py`) sigue sin cambios.

**Variables migradas (nombres):** ver lista en `README.md` sección “Variables migradas”.

---

## Fase 2 — Gateway ✅

- [x] Copiar `app/` → `final_system/chatbot/app/` (raíz intacta)
- [x] `chatbot/gateway.py` → `handle_incoming_message()` (misma lógica que `POST /bot`)
- [x] `business_id` opcional en payload (passthrough)
- [x] `chatbot/runtime.py` — singleton servicios
- [x] `scripts/validate_chatbot.py`
- [x] Rutas `DATA_DIR` / `FLOWS_PATH` / `REPO_ROOT` apuntan solo a `final_system/`

**Validar:** `python scripts/validate_chatbot.py` desde `final_system/`.

---

## Fase 3 — Config ✅

- [x] Secrets y URLs solo en `final_system/.env` (sin sobrescribir valores Fase 1)
- [x] `config/settings.py` — Twilio, admin, JWT, paths, API
- [x] `config/sheets_config.py` — Sheets TTL, credenciales (alias legacy)
- [x] `config/bot_config.py` — FLOWS_PATH, NAV_HINT, branding
- [x] `config/intents.py` — GLOBAL_COMMAND_INTENTS + GREETING_PHRASES (parser legacy)
- [x] `config/prompts.py` — 21 textos desde `flows/restaurant_flow.json` + gateway
- [x] `chatbot/app/config.py` — shim hacia `config/*`
- [x] `validate_chatbot.py` → 0 fallos

---

## Fase 4 — API webhook ✅

- [x] `api/main.py` (FastAPI + CORS + `/health`)
- [x] `api/routes/whatsapp.py` → gateway + persistencia BD
- [x] `infrastructure/twilio_client.py` (TwiML + REST)
- [x] `models/conversation.py`, `models/message.py`
- [x] `services/conversation_service.py` (incoming + outgoing)
- [x] `scripts/migrate_db.py`, `scripts/validate_api.py`
- [x] `validate_chatbot.py` → 0 fallos

**Arranque:** `cd final_system && python -m api.main`  
**Webhook Twilio:** `{API_PUBLIC_URL}/webhook` (o `/bot`)

---

## Fase 5 — Multi-negocio ✅

- [x] Models: `business`, `business_intents`, `business_prompts`, `menu`, `order`, `customer`
- [x] Services: `business_service`, `menu_service`, `order_service`
- [x] API: `/businesses`, `/businesses/{id}/menu`, `/businesses/{id}/orders`
- [x] Webhook: `To` (Twilio) → `business_id` vía `twilio_whatsapp_from`
- [x] Negocio `default` sembrado desde `.env` + `config/intents` + `config/prompts`
- [x] `scripts/migrate_db.py`, `scripts/onboard_business.py`
- [x] `validate_chatbot.py` → 0 fallos

---

## Fase 6 — Pedidos + admin ✅

- [x] `services/notification_service.py` — fachada sobre `AdminService` legacy (notify, confirm, espejo BD)
- [x] `flow_engine` → `on_order_pending()` tras pedido pendiente
- [x] `gateway.py` — admin vía `notification_service` (mismo flujo: cliente → admin → CONFIRMAR → cliente)
- [x] `tests/test_order_confirmation_flow.py` — 3 tests OK
- [x] `validate_chatbot.py` → 0 fallos

```bash
python -m pytest tests/test_order_confirmation_flow.py -v
python scripts/validate_chatbot.py
```

---

## Fase 7 — API WhatsBot ✅

- [x] `api/routes/auth.py` — `POST /auth/login` (JWT + `business_id`)
- [x] `api/middleware/auth.py` — Bearer obligatorio en `/whatsbot/*`
- [x] `api/routes/whatsbot.py` — chats, mensajes, pedidos, menú/intents/prompts por negocio
- [x] `chatbot/gateway.py` + `business_context.py` — menú/intents/prompts desde BD (fallback `config/*`)
- [x] CORS ya en `api/main.py` (`CORS_ORIGINS`)
- [x] `tests/test_whatsbot_api.py` — PUT menu/intents/prompts + gateway BD
- [x] `docs/FLUTTER_APP.md`, `docs/GUIA_EDICION_APP.md` (borradores)

```bash
cd final_system
python -m pytest tests/test_whatsbot_api.py -v
python scripts/validate_chatbot.py
```

Variable nueva: `WHATSBOT_OWNER_PIN` (login app; no exponer en chat).

---

## Fase 8 — Google Sheets opcional ✅

- [x] `services/sheets_sync_service.py` — espejo BD→Sheets; `GOOGLE_SHEETS_ENABLED=false` por defecto
- [x] `api/routes/sheets.py` — status, settings, sync (JWT)
- [x] `GoogleSheetsClient.replace_menu_mirror` / `upsert_order_mirror` (legacy extendido)
- [x] Hooks no bloqueantes: PUT menú app + pedido en BD
- [x] `tests/test_sheets_api.py`
- [x] `validate_chatbot.py` → 0 fallos

```bash
cd final_system
python -m pytest tests/test_sheets_api.py -v
python scripts/validate_chatbot.py
```

Con Sheets apagado el sistema funciona igual (PostgreSQL + chatbot con caché/demo).

---

## Fase 9 — Flutter WhatsBot ✅

- [x] `whatsbot_app/` — proyecto Flutter Android/iOS (sin Flutter Web como producto)
- [x] UI tipo WhatsApp: header `#075E54`, chat `#ECE5DD`, burbujas `#DCF8C6` / blanco
- [x] Pantallas: login, chats, chat, order approve/reject, ajustes
- [x] Editores: menú, intents, mensajes (`GET/PUT /whatsbot/business/*`)
- [x] `lib/services/api_client.dart` + `lib/config/api_config.dart` (`API_PUBLIC_URL` del `.env`)
- [x] Polling chat 4 s / lista 8 s
- [x] `docs/FLUTTER_APP.md`, `docs/GUIA_EDICION_APP.md` completos

```bash
cd final_system/whatsbot_app
flutter pub get
flutter analyze
# No issues found!
```

Prueba manual: login → chat → enviar → aprobar pedido; Menú → guardar; Mensajes → bienvenida → guardar.

---

## Fase 10 — Validación + documentación ✅

**Hecho:**

- [x] `scripts/validate_system.py` — gateway + API + flujo pedido + edición BD
- [x] `validate_chatbot.py`, `validate_api.py`, `validate_system.py` → 0 fallos
- [x] `pytest tests/` → 15 passed
- [x] `README.md` completo (guía 15 líneas, credenciales, backend, Flutter, E2E)
- [x] `docs/GUIA_NEGOCIOS.md` — alta de negocio paso a paso
- [x] `docs/GUIA_EDICION_APP.md` — dueño edita menú/intents/mensajes solo desde app
- [x] `docs/INCREMENTAL_GUIDE.md` (este archivo)
- [x] `docs/FLUTTER_APP.md` — app documentada
- [x] API arranca con `DATABASE_URL=sqlite:///data/whatsbot.db` (dev local sin PostgreSQL)
- [x] `flutter analyze` → No issues found

**Checklist E2E (prompt maestro):**

| Ítem | Automatizado | Manual (Twilio real) |
|------|--------------|----------------------|
| Cliente → bot responde | `validate_system` gateway | Probar WhatsApp |
| Mensaje en app Flutter | webhook + `/whatsbot/conversations` | `flutter run` |
| Dueño responde desde app | API `/whatsbot/messages` | App + teléfono |
| Pedido → admin legacy | `validate_system` notify | ADMIN_WHATSAPP |
| Aprobar desde Flutter | `validate_system` approve | App |
| Aprobar desde ADMIN | `test_order_confirmation_flow` | WhatsApp admin |
| Sheets deshabilitado OK | `test_sheets_api` | — |
| Editar menú en app | `validate_system` menu BD | App → Menú |
| Editar intent en app | `test_whatsbot_api` intents | App → Intents |
| Editar bienvenida/mensajes | `validate_system` prompts BD | App → Mensajes |

```bash
cd final_system
python scripts/validate_chatbot.py
python scripts/validate_api.py
python scripts/validate_system.py
python -m pytest tests/ -v
cd whatsbot_app && flutter analyze
python -m api.main   # con .env y migrate_db
```

**Métrica de éxito:** junior arranca API + app con README, ve chats, responde, confirma pedidos, da de alta negocio y edita bot solo desde Flutter — sin UI web.

---

## Mejora incremental — Alertas tipo WhatsApp ✅

**Hecho (solo Flutter `whatsbot_app/`):**

- [x] `lib/services/message_alerts_service.dart` — sonido + vibración + notificaciones locales al llegar mensajes entrantes
- [x] Sonido corto en primer plano (`audioplayers`) y en canal Android (`res/raw/incoming_message.wav`)
- [x] Notificación del sistema si la app está en segundo plano o en otro chat (como WhatsApp)
- [x] Sin banner si el dueño ya está viendo ese chat; con sonido igualmente
- [x] Lista de chats: preview en negrita, hora verde y punto de no leído
- [x] Tap en notificación abre el chat correspondiente
- [x] Permisos Android `POST_NOTIFICATIONS` + `VIBRATE`; iOS delegado en `AppDelegate`

```bash
cd final_system/whatsbot_app
flutter pub get
flutter analyze
cd ..
python scripts/validate_chatbot.py
```

**Probar:** login → dejar app abierta en lista de chats → enviar WhatsApp al bot → suena y aparece notificación; abrir el chat → nuevo mensaje suena sin banner; minimizar app → notificación en bandeja del sistema.

---

## Fase 11.2 — Backend WebSocket + eventos BD ✅

**Hecho:**

- [x] `services/realtime_service.py` — hub in-memory por `business_id`; eventos `message.new`, `conversation.updated`, `ping`/`pong`
- [x] `api/routes/realtime.py` — `WS /whatsbot/ws?token=<JWT>`
- [x] Emisión tras commit en `api/routes/whatsapp.py` (incoming/outgoing bot) y `api/routes/whatsbot.py` (mensaje dueño)
- [x] REST incremental: `GET /whatsbot/conversations?since=ISO8601`, `GET .../messages?after_id=N`
- [x] `REALTIME_ENABLED`, `WS_HEARTBEAT_SECONDS` en `config/settings.py` y `.env.example`
- [x] `tests/test_realtime_ws.py` — auth WS, broadcast, webhook, filtros sync

```bash
cd final_system
python -m pytest tests/test_realtime_ws.py -v
python scripts/validate_chatbot.py
```

**Pendiente (11.3+):** Flutter `RealtimeService`, FCM, estados mensaje, quitar polling.

**Probar WS manual:** login → token → conectar `wss://{API}/whatsbot/ws?token=...` → enviar mensaje al bot → recibir `message.new`.

---

## Fase 11.3 — Flutter WebSocket + quitar polling ✅

**Hecho:**

- [x] `lib/services/realtime_service.dart` — WS autenticado, backoff 1→30 s, ping/pong, sync al reconectar
- [x] `lib/models/realtime_event.dart`
- [x] `api_client.dart` — `getConversations(since:)`, `getMessages(afterId:)`, `accessToken`
- [x] `chats_list_screen.dart` / `chat_screen.dart` — eventos live; fallback REST 30 s si WS cae
- [x] Login, splash y logout conectan/desconectan WS
- [x] `message_alerts_service.dart` — alertas desde evento `message.new`
- [x] Dependencia `web_socket_channel`

```bash
cd final_system/whatsbot_app
flutter pub get
flutter analyze
```

**Pendiente (11.4+):** FCM push, ticks de estado, pedidos live sin polling REST.

**Probar:** login → lista de chats → cliente escribe al bot → mensaje aparece al instante (sin esperar 4 s); icono nube si WS desconectado.

---

## Fase 11.4 — Push FCM/APNs ✅

**Hecho:**

- [x] `models/device_token.py` + `services/device_token_service.py`
- [x] `services/push_service.py` — Firebase Admin SDK; push si `ws_delivered == 0` y mensaje entrante
- [x] `POST/DELETE /whatsbot/device-token`
- [x] `FCM_ENABLED`, `FCM_SERVICE_ACCOUNT_JSON_PATH` en settings y `.env.example`
- [x] Flutter `lib/services/push_service.dart` — registro token, tap → chat, fallback si sin Firebase
- [x] `tests/test_push_api.py`
- [x] Guía Firebase en `docs/FLUTTER_APP.md`

```bash
cd final_system
pip install -r requirements.txt
python -m pytest tests/test_push_api.py -v
cd whatsbot_app && flutter pub get && flutter analyze
```

**Pendiente (11.5+):** ticks de estado, pedidos live, validación E2E ampliada.

**Probar push:** `FCM_ENABLED=true` + JSON servicio → login en app con `google-services.json` → cerrar app → cliente escribe → notificación del sistema → tap abre chat.

---

## Fase 11.5 — Estados mensaje + ticks + pedidos live ✅

**Hecho:**

- [x] `messages.status`, `delivered_at`, `read_at` + `scripts/migrate_message_status.py`
- [x] `POST /whatsbot/conversations/{id}/mark-read` + eventos `message.status`
- [x] Ticks en burbujas salientes (`message_status_ticks.dart`)
- [x] Eventos `order.pending` / `order.updated` (webhook pedido + approve/reject)
- [x] Flutter: pedidos live sin polling REST; typing indicator v1
- [x] `tests/test_message_status.py`

```bash
cd final_system
python scripts/migrate_message_status.py
python -m pytest tests/test_message_status.py -v
cd whatsbot_app && flutter analyze
```

**Pendiente (11.6):** validación E2E ampliada, `validate_system.py`, README tiempo real.

---

## Fase 11.6 — Validación E2E ✅

**Hecho:**

- [x] `scripts/validate_system.py` — WS connect, ping/pong, `message.new`, device-token, mark-read, `?since=`
- [x] Migración status en validate setup
- [x] `README.md` — sección tiempo real + checklist Fase 11
- [x] `docs/ARCHITECTURE.md` — diagrama WS + FCM
- [x] API `0.9.0`; 29 tests pytest; `flutter analyze` limpio

```bash
cd final_system
python scripts/migrate_message_status.py
python scripts/validate_system.py
python -m pytest tests/ -q
cd whatsbot_app && flutter analyze
```

**Fase 11 cerrada.** Próximo trabajo fuera de alcance: Redis pub/sub multi-instancia, read receipts Twilio, typing desde cliente WA.

---

## Mejoras UX chat (post-Fase 11) ✅

**Hecho:**

- [x] Aprobar pedido desde app: verifica Twilio, persiste confirmación en chat y emite `message.new`
- [x] Burbujas: respuestas del bot con etiqueta «WhatsBot»; mensajes del dueño sin marca
- [x] Lista de chats: reorden al instante vía WS (`message.new`) sin depender solo del polling
- [x] Al abrir chat: posición final instantánea (`jumpTo` sin animación; lista oculta hasta sync inicial)
- [x] Leído/no leído: `seenAt` alineado al último mensaje al salir del chat (incluye salientes)

```bash
cd final_system
python -m pytest tests/test_order_confirmation_flow.py -v
python scripts/validate_chatbot.py
cd whatsbot_app && flutter analyze
```

---

## Offline-first WhatsBot (OF-A — OF-E) ✅

### OF-A — Cache local + carga instantánea ✅

- [x] Drift SQLite: `conversations`, `messages`, `sync_cursors`
- [x] `ChatRepository`, `MessageRepository`, `AppServices`
- [x] UI lee streams locales; HTTP hidrata en background

### OF-B — Sync incremental + WS→DB + dedup ✅

- [x] `SyncEngine` centraliza REST + eventos WS → SQLite
- [x] Dedup en upsert; retención 500 msgs/chat
- [x] `RealtimeService.persistEvent` escribe antes de emitir a UI

### OF-C — Cola saliente offline ✅

- [x] Tabla `outbound_queue`; mensajes optimistas (`status: pending`)
- [x] `flushOutboundQueue` al reconectar / volver online
- [x] API: `client_id` opcional + `scripts/migrate_client_id.py`

### OF-D — connectivity_plus + sin polling ✅

- [x] `connectivity_service.dart` reemplaza polling 30 s
- [x] Sync al detectar red; icono nube si offline o WS caído

### OF-E — Tests + docs + cierre ✅

- [x] `flutter test` — repositorios, sync engine, smoke UI
- [x] `docs/FLUTTER_APP.md`, `ARCHITECTURE.md` actualizados
- [x] Checklist manual offline documentado

```bash
cd final_system
python scripts/migrate_client_id.py
python -m pytest tests/test_whatsbot_api.py -v
cd whatsbot_app
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
```

**Fases offline-first cerradas.** Pedidos offline (aprobar/rechazar sin red) quedan fuera de alcance.

**Nota (2026-06):** `test/helpers/test_app_services.dart` cablea `AppServices` en memoria (DB + `TestApiClient`) porque `AppServices` no expone `initForTesting`/`resetForTesting`.

---

## Chat: apertura sin scroll visible ✅

- `chat_screen.dart`: fase `_openingConversation` oculta la lista (`Opacity: 0`) hasta el `jumpTo` final tras sync/cache.
- Solo `animateTo` cuando el chat ya está abierto y el usuario está al fondo (mensaje nuevo o envío).
- Evita el desplazamiento visible al cargar historial incremental desde SQLite + red.

---

## Chat: apertura instantánea desde caché (comportamiento WhatsApp) ✅

- `chat_screen.dart`: mensajes visibles al instante desde `watchMessages` (SQLite); sin `Opacity: 0` ni spinner si hay caché.
- `jumpTo` al fondo en el primer frame (`_needsInitialScroll`); sync de red en background sin bloquear UI.
- Spinner solo si `messages.isEmpty` y no hay datos locales (primera apertura).
- `SyncEngine.syncMessagesIncremental`: guard con TTL 2 min + cursor (`needsSyncFromApi`); `force: true` al reconectar.
- Reabrir conversación visitada: sin loading ni re-sync innecesario; actualización solo si hay delta real (WS o TTL).

---

## Chat: apertura fluida sin saltos (reverse ListView) ✅

- `chat_screen.dart`: `ListView.builder(reverse: true)` — offset 0 = último mensaje visible en el primer frame, sin `jumpTo`/`animateTo` en apertura.
- Índice 0 = mensaje más reciente; `TypingIndicator` en i==0 (extremo inferior).
- Eliminados `_needsInitialScroll`, `_positionAtBottom` y `addPostFrameCallback` de scroll dentro del `StreamBuilder`.
- Scroll animado solo vía `_onMessagesUpdated` (listener del stream) si hay mensaje nuevo y `_isNearBottom()`.
- `chats_list_screen.dart`: precarga SQLite (`getCachedMessages`) antes del `push`; `initialData` en `StreamBuilder`.
- `initState`: sync/mark-read diferidos con `scheduleFrameCallback` (no bloquean el primer paint).

---

## Chat: mensajes entrantes visibles + capitalización al escribir (v1.17) ✅

- `chat_screen.dart`: lista `_displayMessages` + `setState` en el watch Drift (sin depender solo de `StreamBuilder`).
- `message.new`: merge inmediato del payload WS en pantalla (antes de depender solo de SQLite).
- `conversation.updated` / apertura: si el preview de la conversación es más reciente que el último mensaje local, `refreshFromApi(incremental: true)` sin pasar por el TTL del `SyncEngine`.
- `TextField`: `textCapitalization: TextCapitalization.sentences`.

---

## Chat: mensajes enviados visibles + orden tipo WhatsApp (v1.24) ✅

- `chat_screen.dart`: merge por `clientUuid` al confirmar envío; reconciliación SQLite para no perder optimistas; lectura inmediata de caché tras enviar; scroll al primer mensaje.
- `chats_list_screen.dart`: eventos `message.new` salientes fuerzan rebuild (el bump ya lo hace `sync_engine` vía Drift).

**Validar:** abrir chat → enviar → la burbuja aparece al instante y persiste; volver a la lista → ese chat arriba; mensaje entrante también sube al tope.

```bash
cd whatsbot_app && flutter test && flutter analyze
```

---

## Chat: preview al enviar + orden al recibir (v1.19) ✅

- `chat_repository.dart`: `mergeWithLocal` no sobrescribe preview local si el servidor trae el mismo `lastMessageAt`; `upsertConversations` usa merge por ítem (no pisa envíos optimistas).
- `message_repository.dart`: `_bumpConversation` siempre actualiza preview en mensajes salientes del dueño.
- `sync_engine.dart`: `message.new` sube la conversación aunque no exista aún en SQLite (sync + bump) y fusiona metadata WS con caché local.
- `chats_list_screen.dart`: `await Navigator.push` al abrir chat y refresh al volver (preview actualizado tras enviar).

**Validar:** abrir chat → enviar → volver a la lista: preview y chat al tope; mensaje entrante también sube al tope.

```bash
cd whatsbot_app && flutter test && flutter analyze
```

---

## Chat: orden cronológico + lista al recibir (v1.18) ✅

- `message_dao.dart` / `ChatMessage.compareChronological`: orden estable por `createdAt` + `id`.
- `sync_engine.dart`: `message.new` siempre actualiza la conversación (aunque el mensaje esté deduplicado).
- `chat_repository.dart`: `mergeWithLocal` — no retrocede `lastMessageAt` con datos viejos del servidor.
- `message_repository.dart`: al sincronizar mensajes por REST, sube el preview/timestamp de la conversación.
- `conversation_service.py`: historial API ordenado por `created_at, id`.

**Validar:** mensajes del dueño, del bot y del cliente intercalados en orden; chat sube al tope al recibir igual que al enviar.

```bash
cd whatsbot_app && flutter test && flutter analyze
```

---

## Chat: REST fallback con WS caído (FIX TTL) ✅

- `sync_engine.dart`: `syncMessagesIncremental` omite TTL si `force: true` o `RealtimeService.isConnected == false`.
- `chat_screen.dart`: sync inmediato al abrir con WS↓; timer REST ~30 s solo con chat abierto + WS↓ + online; refresh force al pasar connected→disconnected.
- Sin polling en lista cuando WS está OK.

**Tests:** `test/sync/sync_engine_test.dart` (TTL con WS↑/↓); `test/screens/chat_screen_test.dart` (`ChatScreen con WS caído trae mensaje nuevo vía REST sin reabrir`).

```bash
cd whatsbot_app && flutter analyze && flutter test
```

**Probar manual:** login → abrir chat con icono nube → cliente escribe → burbuja en ≤30 s sin salir; con WS conectado el mensaje llega al instante.

---

## Chat: WS conectado — mensaje visible en lista y chat (FIX 1b) ✅

- **Causa raíz:** `resolveForLocalStore` priorizaba `conversation_id` del servidor sobre el hilo local por `wa_id`; bump y UI apuntaban al hilo equivocado.
- `message_repository.dart`: `resolveForLocalStore` enlaza por `wa_id` antes que id servidor.
- `sync_engine.dart`: `_handleMessageNew` persiste y hace bump con mensaje ya resuelto al hilo local.
- `chat_screen.dart`: merge inmediato del payload WS en `_displayMessages` (v1.17).
- `chats_list_screen.dart`: bump de preview por `wa_id` al recibir `message.new`.

**Tests:** `message_repository_test` (wa_id); `sync_engine_test` (persist en hilo local); `chat_screen_test` y `chats_list_screen_test` (conversation_id servidor distinto).

```bash
cd whatsbot_app && flutter analyze && flutter test
```

**Probar manual:** WS conectado → cliente escribe → burbuja <1 s en chat abierto; preview y orden en lista; al abrir chat el mensaje ya está.

---

## Chat: mensajes en vivo con chat abierto (FIX UI reactiva) ✅

- **Causa raíz:** `_refresh` sincronizaba SQLite pero no reconciliaba `_displayMessages`; si el watch Drift o el merge WS fallaban, la UI quedaba congelada en el snapshot de apertura hasta salir y reentrar.
- `chat_screen.dart`: `_applyStoreSnapshot` / `_reloadDisplayFromStore` — red de seguridad tras `_refresh` y `_send`; `message.new` resuelve hilo local vía `resolveForLocalStore` antes del merge; `_sameWa` compara solo dígitos (`35699155990` vs `+356…`).

**Tests:** `test/screens/chat_screen_test.dart` — `wa_id sin + y caché precargada`; `reconcilia tras refresh cuando llegan mensajes vía REST`.

```bash
cd whatsbot_app && flutter test test/screens/chat_screen_test.dart && flutter analyze
```

**Probar manual:** abrir chat Omar (`35699155990`) → cliente escribe / bot responde / admin envía → burbuja al instante sin salir del chat.
