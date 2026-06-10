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

En la app Flutter, el dueño entra con **ID del negocio:** `default` y el PIN de `WHATSBOT_OWNER_PIN`.

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

### Paso 3 — Login en la app

1. Abre WhatsBot en el móvil.
2. **ID del negocio:** `pizzeria-norte` (el `--id` que usaste).
3. **PIN:** el valor de `WHATSBOT_OWNER_PIN` en el `.env` del servidor.
4. Entra y personaliza menú, intents y mensajes desde Ajustes.

### Paso 4 — Probar

1. Desde un teléfono cliente, escribe al número Twilio del negocio nuevo.
2. Debe responder el bot con la bienvenida.
3. El chat aparece en la app del dueño.
4. Haz un pedido de prueba y confírmalo desde la app o desde el WhatsApp admin.

---

## Varios negocios en un solo servidor

| Concepto | Cómo funciona |
|----------|----------------|
| Identificación | Twilio envía el campo **To** → el sistema busca `twilio_whatsapp_from` en la tabla `business`. |
| Datos aislados | Menú, intents, prompts, chats y pedidos van por `business_id`. |
| App Flutter | Cada dueño entra con su `business_id` + PIN. |
| Secrets | Twilio y PIN **solo** en el servidor (`.env`), nunca en Flutter. |

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
| App no conecta | Verifica `api_config.dart` y que la API esté encendida |
| PIN incorrecto | Revisa `WHATSBOT_OWNER_PIN` en `final_system/.env` |

Para editar menú e intents después del alta, ver `docs/GUIA_EDICION_APP.md`.
