# WhatsBot

Backend **FastAPI** para bot de WhatsApp multi-negocio. Gestiona conversaciones, pedidos, menú e intents desde la API. El cliente externo (app móvil, panel, etc.) se conecta por REST + WebSocket.

## Guía rápida

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Crear tablas y negocio default
python scripts/migrate_db.py
python scripts/onboard_business.py --default

# 3. Arrancar la API
python -m api.main
# → http://127.0.0.1:5000
# → Health: GET /health

# 4. Exponer webhook (desarrollo)
ngrok http 5000
# Twilio Console → When a message comes in → POST https://<ngrok>/webhook
```

---

## A. Arrancar el backend

1. Instala dependencias:

   ```bash
   pip install -r requirements.txt
   ```

2. Ajusta `.env`. Sin PostgreSQL local usa SQLite:

   ```env
   DATABASE_URL=sqlite:///data/whatsbot.db
   ```

3. Crea tablas y negocio default:

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

6. (Opcional) Google Sheets espejo — desactivado por defecto (`GOOGLE_SHEETS_ENABLED=false`).

7. Valida antes de producción:

   ```bash
   python scripts/validate_chatbot.py
   python scripts/validate_api.py
   python scripts/validate_system.py
   python -m pytest tests/ -v
   ```

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
| 2 | `GET /whatsbot/conversations` con JWT | Chat del cliente en la lista |
| 3 | `POST /whatsbot/messages` con JWT | Cliente recibe mensaje por WhatsApp |
| 4 | Cliente confirma un pedido | Admin recibe alerta en `ADMIN_WHATSAPP_NUMBER` |
| 5a | `POST /whatsbot/orders/{id}/approve` | Cliente recibe confirmación |
| 5b | Dueño escribe `CONFIRMAR ORD-XXX` por WhatsApp admin | Mismo resultado (legacy) |

---

## Checklist E2E

- [ ] Cliente escribe al bot → respuesta automática
- [ ] `GET /whatsbot/conversations` devuelve conversaciones
- [ ] `POST /whatsbot/messages` → cliente recibe por Twilio
- [ ] Pedido → notifica admin WhatsApp legacy
- [ ] `POST /whatsbot/orders/{id}/approve` → cliente notificado
- [ ] Dueño aprueba desde `ADMIN_WHATSAPP_NUMBER` → sigue funcionando
- [ ] Sheets deshabilitado → OK (`GOOGLE_SHEETS_ENABLED=false`)
- [ ] `PUT /whatsbot/business/menu` → cliente ve menú nuevo en WhatsApp
- [ ] `PUT /whatsbot/business/intents` → bot reacciona a keyword nueva
- [ ] `PUT /whatsbot/business/prompts` → cliente recibe el texto nuevo

Automatizado en `scripts/validate_system.py`.

---

## Tiempo real (WebSocket)

El backend emite eventos WebSocket en cuanto persiste cada mensaje o pedido.

| Canal | Cuándo | Eventos |
|-------|--------|---------|
| **WebSocket** `WS /whatsbot/ws?token=JWT` | Cliente conectado, `REALTIME_ENABLED=true` | `message.new`, `order.pending`, `message.status` |
| **FCM/APNs** | App background/cerrada, `FCM_ENABLED=true` | Push si no hay WS activo |
| **REST sync** | Reconexión o vuelta de red | `?since=` / `?after_id=` |

### Variables `.env`

```env
REALTIME_ENABLED=true
WS_HEARTBEAT_SECONDS=30
FCM_ENABLED=false
FCM_SERVICE_ACCOUNT_JSON_PATH=credentials/firebase-service-account.json
```

Migración de estado de mensajes: `python scripts/migrate_message_status.py`

---

## Estructura del proyecto

| Carpeta | Rol |
|---------|-----|
| `api/` | FastAPI: webhook Twilio, auth JWT, REST |
| `chatbot/` | Gateway + lógica conversacional |
| `config/` | Settings, intents, prompts |
| `models/` | SQLAlchemy: business, conversation, message, order, menu |
| `services/` | Negocio, conversaciones, pedidos, notificaciones, Sheets opcional |
| `infrastructure/` | BD, cache Redis, Twilio |
| `scripts/` | migrate, onboard, validate_* |
| `docs/` | Guías de arquitectura y negocios |

---

## Documentación

- `docs/ARCHITECTURE.md` — diagrama y flujos
- `docs/GUIA_NEGOCIOS.md` — alta de negocio paso a paso
- `docs/INCREMENTAL_GUIDE.md` — registro por fase (desarrolladores)

---

## Resultados de validación

Ejecutar desde la raíz del proyecto:

```bash
python scripts/validate_chatbot.py
python scripts/validate_api.py
python scripts/migrate_message_status.py   # si BD existía antes de Fase 11.5
python scripts/validate_system.py
python -m pytest tests/ -q
```

Salida esperada: **0 fallos** en scripts de validación, **tests passed** en pytest.

`GET /health` incluye `realtime_enabled` y `fcm_enabled`.
