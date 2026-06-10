# WhatsBot SaaS

Backend **FastAPI** + app móvil **Flutter** (UI tipo WhatsApp). Multi-negocio; el dueño edita menú, intents y mensajes **solo desde la app** — no hay UI web.

## Guía rápida (15 líneas)

Para correr el sistema:

- **Bot (Python / API): desde final_system:**

python -m api.main

- **App Flutter: desde final_system:**

cd whatsbot_app
flutter run





1. `cd final_system` → activa venv → `pip install -r requirements.txt`
2. El `.env` ya tiene credenciales migradas del bot en la raíz (Twilio, Admin, Google).
3. `python scripts/migrate_db.py` — crea tablas (SQLite local si no hay PostgreSQL).
4. `python scripts/onboard_business.py --default` — negocio `default` con Twilio/Admin del legacy.
5. `python -m api.main` — API en `http://127.0.0.1:5000`
6. ngrok (opcional): `ngrok http 5000` → Twilio webhook `POST {URL}/webhook`
7. `cd whatsbot_app` → edita `lib/config/api_config.dart` si usas emulador/teléfono.
8. `flutter pub get && flutter run` — app WhatsBot en el móvil.
9. Login: negocio `default`, PIN = `WHATSBOT_OWNER_PIN` del `.env`.
10. Cliente escribe al `TWILIO_WHATSAPP_FROM` → chat aparece en la app.
11. Dueño responde desde la app → cliente recibe por WhatsApp.
12. Pedido → notifica `ADMIN_WHATSAPP_NUMBER`; aprueba desde app **o** escribiendo `CONFIRMAR ORD-XXX`.
13. Ajustes → Menú / Intents / Mensajes para cambiar el bot sin código.
14. Validar: `python scripts/validate_system.py` y `python -m pytest tests/ -v`
15. Más detalle: `docs/GUIA_NEGOCIOS.md`, `docs/GUIA_EDICION_APP.md`, `docs/FLUTTER_APP.md`

---

## Credenciales migradas (desde bot original en raíz)

Valores en `final_system/.env` (no se listan secrets aquí). Origen en el `.env` legacy de la raíz:

| Variable `final_system` | Origen legacy |
|-------------------------|---------------|
| `TWILIO_ACCOUNT_SID` | `TWILIO_ACCOUNT_SID` |
| `TWILIO_AUTH_TOKEN` | `TWILIO_AUTH_TOKEN` |
| `TWILIO_WHATSAPP_FROM` | `TWILIO_WHATSAPP_FROM` |
| `TWILIO_REST_WEBHOOK_REPLIES` | `TWILIO_REST_WEBHOOK_REPLIES` |
| `ADMIN_WHATSAPP_NUMBER` | `ADMIN_WHATSAPP_NUMBER` |
| `ADMIN_REMINDER_INTERVAL_SECONDS` | `ADMIN_REMINDER_INTERVAL_SECONDS` |
| `ADMIN_REMINDER_MAX_SECONDS` | `ADMIN_REMINDER_MAX_SECONDS` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | `GOOGLE_SHEETS_CREDENTIALS_PATH` |
| `GOOGLE_SPREADSHEET_ID` | `GOOGLE_SPREADSHEET_ID` |
| `MENU_CACHE_TTL_SECONDS` | `MENU_CACHE_TTL_SECONDS` |
| `ORDERS_CACHE_TTL_SECONDS` | `ORDERS_CACHE_TTL_SECONDS` |
| `BLOCKED_USERS_CACHE_TTL_SECONDS` | `BLOCKED_USERS_CACHE_TTL_SECONDS` |
| `SHEETS_INCREMENTAL_*` | mismos nombres en legacy |
| `STATE_PERSIST_PATH` | `STATE_PERSIST_PATH` |
| `PARSER_ERROR_LOG_PATH` | `PARSER_ERROR_LOG_PATH` |
| `DEFAULT_BUSINESS_NAME` | `RESTAURANT_NAME` |
| `JWT_SECRET_KEY` | `SECRET_KEY` |
| `SECRET_KEY` | `SECRET_KEY` |
| Archivo JSON Google | `credentials/google-service-account.json` (copiado) |

**Nuevas (solo SaaS):** `DATABASE_URL`, `API_PUBLIC_URL`, `CORS_ORIGINS`, `WHATSBOT_OWNER_PIN`, `DEFAULT_BUSINESS_ID`, `GOOGLE_SHEETS_ENABLED`.

Plantilla vacía: `.env.example`.

---

## A. Arrancar backend (API + webhook)

1. Entra al directorio e instala dependencias:

   ```bash
   cd final_system
   pip install -r requirements.txt
   ```

2. Revisa `final_system/.env`. Si vienes del bot legacy, ya está poblado. Sin PostgreSQL local:

   ```env
   DATABASE_URL=sqlite:///data/whatsbot.db
   ```

3. Crea tablas y negocio default (Twilio + Admin del legacy):

   ```bash
   python scripts/migrate_db.py
   python scripts/onboard_business.py --default
   ```

4. Arranca la API:

   ```bash
   python -m api.main
   ```

   Health: `GET http://127.0.0.1:5000/health`

5. Expón el webhook para Twilio (desarrollo):

   ```bash
   ngrok http 5000
   ```

   En Twilio Console → WhatsApp → **When a message comes in**:

   ```
   POST https://<tu-ngrok>.ngrok-free.app/webhook
   ```

   Alias compatible: `POST /bot`

6. (Opcional) Google Sheets espejo — desactivado por defecto (`GOOGLE_SHEETS_ENABLED=false`). El sistema funciona solo con BD.

7. Valida antes de producción:

   ```bash
   python scripts/validate_chatbot.py
   python scripts/validate_api.py
   python scripts/validate_system.py
   python -m pytest tests/ -v
   ```

---

## B. Arrancar app Flutter (`whatsbot_app`)

1. Con la API corriendo, abre otra terminal:

   ```bash
   cd final_system/whatsbot_app
   flutter pub get
   ```

2. Edita la URL del backend en `lib/config/api_config.dart`:

   | Entorno | `apiBaseUrl` |
   |---------|--------------|
   | iOS Simulator / PC local | `http://127.0.0.1:5000` |
   | Emulador Android | `http://10.0.2.2:5000` |
   | Teléfono misma WiFi | `http://<IP-de-tu-PC>:5000` |
   | Producción | `API_PUBLIC_URL` HTTPS |

3. Ejecuta la app:

   ```bash
   flutter analyze
   flutter run
   ```

4. Login de prueba:
   - **ID negocio:** `default`
   - **PIN:** valor de `WHATSBOT_OWNER_PIN` en `final_system/.env`

5. Pantallas: lista de chats, chat (responder), barra de pedidos, Ajustes → Menú / Intents / Mensajes.

Detalle visual y rutas API: `docs/FLUTTER_APP.md`. Tutorial dueño: `docs/GUIA_EDICION_APP.md`.

---

## Alta de nuevo negocio

Ver `docs/GUIA_NEGOCIOS.md`. Resumen:

```bash
python scripts/onboard_business.py \
  --id otro-local \
  --name "Otro Local" \
  --twilio-from "whatsapp:+57300..." \
  --admin "whatsapp:+57300..."
```

Configura el webhook Twilio del nuevo número → `{API_PUBLIC_URL}/webhook`.

---

## Probar flujo completo

| Paso | Acción | Resultado esperado |
|------|--------|-------------------|
| 1 | Cliente escribe al `TWILIO_WHATSAPP_FROM` | Bot responde (bienvenida / menú) |
| 2 | Abrir app Flutter → login `default` | Chat del cliente en la lista |
| 3 | Dueño responde desde la app | Cliente recibe mensaje por WhatsApp |
| 4 | Cliente confirma un pedido | Admin recibe alerta en `ADMIN_WHATSAPP_NUMBER` |
| 5a | Dueño **Aprueba** en la app | Cliente recibe confirmación |
| 5b | Dueño escribe `CONFIRMAR ORD-XXX` por WhatsApp admin | Mismo resultado (legacy) |
| 6 | App → Menú → cambiar precio → Guardar | Cliente que pida `menu` ve el cambio |
| 7 | App → Mensajes → cambiar bienvenida | Próximo saludo usa el texto nuevo |

---

## Checklist E2E (Fase 10)

- [ ] Cliente escribe al bot → respuesta automática
- [ ] Mensaje aparece en app Flutter
- [ ] Dueño responde desde Flutter → cliente recibe por Twilio
- [ ] Pedido → notifica admin WhatsApp legacy
- [ ] Dueño aprueba desde Flutter → cliente notificado
- [ ] Dueño aprueba desde `ADMIN_WHATSAPP_NUMBER` → sigue funcionando
- [ ] Sheets deshabilitado → OK (`GOOGLE_SHEETS_ENABLED=false`)
- [ ] Dueño edita menú en app → cliente ve menú nuevo en WhatsApp
- [ ] Dueño edita un intent en app → bot reacciona a la keyword nueva
- [ ] Dueño edita texto de bienvenida en app → cliente recibe el texto nuevo

Automatizado en `scripts/validate_system.py` (gateway, API, pedido, edición BD). Pruebas manuales con Twilio real para los ítems de WhatsApp físico.

---

## Tiempo real (Fase 11)

Comportamiento tipo WhatsApp: mensajes al instante, push con app cerrada, ticks de estado.

| Capa | Qué hace |
|------|----------|
| **WebSocket** | `WS /whatsbot/ws?token=JWT` — eventos live (`message.new`, `order.pending`, …) |
| **FCM/APNs** | Push si el dueño no tiene WS activo (`FCM_ENABLED=true` + credenciales servidor) |
| **REST sync** | `?since=` / `?after_id=` al reconectar; fallback 30 s si WS cae |
| **Estados** | `sent` → `delivered` → `read`; ticks en burbujas salientes del dueño |

### Variables `.env` (Fase 11)

```env
REALTIME_ENABLED=true
WS_HEARTBEAT_SECONDS=30
FCM_ENABLED=false
FCM_SERVICE_ACCOUNT_JSON_PATH=credentials/firebase-service-account.json
```

Migración BD mensajes: `python scripts/migrate_message_status.py` (o `python scripts/migrate_db.py`).

Setup Firebase en app: `docs/FLUTTER_APP.md` sección **Push FCM/APNs**.

### Checklist E2E tiempo real (Fase 11)

| Ítem | Automatizado | Manual |
|------|--------------|--------|
| Cliente escribe → dueño ve en &lt;1 s (app abierta, sin polling) | `validate_system` WS | WhatsApp real |
| WS reconecta + sync `since`/`after_id` | tests realtime | WiFi on/off |
| Registro device token | `validate_system` | — |
| mark-read + status en BD | `test_message_status` | Abrir chat en app |
| Pedido → `order.pending` en WS | tests + mirror hook | Pedido real |
| Push FCM app cerrada | — | Firebase configurado |
| Sin FCM → WS + notif. locales | degradación documentada | `FCM_ENABLED=false` |
| Dos teléfonos mismo negocio | `test_realtime_ws` broadcast | 2 dispositivos |

---

## Validación (salidas de referencia)

Ejecutar desde `final_system/`:

```bash
python scripts/validate_chatbot.py
python scripts/validate_api.py
python scripts/validate_system.py
python -m pytest tests/ -v
```

Ver sección **Resultados de validación** al final de este README (actualizada en Fase 10).

---

## Estructura del proyecto

| Carpeta | Rol |
|---------|-----|
| `api/` | FastAPI: webhook, auth JWT, REST WhatsBot |
| `chatbot/` | Gateway + lógica conversacional (copiada del legacy) |
| `config/` | Settings, intents, prompts (fallback + semilla) |
| `models/` | SQLAlchemy: business, conversation, message, order, menu |
| `services/` | Negocio, conversaciones, pedidos, notificaciones, Sheets opcional |
| `whatsbot_app/` | App Flutter del dueño |
| `scripts/` | migrate, onboard, validate_* |
| `docs/` | Guías arquitectura, Flutter, negocios, edición, incremental |

---

## Documentación

- `docs/ARCHITECTURE.md` — diagrama y flujos
- `docs/FLUTTER_APP.md` — compilar app, login, rutas API
- `docs/GUIA_NEGOCIOS.md` — alta de negocio paso a paso
- `docs/GUIA_EDICION_APP.md` — dueño edita menú/intents/mensajes sin código
- `docs/INCREMENTAL_GUIDE.md` — registro por fase (desarrolladores)

---

## Resultados de validación (Fase 10 + 11)

Ejecutar desde `final_system/`:

```bash
python scripts/validate_chatbot.py
python scripts/validate_api.py
python scripts/migrate_message_status.py   # si BD existía antes de Fase 11.5
python scripts/validate_system.py
python -m pytest tests/ -q
cd whatsbot_app && flutter analyze
```

Salida esperada: **0 fallos** en scripts de validación, **29 passed** en pytest, **No issues found!** en Flutter.

`GET /health` incluye `realtime_enabled` y `fcm_enabled`.

API en ejecución local: `python -m api.main` con `DATABASE_URL=sqlite:///data/whatsbot.db`.
