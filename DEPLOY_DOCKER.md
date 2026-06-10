# Producción con Docker — WhatsBot

Guía sencilla para desplegar el **backend** (API + webhook Twilio + WebSocket) en un VPS con Docker. La app Flutter se compila en tu PC y apunta a la URL pública del servidor.

**Tiempo estimado:** 30–45 min (con dominio y DNS listos).

---

## Qué vas a tener al final

```
Internet
   │
   ▼
[Caddy HTTPS :443]  ← dominio público (ej. api.tunegocio.com)
   │
   ▼
[API FastAPI :5000]  ← webhook Twilio + REST + WebSocket
   │
   ▼
[PostgreSQL]         ← chats, mensajes, pedidos, negocios
```

| Componente | Dónde corre |
|------------|-------------|
| Backend + BD | VPS con Docker |
| App Flutter | Teléfonos Android/iOS (APK/IPA que compilas tú) |
| Twilio | Webhook → `https://tu-dominio/webhook` |
| Firebase (opcional) | Push con app cerrada — ver sección final |

---

## Requisitos previos

1. **VPS** (Ubuntu 22/24, 1 GB RAM mínimo, 2 GB recomendado): DigitalOcean, Hetzner, AWS Lightsail, etc.
2. **Dominio** apuntando al VPS (registro A → IP del servidor). Ej: `api.tunegocio.com`.
3. **Docker** instalado en el VPS:

   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   # Cierra sesión y vuelve a entrar
   ```

4. **Credenciales listas:**
   - Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
   - `ADMIN_WHATSAPP_NUMBER` (confirmación de pedidos)
   - PIN del dueño para la app: elige un `WHATSBOT_OWNER_PIN` seguro
   - `JWT_SECRET_KEY` largo y aleatorio (32+ caracteres)

---

## Paso 1 — Clonar el proyecto en el VPS

```bash
cd ~
git clone https://github.com/TU_USUARIO/final_system.git
cd final_system
```

(Si subes el zip, descomprímelo en `~/final_system`.)

---

## Paso 2 — Crear los archivos Docker

Crea estos **3 archivos** en la raíz de `final_system/` (junto a `README.md`).

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data credentials client_messages_log

ENV HOST=0.0.0.0
ENV PORT=5000
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

### `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: whatsbot
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: whatsbot
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U whatsbot -d whatsbot"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./data:/app/data
      - ./credentials:/app/credentials
    expose:
      - "5000"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      DOMAIN: ${DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api

volumes:
  pgdata:
  caddy_data:
  caddy_config:
```

### `Caddyfile`

Reemplaza `api.tunegocio.com` por tu dominio real:

```
api.tunegocio.com {
    reverse_proxy api:5000
}
```

Caddy obtiene el certificado HTTPS automáticamente y soporta **WebSocket** (tiempo real) sin configuración extra.

---

## Paso 3 — Archivo `.env` de producción

Copia la plantilla y edítala:

```bash
cp .env.example .env
nano .env
```

**Valores mínimos para Docker** (ajusta todo lo marcado con `←`):

```env
# --- Público ---
DOMAIN=api.tunegocio.com                                    ← tu dominio
API_PUBLIC_URL=https://api.tunegocio.com                    ← mismo, con https
CORS_ORIGINS=*

# --- Servidor ---
HOST=0.0.0.0
PORT=5000
DEBUG=false

# --- PostgreSQL (nombre del servicio en docker-compose) ---
POSTGRES_PASSWORD=una_clave_larga_y_segura                  ← inventa una
DATABASE_URL=postgresql://whatsbot:una_clave_larga_y_segura@db:5432/whatsbot

# --- Twilio ---
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+573001234567
TWILIO_REST_WEBHOOK_REPLIES=0

# --- Admin (confirmación pedidos por WhatsApp personal) ---
ADMIN_WHATSAPP_NUMBER=whatsapp:+573009876543

# --- Auth app Flutter ---
JWT_SECRET_KEY=genera_una_clave_aleatoria_de_32_caracteres_minimo
JWT_EXPIRE_MINUTES=1440
WHATSBOT_OWNER_PIN=tu_pin_secreto_para_la_app               ← el dueño usa esto al login

# --- Negocio ---
DEFAULT_BUSINESS_ID=default
DEFAULT_BUSINESS_NAME=Mi Negocio

# --- Google Sheets (opcional, dejar desactivado al inicio) ---
GOOGLE_SHEETS_ENABLED=false

# --- Rutas runtime ---
STATE_PERSIST_PATH=data/user_states.json
PARSER_ERROR_LOG_PATH=data/parser_errors.jsonl
FLOWS_PATH=flows/restaurant_flow.json

# --- Tiempo real (Fase 11) ---
REALTIME_ENABLED=true
WS_HEARTBEAT_SECONDS=30
FCM_ENABLED=false

# --- Legacy (rellena JWT_SECRET_KEY también aquí si usas SECRET_KEY en algún script) ---
SECRET_KEY=misma_clave_que_JWT_SECRET_KEY
```

> **Importante:** `DATABASE_URL` usa el host `db` (nombre del servicio en `docker-compose.yml`), no `localhost`.

Si usas Google Sheets en producción, copia el JSON a `credentials/google-service-account.json` en el servidor y activa `GOOGLE_SHEETS_ENABLED=true`.

---

## Paso 4 — Levantar los contenedores

```bash
cd ~/final_system
docker compose up -d --build
```

Comprueba que todo está arriba:

```bash
docker compose ps
docker compose logs -f api    # Ctrl+C para salir
curl -s https://api.tunegocio.com/health | python3 -m json.tool
```

Respuesta esperada (aprox.):

```json
{
  "status": "ok",
  "realtime_enabled": true,
  "fcm_enabled": false
}
```

---

## Paso 5 — Inicializar la base de datos (solo la primera vez)

Estos comandos crean tablas, columnas de ticks y el negocio `default`:

```bash
docker compose exec api python scripts/migrate_db.py --postgres
docker compose exec api python scripts/onboard_business.py --default
```

**No hace falta repetirlos** en cada reinicio. Solo si borras el volumen de PostgreSQL o despliegas en un servidor nuevo.

Verificación rápida:

```bash
docker compose exec api python scripts/validate_system.py
```

---

## Paso 6 — Configurar Twilio

En [Twilio Console](https://console.twilio.com/) → **Messaging** → tu número WhatsApp → **When a message comes in**:

| Campo | Valor |
|-------|--------|
| URL | `https://api.tunegocio.com/webhook` |
| Método | `POST` |

Alias compatible: `https://api.tunegocio.com/bot`

Prueba: envía un WhatsApp al número del bot. Debe guardarse en BD y, si tienes la app abierta, aparecer al instante.

---

## Paso 7 — App Flutter apuntando a producción

En **tu PC** (no en el VPS), edita:

`whatsbot_app/lib/config/api_config.dart`

```dart
static const String apiBaseUrl = 'https://api.tunegocio.com';
```

Compila e instala en el teléfono:

```bash
cd whatsbot_app
flutter pub get
flutter build apk --release
```

El APK queda en:

`whatsbot_app/build/app/outputs/flutter-apk/app-release.apk`

Cópialo al teléfono e instálalo. Login:

| Campo | Valor |
|-------|--------|
| Negocio | `default` |
| PIN | el `WHATSBOT_OWNER_PIN` de tu `.env` |

---

## Paso 8 — Prueba end-to-end

1. App abierta en el teléfono → login OK.
2. Cliente escribe al WhatsApp del bot → mensaje aparece en la app sin refrescar.
3. Dueño responde desde la app → cliente lo recibe por WhatsApp.
4. Pedido de prueba → notificación al admin → aprobar desde app o por WhatsApp admin.
5. Ajustes → editar menú/mensajes → guardar.

Si el WebSocket falla pero el REST funciona, revisa que `API_PUBLIC_URL` sea **HTTPS** y que Caddy esté corriendo (`docker compose logs caddy`).

---

## Comandos útiles del día a día

| Acción | Comando |
|--------|---------|
| Ver logs API | `docker compose logs -f api` |
| Reiniciar API | `docker compose restart api` |
| Actualizar código | `git pull && docker compose up -d --build` |
| Parar todo | `docker compose down` |
| Parar y borrar BD | `docker compose down -v` ⚠️ borra datos |
| Entrar al contenedor | `docker compose exec api bash` |
| Backup PostgreSQL | `docker compose exec db pg_dump -U whatsbot whatsbot > backup.sql` |

---

## Firewall del VPS

Abre solo lo necesario:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

No expongas el puerto 5000 ni 5432 a internet; Caddy y la red interna de Docker se encargan.

---

## Push con app cerrada (opcional — Firebase)

Por defecto `FCM_ENABLED=false`. Con eso:

- **App abierta:** tiempo real por WebSocket ✓
- **App en segundo plano:** notificaciones locales (limitado)
- **App cerrada:** sin push del sistema

Para paridad total con WhatsApp cuando la app está muerta:

1. Crea proyecto en [Firebase Console](https://console.firebase.com/).
2. Android: descarga `google-services.json` → `whatsbot_app/android/app/`.
3. Servidor: descarga JSON de cuenta de servicio → `credentials/firebase-service-account.json` en el VPS.
4. En `.env` del servidor:

   ```env
   FCM_ENABLED=true
   FCM_SERVICE_ACCOUNT_JSON_PATH=credentials/firebase-service-account.json
   ```

5. `docker compose restart api` y recompila la app Flutter.

Detalle extendido: `docs/FLUTTER_APP.md` (sección Push FCM/APNs).

---

## Alta de un segundo negocio

```bash
docker compose exec api python scripts/onboard_business.py \
  --id pizzeria \
  --name "Pizzería Centro" \
  --twilio-from "whatsapp:+573001112223" \
  --admin "whatsapp:+573009998877"
```

Configura el webhook de Twilio del **nuevo número** a la misma URL (`/webhook`). El dueño hace login en la app con `business_id` = `pizzeria`.

Más contexto: `docs/GUIA_NEGOCIOS.md`.

---

## Solución de problemas

| Síntoma | Qué revisar |
|---------|-------------|
| `502` en el dominio | `docker compose logs api` — ¿API arrancó? ¿BD lista? |
| Twilio no recibe respuesta | URL webhook HTTPS correcta; `API_PUBLIC_URL` coincide con dominio |
| App no conecta | `api_config.dart` con HTTPS; no uses IP directa si Caddy exige dominio |
| WS no conecta (icono nube) | `REALTIME_ENABLED=true`; dominio con `wss://`; Caddy delante de API |
| Error columna `status` | `docker compose exec api python scripts/migrate_db.py --postgres` |
| Login falla | `WHATSBOT_OWNER_PIN` en `.env`; negocio `default` creado con onboard |
| Cambios no persisten | Volúmenes `./data` y `pgdata` montados; no uses `docker compose down -v` sin querer |

---

## Checklist rápido antes de dar por bueno producción

- [ ] `curl https://tu-dominio/health` → `status: ok`
- [ ] `migrate_db.py --postgres` + `onboard_business.py --default` ejecutados una vez
- [ ] Webhook Twilio → `POST https://tu-dominio/webhook`
- [ ] `JWT_SECRET_KEY` y `WHATSBOT_OWNER_PIN` no son los de ejemplo
- [ ] `POSTGRES_PASSWORD` fuerte y coincide en `DATABASE_URL`
- [ ] App Flutter con `apiBaseUrl` HTTPS de producción
- [ ] Prueba manual cliente → app → respuesta → pedido
- [ ] Backup de `pgdata` o `pg_dump` programado (recomendado)

---

## Resumen en 6 líneas

1. Clona repo en VPS → crea `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `.env`.
2. `docker compose up -d --build`
3. `docker compose exec api python scripts/migrate_db.py --postgres`
4. `docker compose exec api python scripts/onboard_business.py --default`
5. Twilio webhook → `https://tu-dominio/webhook`
6. Flutter `apiBaseUrl` = mismo dominio → `flutter build apk --release` → instalar y probar.
