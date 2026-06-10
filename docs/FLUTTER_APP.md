# App Flutter WhatsBot

App móvil del dueño (Android/iOS) con UI tipo WhatsApp. Consume la API REST de Fase 7.

## Proyecto

| Concepto | Ubicación |
|----------|-----------|
| Código Flutter | `final_system/whatsbot_app/` |
| URL del backend | `lib/config/api_config.dart` → `apiBaseUrl` |
| Origen de la URL | `API_PUBLIC_URL` en `final_system/.env` (actualmente `http://127.0.0.1:5000`) |
| Tema visual | `lib/theme/whatsapp_theme.dart` |

**Prohibido en la app:** `TWILIO_AUTH_TOKEN`, SIDs, ni cualquier secret de Twilio.

## Compilar y ejecutar

```bash
# Terminal 1 — backend
cd final_system
python -m api.main

# Terminal 2 — app
cd final_system/whatsbot_app
flutter pub get
flutter analyze
flutter run
```

### URL según dispositivo

| Dispositivo | `apiBaseUrl` típica |
|-------------|---------------------|
| iOS Simulator | `http://127.0.0.1:5000` |
| Emulador Android | `http://10.0.2.2:5000` |
| Teléfono en la misma WiFi | `http://<IP-de-tu-PC>:5000` |
| Producción | URL HTTPS de `API_PUBLIC_URL` (ngrok, Railway, etc.) |

Edita `lib/config/api_config.dart` si cambias de entorno.

## Login de prueba

```http
POST /auth/login
Content-Type: application/json

{"business_id": "default", "pin": "<WHATSBOT_OWNER_PIN del .env del servidor>"}
```

Respuesta:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "business_id": "default",
  "business_name": "..."
}
```

La app guarda el JWT en `shared_preferences` y lo envía como `Authorization: Bearer ...`.

## Rutas consumidas

| Método | Ruta | Pantalla Flutter |
|--------|------|------------------|
| POST | `/auth/login` | `login_screen.dart` |
| GET | `/whatsbot/conversations` | `chats_list_screen.dart` |
| GET | `/whatsbot/conversations/{id}/messages` | `chat_screen.dart` |
| POST | `/whatsbot/messages` | `chat_screen.dart` (enviar) |
| GET | `/whatsbot/orders/pending` | `chat_screen.dart` (barra pedido) |
| POST | `/whatsbot/orders/{id}/approve` | `order_actions_bar.dart` |
| POST | `/whatsbot/orders/{id}/reject` | `order_actions_bar.dart` |
| GET | `/whatsbot/business/me` | `settings_screen.dart` |
| GET/PUT | `/whatsbot/business/menu` | `menu_editor_screen.dart` |
| GET/PUT | `/whatsbot/business/intents` | `intents_editor_screen.dart` |
| GET/PUT | `/whatsbot/business/prompts` | `prompts_editor_screen.dart` |

## UI esperada

| Pantalla | Detalle visual |
|----------|----------------|
| Login | Fondo verde `#075E54`, tarjeta con business_id + PIN |
| Lista chats | AppBar verde, avatar, preview último mensaje, hora |
| Chat | Fondo `#ECE5DD`, burbujas blancas (entrante) y `#DCF8C6` (saliente) |
| Input chat | Barra inferior gris claro, botón enviar `#128C7E` |
| Pedido pendiente | Banner amarillo con Aprobar / Rechazar |
| Ajustes | Acceso a Menú, Intents, Mensajes |

## Tiempo real (Fase 11.3+)

- **WebSocket** `wss://{API}/whatsbot/ws?token=<JWT>` — mensajes al instante.
- Servicio: `lib/services/realtime_service.dart` (reconexión + sync `since`/`after_id`).
- **Sync al reconectar:** `SyncEngine` + `connectivity_plus` (sin polling periódico).
- Pull-to-refresh sigue disponible en la lista de chats.

## Offline-first (OF-A — OF-E)

La app funciona sin red: chats e historial desde SQLite; sync al volver online.

| Capa | Ubicación |
|------|-----------|
| SQLite local | `lib/data/local/` (Drift) |
| Repositorios | `lib/data/repositories/` |
| Motor de sync | `lib/data/sync/sync_engine.dart` |
| Cola saliente | `outbound_queue` + `MessageRepository.sendMessage` |
| Conectividad | `lib/services/connectivity_service.dart` |

### Comportamiento

1. **Cold start** — lista e historial desde disco (<100 ms si hay caché).
2. **Sin red** — datos locales visibles; envío encola mensaje optimista (`status: pending`).
3. **Vuelve red** — `flushOutboundQueue` + sync incremental + reconexión WS.
4. **Idempotencia** — `client_id` en `POST /whatsbot/messages` evita duplicados en reintento.

### Validación offline-first

```bash
cd final_system/whatsbot_app
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
```

### Checklist manual offline

1. Login con API → ver chats → cerrar app → reabrir → lista instantánea.
2. Modo avión → abrir chat → historial local visible.
3. Modo avión → enviar mensaje → burbuja con reloj pendiente.
4. Quitar modo avión → mensaje se envía; ticks normales.
5. WS activo → mensaje cliente aparece al instante y persiste tras reinicio.

## Push FCM/APNs (Fase 11.4)

Con la app en **background o cerrada**, el servidor envía push si no hay WebSocket activo.

### Sin Firebase (degradación)

La app funciona igual: WS + notificaciones locales. `PushService.init()` captura el error si no hay config Firebase.

### Configurar Firebase (una vez)

1. [Firebase Console](https://console.firebase.google.com/) → crear proyecto → añadir app **Android** e **iOS**.
2. **Android:** descargar `google-services.json` → `whatsbot_app/android/app/google-services.json`
3. **iOS:** descargar `GoogleService-Info.plist` → `whatsbot_app/ios/Runner/GoogleService-Info.plist`
4. **Backend:** en Firebase → Configuración → Cuentas de servicio → generar clave JSON → guardar en `final_system/credentials/firebase-service-account.json` (gitignore).
5. En `final_system/.env`:

   ```env
   FCM_ENABLED=true
   FCM_SERVICE_ACCOUNT_JSON_PATH=credentials/firebase-service-account.json
   ```

6. `pip install -r requirements.txt` (incluye `firebase-admin`).
7. Recompilar app: `flutter pub get && flutter run`.

### Registro de token

Tras login, `push_service.dart` llama `POST /whatsbot/device-token`. Al logout, `DELETE /whatsbot/device-token`.

### Deep link

Payload FCM incluye `conversation_id`. Tap en la notificación abre el chat (`messageAlerts.onOpenConversation`).

### iOS adicional

- Xcode → Runner → Signing & Capabilities → **Push Notifications**
- `Info.plist` ya incluye `UIBackgroundModes` → `remote-notification`
- Subir clave APNs en Firebase (Project Settings → Cloud Messaging)

## Validación Fase 9

```bash
cd final_system/whatsbot_app
flutter pub get
flutter analyze
# Resultado esperado: No issues found!
```

### Prueba manual (checklist)

1. **Login → chat → mensaje → pedido**
   - Iniciar sesión con `default` + PIN del servidor.
   - Abrir una conversación (o enviar mensaje de prueba al bot desde WhatsApp).
   - Escribir respuesta desde la app → el cliente debe recibirla por Twilio.
   - Si hay pedido pendiente del cliente, usar **Aprobar** o **Rechazar**.

2. **Menú**
   - Ajustes → Menú → editar nombre/precio de un producto → Guardar.
   - El bot cargará el menú nuevo en BD; el próximo cliente que pida *menu* verá los cambios.

3. **Mensajes**
   - Ajustes → Mensajes → editar bienvenida (`node_start_message` o `empty_body_hint`) → Guardar.
   - Un cliente nuevo que escriba al bot recibirá el texto actualizado.

Ver también: `docs/GUIA_EDICION_APP.md` (tutorial para el dueño del negocio).

## Estructura del código

```
whatsbot_app/lib/
├── config/api_config.dart
├── di/app_services.dart
├── data/
│   ├── local/          # Drift: conversations, messages, sync_cursors, outbound_queue
│   ├── repositories/   # chat_repository, message_repository
│   └── sync/           # sync_engine.dart
├── theme/whatsapp_theme.dart
├── services/
│   ├── api_client.dart
│   ├── realtime_service.dart
│   ├── connectivity_service.dart
│   └── message_alerts_service.dart
├── models/
├── screens/
└── widgets/
```
