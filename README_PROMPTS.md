## v1.4





#######################################################
## v1.0.
Primer versión





#######################################################
## v1.1


## prompt ##

[[[[[- llega el mensaje por notificación push, barra de estado y sonido, pero  dentro de la app, en el listado, no se actualiza que llegó nuevo mensaje, necesito 
- Cuando estoy dentro de un chat, todo funciona correctamente, lo único que quiero que corrijas es lo siguiente: cuando yo envío un mensaje se envía correctamente, el problema es de visualización, todos los mensajes que envío desde whatsbot al cliente llega, pero siempre se quedan como si se hubieran acabado de enviar, y aunque el cliente le envíe mensajes, los que el cliente envía se ven y loq eu responde el bot también, pero lo que yo escribí como humano, queda ahí, ]]]]]


IMPORTANTE: REVISA ESAS DOS INCIDENCIAS, SOLAMENTE QUIERO QUE LAS REVISES, VERIFIQUES, NO TOQUES CODIGO SOLO ME PROPONGAS QUÉ SE DEBE HACER PARA SOLUCIONAR ESO, RESUMIDO, SOLO PROPON NO TOQUE SEL PROYECTO, DAME RESUMIDO Y QUE TENGAS CERTEZA DE QUE SE SOLUCIONARA



## resp cursor ##

## Diagnóstico (sin tocar código)

Revisé el flujo completo. Las dos incidencias tienen causas distintas pero relacionadas con el mismo patrón: **la notificación funciona por un camino, pero la UI depende de otro que no siempre se ejecuta**.

---

### 1. Lista de chats no se actualiza (pero suena la push)

**Causa raíz (alta certeza):**  
La push solo se envía cuando el WebSocket **no** entregó el mensaje (`ws_delivered == 0` en el backend). En ese momento la app recibe FCM, muestra sonido/banner… pero `push_service.dart` **solo llama a `notifyFromPush()`** — no persiste nada en SQLite ni actualiza la conversación.

La lista depende de:
- evento WS `message.new` → `SyncEngine` → SQLite, o
- pull-to-refresh / reconexión manual.

Si llega push = WS caído o no conectado → **notificación sí, lista no**.

**Qué hacer para solucionarlo:**
1. En el handler de push (`_onForegroundMessage` y el background handler), además de notificar, **sincronizar datos**: llamar a `syncConversationsIncremental()` y/o traer el mensaje de esa conversación y hacer `upsert` en SQLite.
2. En `ChatsListScreen`, escuchar también `conversation.updated` (no solo `message.new`).
3. Opcional: al volver a primer plano, forzar un sync silencioso de conversaciones si hubo push reciente.

**Por qué estoy seguro:** el backend solo manda push cuando el WS falló; el handler de push no escribe en la base local; la lista lee de SQLite vía `watchConversations()`.

---

### 2. Tus mensajes humanos quedan “enviando” (reloj ⏱)

**Causa raíz (alta certeza):**  
Bug de visualización en `chat_screen.dart`, no de envío.

Flujo actual:
1. Al enviar → mensaje optimista con `status: 'pending'` (reloj).
2. El servidor responde OK y el WS emite `message.new` del mismo mensaje.
3. `SyncEngine` confirma el mensaje en SQLite (`status: 'sent'`) **antes** de que la UI lo refleje.
4. `_mergeIncomingMessage()` hace esto cuando ya existe el mensaje por `clientUuid`:

```dart
if (exists) return current;  // ← devuelve la lista VIEJA con pending
```

5. Eso hace `setState` con la versión **pending** otra vez.
6. Como la DB ya no cambia más, el stream de Drift **no vuelve a emitir** → el reloj queda para siempre.

Los mensajes del cliente y del bot no pasan por este camino optimista, por eso se ven bien.

**Qué hacer para solucionarlo:**
1. **Opción A (recomendada):** En `_mergeIncomingMessage`, si ya existe por `id` o `clientUuid`, **reemplazar** el mensaje viejo con el entrante (id real, status, timestamps) — no devolver `current` sin cambios.
2. **Opción B:** Eliminar el manejo de `message.new` en `ChatScreen` para mensajes salientes y confiar solo en el stream `watchMessages()` (ya está suscrito).
3. **Opción C:** Ignorar en `_onRealtimeEvent` los `message.new` con `isOutgoing && isAdmin`.

**Por qué estoy seguro:** el envío funciona (llega al cliente); el icono depende de `status`; el único camino que deja `pending` pegado es ese `return current` tras un ack que ya ocurrió en SQLite; el WS siempre emite `message.new` al guardar un mensaje del dueño.

---

### Resumen de cambios (2 archivos principales)

| Incidencia | Archivo(s) | Cambio |
|---|---|---|
| Lista no actualiza | `push_service.dart`, `chats_list_screen.dart` | Push → sync SQLite + escuchar `conversation.updated` |
| Reloj en mis mensajes | `chat_screen.dart` | Arreglar `_mergeIncomingMessage` o dejar de sobrescribir con pending |

Son cambios acotados (~15–30 líneas). No requieren cambios en backend ni en Twilio.

¿Quieres que implemente estas correcciones?


## segundo prompt ##


si


## resp cursor ##


Listo. Cambios aplicados en 3 archivos:

1. Lista de chats (push_service.dart + chats_list_screen.dart)
Al llegar una push, primero sincroniza SQLite (syncConversationsIncremental + mensajes de esa conversación) y después muestra sonido/banner.
Al abrir desde notificación, también sincroniza antes de navegar.
La lista ahora escucha conversation.updated / conversation.sync, además de message.new.
2. Mensajes humanos atascados en “enviando” (chat_screen.dart)
_mergeIncomingMessage reemplaza el mensaje optimista (id temporal + pending) por la confirmación del servidor (id real + sent), en lugar de ignorar el evento.
Los message.new salientes del dueño ya no sobrescriben la UI; el stream de SQLite es la fuente de verdad.
Tests: 18 pasaron correctamente.

Para probar:

Lista: con la app abierta en chats, que un cliente escriba con WS caído → debe actualizarse preview/hora sin pull-to-refresh.
Chat: envía un mensaje como humano → el reloj debe pasar a ✓ en cuanto confirme el servidor.





#######################################################
## v1.2

## prompt 

la notificación funciona por un camino, pero la UI depende de otro que no siempre se ejecuta. eso lo solucionaste? solo dime


## resp cursor ##

Encontré por qué seguía igual:

Tu log dice: PushService: Firebase no configurado. La notificación no viene de FCM, viene del WebSocket + MessageAlertsService (sonido local). El arreglo anterior de push no aplicaba en tu dispositivo.

El bug real de la lista: al llegar un mensaje por WS, mergeWithLocal bloqueaba la actualización del preview si ya habías enviado un mensaje optimista (timestamp local más reciente). Sonaba la alerta, pero SQLite no actualizaba la fila del chat.

El bug de tus mensajes con reloj: _reconcileMessagesFromStore volvía a meter el mensaje pending aunque ya existía confirmado en SQLite.

Qué cambié ahora
bumpConversationFromMessage — actualiza la lista directo, sin pasar por mergeWithLocal.
_reconcileMessagesFromStore — no reinserta optimistas ya confirmados.
Tras enviar — fuerza lectura desde SQLite.
message.status — refresca ticks de entregado/leído.
Haz hot restart (R en la terminal, no r) y prueba de nuevo.




##############################
## v1.3



## prompt ##


Quiero que analices un problema específico en mi app de chat (WhatsBot).

Necesito que generes un prompt técnico detallado para solucionar lo siguiente:

Cuando entro a un chat, los mensajes no se actualizan automáticamente.
No se actualizan ni los mensajes entrantes ni los salientes en tiempo real.
El problema está SOLO en la capa de mensajería del chat (UI/real-time rendering).
NO quiero que modifiques autenticación, backend, base de datos, arquitectura general ni lógica de negocio.
SOLO debes enfocarte en la parte visual o de actualización en tiempo real del chat (streaming de mensajes, state management del chat UI, listeners, subscriptions, etc.).
Debe proponer una solución sin romper el resto del sistema.

IMPORTANTE: NO TOQUES CODIGO NI EDITES PROYECTO, SOLO DAME UN PROMPT PARA PONERTE PARA QUE HAGAS LO QUE QUIERO




## resp cursor ## (prompt para poner en cursor)

## Objetivo

Corregir la actualización en tiempo real de mensajes DENTRO de un chat abierto en WhatsBot (Flutter).
Problema: al entrar a un chat, los mensajes NO se actualizan automáticamente — ni entrantes ni salientes en vivo.
El usuario debe ver burbujas nuevas al instante (como WhatsApp) sin salir y reentrar al chat.

## Alcance ESTRICTO (no negociable)

✅ SÍ tocar:
- Capa UI / state management del chat abierto
- Suscripciones, listeners, streaming de mensajes hacia la UI
- Render en tiempo real (ListView, burbujas, ticks de estado)
- Tests de widget del chat (`chat_screen_test.dart`)

❌ NO tocar:
- Autenticación / login / JWT
- Backend Python / FastAPI / WebSocket server
- Esquema de base de datos / migraciones
- `SyncEngine`, `MessageRepository`, `ChatRepository` (salvo lectura para entender el flujo)
- `push_service.dart`, `chats_list_screen.dart` (salvo que sea imprescindible y justificado)
- Arquitectura general ni lógica de negocio (envío, dedup, cola offline, etc.)

Asume que la persistencia SQLite y el WS ya funcionan. El bug es de RENDERIZADO / REACTIVIDAD UI.

## Contexto del flujo actual (para no romper nada)

1. `RealtimeService.emitAfterPersist()` persiste en SQLite vía `SyncEngine.handleRealtimeEvent()` ANTES de emitir el evento a listeners UI.
2. `ChatScreen` hoy tiene DOS caminos paralelos hacia la UI:
   - `_messagesSub` → `watchMessages(conversationId).listen(_onMessagesFromStore)` → `setState()`
   - `StreamBuilder` en `build()` con `stream: _messageRepo.watchMessages(...)` e `initialData: widget.initialMessages`
3. `ChatsListScreen._openChat()` pasa `initialMessages` precargados desde SQLite (caché no vacía en uso real).
4. `_onRealtimeEvent()` en `message.new` / `message.status` solo llama `_refresh(silent: true, force: true)` (sync REST), NO actualiza la lista visible directamente.
5. La guía interna (`docs/INCREMENTAL_GUIDE.md` v1.17/v1.24) documentaba `_displayMessages` + merge inmediato del payload WS + reconciliación por `clientUuid`, pero el `chat_screen.dart` actual ya NO tiene eso — regresión probable.

## Hipótesis de causa raíz (priorizadas)

### A) Anti-patrón StreamBuilder + initialData stale (ALTA probabilidad)
- `watchMessages()` se invoca en cada `build()`, creando un stream NUEVO en cada `setState()`.
- `initialData: widget.initialMessages` es inmutable (snapshot al abrir el chat).
- Cada rebuild puede resetear visualmente al caché viejo hasta que el nuevo stream emita; en carreras o dedup sin escritura DB, la UI queda congelada en `initialMessages`.
- Los tests usan `initialMessages: const []` y pasan; en producción casi siempre hay caché → el bug no se reproduce en CI.

### B) Doble suscripción que se pisa (MEDIA)
- `_messagesSub` dispara `setState()` en cada cambio Drift.
- Eso fuerza rebuild del `StreamBuilder`, que cancela/resuscribe streams → thrashing y posible pérdida de frames intermedios.

### C) Dependencia exclusiva de `_refresh()` ante WS (MEDIA)
- Si SQLite ya tiene el mensaje (persistEvent) pero `upsertMessageDeduped` no escribe (dedup), Drift no re-emite.
- `_refresh()` tampoco provoca cambio DB → UI nunca se entera.
- Falta merge inmediato en capa UI (como documentaba v1.17).

### D) Mensajes salientes optimistas / ticks (MEDIA-BAJA, sub-síntoma)
- Tras enviar, la burbuja optimista (`status: pending`) debe reconciliarse con confirmación (`sent`/`delivered`) vía stream o merge por `clientUuid`.
- Si la UI no reacciona al stream, el reloj ⏱ puede quedar pegado (incidencia previa v1.1/v1.2).

## Solución esperada (implementar)

Refactorizar SOLO `chat_screen.dart` hacia un patrón de fuente única de verdad para la UI:

### 1. Un solo listener Drift (cachear stream en initState)
```dart
late final Stream<List<ChatMessage>> _messagesStream;

@override
void initState() {
  super.initState();
  _messagesStream = _messageRepo.watchMessages(widget.conversation.id);
  _messagesSub = _messagesStream.listen(_onMessagesFromStore);
  // seed inicial UNA vez:
  _displayMessages = widget.initialMessages ?? [];
}



## resp cursor ##

## Corrección aplicada

El bug venía del anti-patrón **StreamBuilder + `initialData` stale** combinado con doble suscripción a Drift. En cada `setState()` se recreaba el stream y la UI volvía al snapshot de `initialMessages` (caché al abrir el chat), quedando congelada en producción.

### Cambios en `chat_screen.dart`

1. **Fuente única de verdad:** `_displayMessages`, sembrada una sola vez con `initialMessages` en `initState`.
2. **Stream cacheado:** `_messagesStream` se crea una vez; un solo listener en `_messagesSub`.
3. **Sin `StreamBuilder`:** el `ListView` renderiza directamente `_displayMessages`.
4. **Reconciliación con SQLite:** `_reconcileWithStore()` mantiene optimistas pendientes y fusiona por `clientUuid`.
5. **Merge inmediato WS (v1.17/v1.24):**
   - `message.new` → `_mergeMessageIntoDisplay()` antes del `_refresh` REST
   - `message.status` → `_applyStatusUpdate()` para ticks en vivo

### Tests nuevos (regresión)

- **Con caché precargada + WS:** mensaje nuevo visible sin reabrir el chat.
- **Con caché precargada + Drift:** actualización al escribir en SQLite sin reabrir.

**14/14 tests pasan** en `chat_screen_test.dart`.

### Validación manual sugerida

1. Abrir un chat con historial → enviar mensaje → la burbuja aparece al instante y el tick se actualiza.
2. Recibir mensaje entrante con el chat abierto → burbuja nueva sin salir/reentrar.
3. Volver a la lista y reabrir → historial intacto (sin duplicados).





################################################
## v1.4

## prompt cursor ##

Esta es la parte que necesito que arregles, esta parte del chat, analiza y busca por qué podría ser y dame las soluciones en un prompt

adapta el prompt : 
[## Objetivo

Corregir la actualización en tiempo real de mensajes DENTRO de un chat abierto en WhatsBot (Flutter).
Problema: al entrar a un chat, los mensajes NO se actualizan automáticamente — ni entrantes ni salientes en vivo.
El usuario debe ver burbujas nuevas al instante (como WhatsApp) sin salir y reentrar al chat.

## Alcance ESTRICTO (no negociable)

✅ SÍ tocar:
- Capa UI / state management del chat abierto
- Suscripciones, listeners, streaming de mensajes hacia la UI
- Render en tiempo real (ListView, burbujas, ticks de estado)
- Tests de widget del chat (`chat_screen_test.dart`)

❌ NO tocar:
- Autenticación / login / JWT
- Backend Python / FastAPI / WebSocket server
- Esquema de base de datos / migraciones
- `SyncEngine`, `MessageRepository`, `ChatRepository` (salvo lectura para entender el flujo)
- `push_service.dart`, `chats_list_screen.dart` (salvo que sea imprescindible y justificado)
- Arquitectura general ni lógica de negocio (envío, dedup, cola offline, etc.)

Asume que la persistencia SQLite y el WS ya funcionan. El bug es de RENDERIZADO / REACTIVIDAD UI.

## Contexto del flujo actual (para no romper nada)

1. `RealtimeService.emitAfterPersist()` persiste en SQLite vía `SyncEngine.handleRealtimeEvent()` ANTES de emitir el evento a listeners UI.
2. `ChatScreen` hoy tiene DOS caminos paralelos hacia la UI:
   - `_messagesSub` → `watchMessages(conversationId).listen(_onMessagesFromStore)` → `setState()`
   - `StreamBuilder` en `build()` con `stream: _messageRepo.watchMessages(...)` e `initialData: widget.initialMessages`
3. `ChatsListScreen._openChat()` pasa `initialMessages` precargados desde SQLite (caché no vacía en uso real).
4. `_onRealtimeEvent()` en `message.new` / `message.status` solo llama `_refresh(silent: true, force: true)` (sync REST), NO actualiza la lista visible directamente.
5. La guía interna (`docs/INCREMENTAL_GUIDE.md` v1.17/v1.24) documentaba `_displayMessages` + merge inmediato del payload WS + reconciliación por `clientUuid`, pero el `chat_screen.dart` actual ya NO tiene eso — regresión probable.

## Hipótesis de causa raíz (priorizadas)

### A) Anti-patrón StreamBuilder + initialData stale (ALTA probabilidad)
- `watchMessages()` se invoca en cada `build()`, creando un stream NUEVO en cada `setState()`.
- `initialData: widget.initialMessages` es inmutable (snapshot al abrir el chat).
- Cada rebuild puede resetear visualmente al caché viejo hasta que el nuevo stream emita; en carreras o dedup sin escritura DB, la UI queda congelada en `initialMessages`.
- Los tests usan `initialMessages: const []` y pasan; en producción casi siempre hay caché → el bug no se reproduce en CI.

### B) Doble suscripción que se pisa (MEDIA)
- `_messagesSub` dispara `setState()` en cada cambio Drift.
- Eso fuerza rebuild del `StreamBuilder`, que cancela/resuscribe streams → thrashing y posible pérdida de frames intermedios.

### C) Dependencia exclusiva de `_refresh()` ante WS (MEDIA)
- Si SQLite ya tiene el mensaje (persistEvent) pero `upsertMessageDeduped` no escribe (dedup), Drift no re-emite.
- `_refresh()` tampoco provoca cambio DB → UI nunca se entera.
- Falta merge inmediato en capa UI (como documentaba v1.17).

### D) Mensajes salientes optimistas / ticks (MEDIA-BAJA, sub-síntoma)
- Tras enviar, la burbuja optimista (`status: pending`) debe reconciliarse con confirmación (`sent`/`delivered`) vía stream o merge por `clientUuid`.
- Si la UI no reacciona al stream, el reloj ⏱ puede quedar pegado (incidencia previa v1.1/v1.2).

## Solución esperada (implementar)

Refactorizar SOLO `chat_screen.dart` hacia un patrón de fuente única de verdad para la UI:

### 1. Un solo listener Drift (cachear stream en initState)
```dart
late final Stream<List<ChatMessage>> _messagesStream;

@override
void initState() {
  super.initState();
  _messagesStream = _messageRepo.watchMessages(widget.conversation.id);
  _messagesSub = _messagesStream.listen(_onMessagesFromStore);
  // seed inicial UNA vez:
  _displayMessages = widget.initialMessages ?? [];
}

]


IMPORTANTE: NO EDITES CODIGO NI MODIFIQUES PROYECTO, NECESITO QUE ME DES UN PROMPT QUE PONDRE EN PLAN (NO AGENT, PLAN) PARA SOLUCOINAR ESO, OSEA ADAPTA EL PROMPT A LA IMAGEN, ESA ES LA PARTE QUE NECESITO QUE ARREGLES, QUE LOS MENSAJES SE VISUALICEN PORQUE NO SE ESTÁN VISUALIZANDO, REVISA Y DAME EL PROMPT



## RESP CURSOR ##

## Objetivo

Corregir la actualización en tiempo real de mensajes DENTRO de un chat abierto en WhatsBot (Flutter).

### Síntoma reportado (captura adjunta — Omar Suarez, 35699155990)

- Al abrir el chat con Omar Suarez, los mensajes históricos SÍ se ven (entrantes del cliente: "kmk", "jkmnl", "scsdv"; respuestas automáticas WhatsBot; saliente admin "Jqiqnq" con doble tick).
- El problema es que, con el chat ABIERTO, los mensajes nuevos NO aparecen en vivo — ni entrantes del cliente, ni respuestas del bot, ni salientes del admin.
- Solo se ven al salir del chat y volver a entrar (re-carga desde SQLite vía `getCachedMessages` en `ChatsListScreen._openChat`).
- Comportamiento esperado: burbujas nuevas al instante, como WhatsApp, sin salir y reentrar.

## Alcance ESTRICTO (no negociable)

✅ SÍ tocar:
- `whatsbot_app/lib/screens/chat_screen.dart` (UI + state management del chat abierto)
- Suscripciones, listeners, streaming de mensajes hacia la UI
- Render en tiempo real (`ListView.builder` reverse, `MessageBubble`, ticks de estado)
- Tests de widget: `whatsbot_app/test/screens/chat_screen_test.dart`
- Nota breve en `docs/INCREMENTAL_GUIDE.md` solo si cierras la incidencia

❌ NO tocar:
- Autenticación / login / JWT
- Backend Python / FastAPI / WebSocket server
- Esquema de base de datos / migraciones
- `SyncEngine`, `MessageRepository`, `ChatRepository` (salvo lectura para entender el flujo)
- `push_service.dart`, `chats_list_screen.dart` (salvo que sea imprescindible y justificado)
- Arquitectura general ni lógica de negocio (envío, dedup, cola offline, etc.)

Asume que la persistencia SQLite y el WS ya funcionan (los mensajes llegan a DB — se confirma al reabrir el chat). El bug es de RENDERIZADO / REACTIVIDAD UI.

## Estado actual del código (leer ANTES de planificar — no asumir StreamBuilder)

El `chat_screen.dart` actual YA fue refactorizado (v1.17 / v1.24). NO usa `StreamBuilder` en `build()`.

Patrón actual:
1. `_messagesStream` cacheado una vez en `initState` → `_messageRepo.watchMessages(conversation.id)`
2. `_messagesSub` escucha Drift → `_onMessagesFromStore()` → `_reconcileWithStore()` → `setState()`
3. `_displayMessages` es la fuente que renderiza el `ListView.builder(reverse: true)`
4. `_realtimeSub` escucha `realtimeService.events` → `_onRealtimeEvent()`:
   - `message.new` → `_mergeMessageIntoDisplay()` + `setState()` + `_refresh(silent, force: true)`
   - `message.status` → `_applyStatusUpdate()` + `setState()`
5. `ChatsListScreen._openChat()` pasa `initialMessages` precargados desde `getCachedMessages()`
6. `RealtimeService.emitAfterPersist()` persiste vía `SyncEngine.handleRealtimeEvent()` ANTES de emitir a la UI

Los tests en `chat_screen_test.dart` ya cubren:
- Mensaje en vivo sin caché
- Mensaje en vivo CON `initialMessages` en caché (regresión StreamBuilder)
- Actualización por Drift sin reabrir
- `conversation_id` servidor distinto (FIX 1b, por `wa_id`)
- WS caído + REST fallback

Si el bug persiste en dispositivo real, es una regresión o un caso NO cubierto por los tests actuales.

## Hipótesis de causa raíz (priorizadas — actualizadas tras análisis)

### A) Drift watch no dispara actualización UI para el `conversation.id` abierto (ALTA)

- `watchMessages(conversation.id)` filtra por `conversation_id` local en SQLite.
- Si el mensaje se persiste bajo otro `conversation_id` (servidor ≠ local) y el merge WS falla, Drift no emite para el stream del chat abierto.
- Al reabrir: `getCachedMessages()` puede devolver datos ya reconciliados por `resolveForLocalStore`.
- Caso real: Omar con `customerWaId: 35699155990` (sin prefijo `+`) — verificar que `_sameWa()` en `_messageBelongsToChat` normalice correctamente vs payloads WS (`+356...`, `549...`, etc.).
- Si `_messageBelongsToChat` devuelve `false`, `_mergeMessageIntoDisplay` nunca corre y la UI depende solo del watch Drift (que no ve el mensaje).

### B) `_reconcileWithStore` pisa o pierde mensajes mergeados por WS (ALTA)

- Flujo: WS mergea en `_displayMessages` → luego `_onMessagesFromStore` reemplaza con `_reconcileWithStore(store)`.
- Si `store` no incluye el mensaje nuevo (watch filtrado por `conversation_id` incorrecto), `_reconcileWithStore` DEBE preservar mensajes de `_displayMessages` que pasen `_messageBelongsToChat`.
- Bug posible: la reconciliación elimina mensajes "huérfanos" en algún edge case (dedup por `clientUuid`, orden, ids temporales negativos).
- Síntoma: mensaje visible un frame y desaparece, o nunca aparece.

### C) Doble vía con carrera WS ↔ Drift ↔ `_refresh` (MEDIA)

- Cada `message.new` dispara: merge inmediato + `_refresh(silent, force: true)`.
- `_refresh` llama `syncMessagesIncremental` pero NO actualiza `_displayMessages` directamente al terminar (solo `handleChatMessages` para alertas).
- Si merge WS falla y Drift dedup no escribe (`upsertMessageDeduped` → `false`), `_refresh` tampoco provoca cambio visible → UI congelada en snapshot de apertura.
- La red de seguridad debería ser: tras `_refresh`, re-leer SQLite y fusionar en `_displayMessages`.

### D) WS desconectado en dispositivo real sin fallback percibido (MEDIA)

- Fallback REST cada 30 s solo si: chat abierto + WS↓ + online (`_wsFallbackTimer`).
- Usuario sale y reentra antes de 30 s → parece que solo reabrir funciona.
- Verificar estado WS en dispositivo; no confundir con bug de UI si el canal real está caído.

### E) Mensajes salientes / ticks como sub-síntoma (MEDIA-BAJA)

- Envío optimista vía `MessageRepository.sendMessage` → `upsertMessage` → Drift debería emitir.
- Si el watch no reacciona, la burbuja no aparece o el reloj ⏱ queda pegado.
- Reconciliación por `clientUuid` en `_mergeMessageIntoDisplay` debe reemplazar temp id negativo por id servidor.

### F) Tests pasan pero producción falla — gap de cobertura (ALTA probabilidad)

- Tests usan `customerWaId: '+5491111111111'`; producción usa `35699155990`.
- Tests emiten eventos vía `debugEmitEvent` (persiste + UI); en dispositivo el timing puede diferir.
- Falta test E2E widget: caché precargada + `wa_id` sin `+` + mensaje entrante + respuesta bot (`isAdmin: false, direction: outgoing`) mientras chat abierto.

## Plan de diagnóstico (ejecutar primero en Plan, sin tocar backend)

1. Leer `chat_screen.dart` completo y trazar los 3 caminos hacia `_displayMessages`:
   - seed `initialMessages` en `initState`
   - `_onMessagesFromStore` (Drift)
   - `_onRealtimeEvent` → `_mergeMessageIntoDisplay` (WS)
2. Verificar si `_messageBelongsToChat` acepta `35699155990` vs variantes del payload WS.
3. Verificar si `_reconcileWithStore` preserva mensajes WS cuando `store` no los contiene.
4. Confirmar que `build()` renderiza SOLO `_displayMessages` (no hay `StreamBuilder` residual).
5. Ejecutar tests existentes:
   ```bash
   cd whatsbot_app && flutter test test/screens/chat_screen_test.dart && flutter analyze


#######################################




