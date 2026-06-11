# Guía de negocios — alta fácil

Cómo dar de alta un restaurante (negocio) en WhatsBot SaaS **sin tocar código del chatbot**.

---

## Antes de empezar

Necesitas:

1. Backend corriendo (`python -m api.main` en `final_system/`).
2. Base de datos migrada (`python scripts/migrate_db.py`).
3. Un número Twilio WhatsApp **distinto** por negocio (cada local tiene su propia línea del bot).

---

## Negocio default (el primero)

Si migraste desde el bot original, el negocio **default** ya existe con los datos del `.env` legacy:

| Campo | Origen legacy |
|-------|----------------|
| Nombre | `RESTAURANT_NAME` → `DEFAULT_BUSINESS_NAME` |
| Línea del bot | `TWILIO_WHATSAPP_FROM` |
| Admin (confirmaciones) | `ADMIN_WHATSAPP_NUMBER` |

Para asegurarlo o recrearlo:

```bash
cd final_system
python scripts/onboard_business.py --default
```

Salida esperada: `Default business ready: default`

El dueño se autentica con `POST /auth/login` usando **ID del negocio:** `default` y el PIN de `WHATSBOT_OWNER_PIN`.

---

## Alta de un negocio nuevo

### Paso 1 — Crear el negocio en la base de datos

```bash
cd final_system
python scripts/onboard_business.py \
  --id pizzeria-norte \
  --name "Pizzería Norte" \
  --twilio-from "whatsapp:+573009998877" \
  --admin "whatsapp:+573001112233"
```

| Parámetro | Qué es |
|-----------|--------|
| `--id` | Identificador único (sin espacios). Lo usa la app para login. |
| `--name` | Nombre visible en la app. |
| `--twilio-from` | Número WhatsApp del bot en Twilio (formato `whatsapp:+57...`). |
| `--admin` | WhatsApp personal del dueño para confirmar pedidos (legacy). |

El script copia menú, intents y mensajes desde `config/*` como plantilla inicial.

### Paso 2 — Configurar Twilio

En Twilio Console, apunta el webhook del **nuevo número** a:

```
POST {API_PUBLIC_URL}/webhook
```

Ejemplo con ngrok: `https://abc123.ngrok-free.app/webhook`

### Paso 3 — Autenticarse en la API

```http
POST /auth/login
Content-Type: application/json

{"business_id": "pizzeria-norte", "pin": "<WHATSBOT_OWNER_PIN del .env>"}
```

Respuesta: `access_token` JWT. Úsalo como `Authorization: Bearer <token>` en todas las rutas REST y WebSocket.

### Paso 4 — Probar

1. Desde un teléfono cliente, escribe al número Twilio del negocio nuevo.
2. Debe responder el bot con la bienvenida.
3. `GET /whatsbot/conversations` con el JWT devuelve el chat del cliente.
4. Haz un pedido de prueba y confírmalo con `POST /whatsbot/orders/{id}/approve` o desde el WhatsApp admin.

---

## Varios negocios en un solo servidor

| Concepto | Cómo funciona |
|----------|----------------|
| Identificación | Twilio envía el campo **To** → el sistema busca `twilio_whatsapp_from` en la tabla `business`. |
| Datos aislados | Menú, intents, prompts, chats y pedidos van por `business_id`. |
| Auth API | Cada dueño se autentica con su `business_id` + PIN → JWT. |
| Secrets | Twilio y PIN **solo** en el servidor (`.env`). |

---

## Comandos útiles

```bash
# Migrar / crear tablas
python scripts/migrate_db.py

# Solo negocio default (legacy)
python scripts/onboard_business.py --default

# Negocio nuevo
python scripts/onboard_business.py --id mi-local --name "Mi Local" \
  --twilio-from "whatsapp:+57..." --admin "whatsapp:+57..."

# Validar que todo funciona
python scripts/validate_system.py
```

---

## Problemas frecuentes

| Problema | Solución |
|----------|----------|
| El bot no responde al cliente | Revisa webhook Twilio → `{API_PUBLIC_URL}/webhook` |
| Mensajes van al negocio equivocado | El número **To** debe coincidir con `twilio_whatsapp_from` del negocio |
| `POST /auth/login` falla | Verifica que la API esté encendida (`python -m api.main`) |
| PIN incorrecto | Revisa `WHATSBOT_OWNER_PIN` en `.env` |

Para editar menú e intents después del alta, usar `PUT /whatsbot/business/menu`, `PUT /whatsbot/business/intents` y `PUT /whatsbot/business/prompts` con el JWT del negocio.
