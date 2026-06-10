# WhatsBot — App Flutter (Fase 9)

App móvil del dueño con UI tipo WhatsApp. **Solo Android e iOS** — no Flutter Web.

## Requisitos

- Flutter 3.x (`flutter doctor`)
- Backend API corriendo (`python -m api.main` desde `final_system/`)

## Configuración

La URL del backend está en `lib/config/api_config.dart`:

```dart
static const String apiBaseUrl = 'http://127.0.0.1:5000';
```

Este valor coincide con `API_PUBLIC_URL` en `final_system/.env`.

| Entorno | URL típica |
|---------|------------|
| iOS Simulator / dispositivo en LAN | `http://127.0.0.1:5000` o IP de tu PC |
| Emulador Android | `http://10.0.2.2:5000` |
| Producción / ngrok | URL HTTPS pública |

**No** incluir `TWILIO_AUTH_TOKEN` ni otros secrets en la app.

## Arranque

```bash
cd final_system/whatsbot_app
flutter pub get
flutter analyze
flutter run
```

## Login

- **ID negocio:** `default` (o el `business_id` de tu negocio)
- **PIN:** valor de `WHATSBOT_OWNER_PIN` en el `.env` del servidor

## Pantallas

| Pantalla | Descripción |
|----------|-------------|
| Login | business_id + PIN → JWT |
| Lista de chats | Header verde, conversaciones del bot |
| Chat | Burbujas WA, input abajo, tiempo real vía WebSocket |
| Pedido | Barra Aprobar / Rechazar si hay pedido pendiente |
| Ajustes | Menú, Intents, Mensajes, cerrar sesión |

## API consumida

Ver `docs/FLUTTER_APP.md` en la raíz de `final_system/`.
