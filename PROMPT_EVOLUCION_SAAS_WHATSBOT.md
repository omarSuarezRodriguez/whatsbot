# PROMPT MAESTRO — SaaS Multi-Negocio + WhatsBot (Flutter)

> **Cuándo usar:** La carpeta ya contiene el proyecto Python del chatbot (en la raíz). Este documento es la **única fuente de verdad**.
>
> **Objetivo:** Migrar a `final_system/` sin romper el bot. Al terminar: backend Python + **app móvil Flutter WhatsBot** (UI tipo WhatsApp), totalmente funcional.

---

## 0. CONTEXTO DEL PRODUCTO

### Qué existe hoy
- Chatbot WhatsApp en **Python**, en producción (Twilio).
- `TWILIO_WHATSAPP_FROM` = WhatsApp público del **bot del negocio** (lo ven los clientes).
- `ADMIN_WHATSAPP_NUMBER` = WhatsApp personal del **dueño** (confirmación de pedidos legacy).
- Flujo crítico: pedido → bot notifica al admin → admin confirma → bot responde al cliente.

### Qué se construye

| Componente | Tecnología | Rol |
|------------|------------|-----|
| **Chatbot** | Python (caja negra) | Atiende clientes automáticamente vía Twilio |
| **API backend** | Python FastAPI (preferido) | Webhook Twilio, BD, JWT, REST para la app |
| **WhatsBot** | **Flutter (Android/iOS)** | Dueño gestiona el bot: chats, pedidos, menú — **UI clon de WhatsApp** |
| **Google Sheets** | Opcional | Espejo editable; **no** es fuente de verdad |

### Prohibición explícita

| Permitido | Prohibido |
|-----------|-----------|
| API REST/JSON para la app | ❌ UI web para WhatsBot (HTML, React, Vue, panel web) |
| Flutter Android + iOS | ❌ Flutter Web como producto principal |
| Dashboard futuro (otro proyecto) | ❌ Sustituir la app móvil por “API documentada sin app” |

### Terminología
- **`business` / `negocio`** — nunca `restaurant` en código nuevo.
- **WhatsBot** — solo la app Flutter del dueño.

### Modelo de números

```
Cliente     → escribe a TWILIO_WHATSAPP_FROM (bot del negocio)
Dueño       → opera en app Flutter WhatsBot (misma línea del bot vía API)
Dueño       → también puede confirmar por ADMIN_WHATSAPP_NUMBER (legacy, se mantiene)
```

---

## 1. REGLAS ABSOLUTAS

| # | Regla |
|---|-------|
| 1 | Cero regresión del chatbot tras cada fase |
| 2 | No reescribir intents ni algoritmos de respuesta |
| 3 | Gateway único: `chatbot/gateway.py` → `handle_incoming_message()` |
| 4 | Config en máx. 5 archivos en `config/` + secrets en `.env` |
| 5 | Todo el sistema nuevo en `final_system/` |
| 6 | **WhatsBot = Flutter móvil**, UI indistinguible de WhatsApp en UX |
| 7 | Cada mensaje cliente guardado en BD → visible en la app |
| 8 | Google Sheets opcional y no bloqueante |
| 9 | Comentarios en cada frontera: qué entra, qué sale, por qué |
| 10 | Al cerrar cada fase: nota breve en `docs/INCREMENTAL_GUIDE.md` |
| 11 | **Credenciales del legacy:** tomar del proyecto del bot analizado; no inventar ni pedir al usuario lo que ya existe en el repo |
| 12 | **Config por negocio:** menú, intents y textos editables **solo desde app Flutter**; `config/*` = defaults para nuevos negocios |

---

## 1.b MIGRACIÓN DE CREDENCIALES Y CONFIG (desde el bot original)

> El proyecto del bot en la **raíz** es la fuente de verdad para conexiones, URLs y secrets.

### Qué debe hacer el agente

| Acción | Detalle |
|--------|---------|
| **Buscar en Fase 0** | `.env`, `.env.local`, `config.py`, `settings.py`, constantes en código, `credentials.json`, JSON de Google, URLs de webhook/ngrok en README o scripts |
| **Inventariar** | Tabla: variable legacy \| dónde está \| variable en `final_system/.env` \| obligatoria/opcional |
| **Migrar en Fase 1+** | Crear `final_system/.env` **copiando valores reales** desde el legacy (mismo workspace). Mapear nombres viejos → nombres nuevos del maestro |
| **No inventar** | Si Twilio/BD/Sheets ya existen en el bot, usar esos valores — no placeholders ficticios |
| **Solo preguntar al usuario** | Si tras buscar en todo el repo **falta** un valor obligatorio y no hay default seguro |
| **Flutter** | `api_config.dart` → `API_PUBLIC_URL` tomada del legacy (variable `BASE_URL`, `WEBHOOK_URL`, ngrok en README, puerto en `run.py`, etc.) |
| **Negocio default** | Primer negocio en BD con `twilio_whatsapp_from` y `admin_whatsapp_number` leídos del `.env` legacy |

### Seguridad en el chat

- **Sí:** leer `.env` y archivos de credenciales **en disco** y escribir en `final_system/.env` (gitignore).
- **No:** pegar tokens, passwords ni SIDs completos en mensajes de chat; en tablas usar `***` o últimos 4 caracteres.
- **Sí:** documentar en README *qué* variables se migraron (solo nombres).

### Archivos típicos a revisar (lista no exhaustiva)

```
.env, .env.example, config/*.py, settings.py, constants.py,
credentials.json, service_account*.json, google_sheets*.json,
run.py, main.py, app.py, README, docker-compose.yml
```

---

## 2. FASE 0 — ANÁLISIS (sin modificar código)

```
[ ] 2.1  Inventario de TODOS los archivos
[ ] 2.2  Entry points (webhook, main, scripts)
[ ] 2.3  Dependencias (requirements, imports)
[ ] 2.4  Twilio, BD, Redis, OpenAI, Google Sheets
[ ] 2.5  Variables .env, archivos JSON de credenciales y valores hardcoded
[ ] 2.5b MAPA DE CREDENCIALES: cada secret/config del legacy → destino en final_system
[ ] 2.6  Flujo mensaje cliente → respuesta
[ ] 2.7  Flujo confirmación ADMIN_WHATSAPP_NUMBER
[ ] 2.8  Uso de Google Sheets hoy (rutas a JSON/IDs de hoja en el repo)
[ ] 2.9  Grafo de dependencias
[ ] 2.10 Riesgos de migración
[ ] 2.11 URL pública del backend si existe (ngrok, Render, Railway, HOST, PORT)
```

**Entregables:** tabla archivos, mermaid flujos, **mapa de credenciales** (sin exponer secrets en chat), riesgos, entry points.

**No crear `final_system/` en Fase 0.**

---

## 3. ARQUITECTURA `final_system/`

```
final_system/
├── .env.example
├── README.md                      # Backend + Flutter (dos secciones)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INCREMENTAL_GUIDE.md
│   ├── WHATSAPP_FLOWS.md
│   ├── FLUTTER_APP.md             # Cómo compilar y conectar la app
│   ├── GUIA_NEGOCIOS.md           # Alta de negocios
│   └── GUIA_EDICION_APP.md        # Dueño: editar menú/intents/mensajes en la app
│
├── config/                        # 5 archivos editables (+ sheets opcional)
│   ├── settings.py
│   ├── bot_config.py
│   ├── intents.py
│   ├── prompts.py
│   └── sheets_config.py
│
├── chatbot/                       # Caja negra
│   ├── gateway.py                 # ÚNICA puerta
│   └── ...
│
├── api/                           # Solo backend (JSON), consumido por Flutter
│   ├── main.py
│   ├── routes/
│   │   ├── whatsapp.py            # Webhook Twilio → gateway
│   │   ├── whatsbot.py            # REST app móvil (auth, chats, mensajes, pedidos)
│   │   ├── businesses.py
│   │   ├── menus.py
│   │   ├── orders.py
│   │   ├── auth.py
│   │   └── sheets.py
│   └── middleware/auth.py
│
├── whatsbot_app/                  # ← APP FLUTTER (NO web)
│   ├── pubspec.yaml
│   ├── lib/
│   │   ├── main.dart
│   │   ├── config/api_config.dart # URL del backend (sin secrets Twilio aquí)
│   │   ├── theme/whatsapp_theme.dart
│   │   ├── services/api_client.dart
│   │   ├── models/
│   │   └── screens/
│   │       ├── login_screen.dart
│   │       ├── chats_list_screen.dart    # Como lista de chats WA
│   │       ├── chat_screen.dart          # Burbujas, input abajo, ticks
│   │       ├── order_actions_bar.dart    # Aprobar / Rechazar en chat
│   │       ├── settings_screen.dart      # Ajustes + acceso a editores
│   │       ├── menu_editor_screen.dart   # Editar menú del negocio
│   │       ├── intents_editor_screen.dart
│   │       └── prompts_editor_screen.dart  # Textos del bot
│   └── README.md
│
├── services/
│   ├── business_service.py
│   ├── menu_service.py
│   ├── order_service.py
│   ├── conversation_service.py    # Persistir y listar mensajes
│   ├── notification_service.py
│   ├── analytics_service.py
│   └── sheets_sync_service.py
│
├── models/
│   ├── business.py
│   ├── conversation.py
│   ├── message.py
│   ├── menu.py
│   ├── order.py
│   └── customer.py
│
├── infrastructure/
│   ├── database.py
│   ├── cache.py
│   └── twilio_client.py
│
├── scripts/
│   ├── validate_chatbot.py
│   ├── validate_api.py
│   ├── validate_system.py
│   └── onboard_business.py
│
└── tests/
    ├── test_chatbot_gateway.py
    ├── test_order_confirmation_flow.py
    ├── test_whatsbot_api.py
    └── test_api.py
```

### Integración webhook → bot

```python
# api/routes/whatsapp.py
# 1. Twilio POST → 2. normalizar → 3. gateway → 4. respuesta Twilio
# 5. conversation_service.save_incoming() → Flutter lo ve
from chatbot.gateway import handle_incoming_message
```

```python
# chatbot/gateway.py
# Entrada:  {phone, message, timestamp, business_id?, channel?, metadata?}
# Salida:   {response_text, media?, actions?}
def handle_incoming_message(payload: dict) -> dict:
    ...
```

---

## 4. WhatsBot — APP FLUTTER (especificación UI/UX)

### Principio
El dueño debe sentir que **está usando WhatsApp del número del bot**, no un panel administrativo.

### Pantallas obligatorias (MVP)

| Pantalla | Comportamiento tipo WhatsApp |
|----------|------------------------------|
| **Login** | Email/teléfono + contraseña o código → JWT |
| **Lista de chats** | Avatar, nombre/teléfono, último mensaje, hora, badge no leídos, barra verde superior |
| **Chat** | Fondo `#ECE5DD`, burbujas grises (entrante) y verdes `#DCF8C6` (saliente), hora en burbuja, input + botón enviar abajo |
| **Pedido pendiente** | Banner o barra con **Aprobar** / **Rechazar** (misma lógica que `ADMIN_WHATSAPP_NUMBER`) |
| **Ajustes** | Acceso a configuración del negocio (ver abajo) |
| **Editar menú** | Lista de productos del **su** negocio: agregar, editar precio/nombre, activar/desactivar — **solo desde la app** |
| **Editar intents** | Palabras clave y frases que activan cada flujo del **su** negocio — **solo desde la app** |
| **Editar textos del bot** | Mensajes de bienvenida, confirmación, errores del **su** negocio — **solo desde la app** |

### Edición por negocio — OBLIGATORIO (desde la app, no desde código)

El dueño **no debe editar archivos Python** para su negocio. Toda configuración operativa va en **BD por `business_id`** y se gestiona en Flutter.

| Qué edita el dueño | Dónde en la app | Persistencia |
|--------------------|-----------------|--------------|
| Menú (productos, precios) | Pantalla **Menú** (lista + formulario simple) | Tabla `menu_items` (o equivalente) por `business_id` |
| Intents (keywords, prioridad) | Pantalla **Intents** (lista editable) | Tabla `business_intents` o JSON en `business_config` |
| Textos al cliente | Pantalla **Mensajes** (campos: bienvenida, pedido, error, etc.) | Tabla `business_prompts` o JSON en `business_config` |
| Sheets on/off | Ajustes → toggle (llama API) | `business.sheets_enabled` + `sheets_config` por negocio |

**Archivos `config/intents.py` y `config/prompts.py`:**
- Son **plantillas por defecto** del sistema (fallback).
- Al crear un negocio nuevo (`onboard_business`), **copiar** defaults a BD del negocio.
- El **gateway** carga primero config del negocio en BD; si falta un campo, usa default de `config/*`.

**Prohibido como flujo principal:** decirle al dueño “edita `config/prompts.py`”. Eso es solo para ti/desarrollador en mejoras globales.

### Tema visual (obligatorio)

```dart
// Referencia — whatsapp_theme.dart
// AppBar / header: #075E54
// Accent / send: #128C7E
// Burbbuja saliente: #DCF8C6
// Burbuja entrante: #FFFFFF
// Fondo chat: #ECE5DD
// Tipografía: sistema, tamaños similares a WhatsApp
```

**No copiar assets con trademark de Meta** (logo oficial, iconos exactos). Sí copiar **layout y colores**.

### Conexión con backend

- Toda acción Flutter → `api/routes/whatsbot.py` (HTTPS + JWT).
- Enviar mensaje manual: `POST /whatsbot/messages` → API → `twilio_client` → `TWILIO_WHATSAPP_FROM`.
- Listar chats: `GET /whatsbot/conversations`.
- Historial: `GET /whatsbot/conversations/{id}/messages`.
- Confirmar pedido: `POST /whatsbot/orders/{id}/approve` o `reject`.

### Tiempo real (MVP pragmático)

- **Mínimo:** polling cada 3–5 s en pantalla de chat activa.
- **Opcional Fase 9+:** WebSocket; no bloquear MVP por esto.

### Config de la app

`whatsbot_app/lib/config/api_config.dart`:

```dart
// Editar solo la URL pública de tu API (ngrok/producción)
static const String apiBaseUrl = 'https://tu-api.com';
```

**Nunca** poner `TWILIO_AUTH_TOKEN` en Flutter.

---

## 5. API WhatsBot (backend para Flutter) — contrato mínimo

Documentar en `docs/FLUTTER_APP.md`:

| Método | Ruta | Uso en Flutter |
|--------|------|----------------|
| POST | `/auth/login` | Login |
| GET | `/whatsbot/conversations` | Lista de chats |
| GET | `/whatsbot/conversations/{id}/messages` | Pantalla chat |
| POST | `/whatsbot/messages` | Enviar como bot |
| GET | `/whatsbot/orders/pending` | Badge / filtros |
| POST | `/whatsbot/orders/{id}/approve` | Botón verde |
| POST | `/whatsbot/orders/{id}/reject` | Botón rojo |
| GET | `/whatsbot/business/me` | Datos del negocio |
| GET | `/whatsbot/business/menu` | Menú del negocio (JWT) |
| PUT | `/whatsbot/business/menu` | Guardar menú desde la app |
| GET | `/whatsbot/business/intents` | Intents del negocio |
| PUT | `/whatsbot/business/intents` | Guardar intents desde la app |
| GET | `/whatsbot/business/prompts` | Textos del bot del negocio |
| PUT | `/whatsbot/business/prompts` | Guardar textos desde la app |

Cada handler con comentario: entrada, salida, efecto en Twilio/BD/bot. Tras `PUT`, el **siguiente** mensaje al bot debe usar la config nueva (sin reiniciar servidor).

Documentar en `docs/GUIA_EDICION_APP.md` (tutorial para el dueño, lenguaje simple).

---

## 6. MULTI-NEGOCIO

```
TWILIO_WHATSAPP_FROM → business_id
       ↓
webhook → gateway (lee menú + intents + prompts de BD por business_id; fallback config/*)
       ↓
conversation/message/order con business_id
       ↓
Flutter: JWT incluye business_id del dueño
```

---

## 7. CONFIGURACIÓN — 5 archivos + `.env`

| Archivo | Contenido |
|---------|-----------|
| `.env` | **Migrado del bot original** (Twilio, BD, JWT, Sheets, `API_PUBLIC_URL`). El agente lo rellena leyendo el repo; el usuario no reescribe lo que ya existe |
| `config/settings.py` | Puertos, CORS para app móvil, timeouts |
| `config/bot_config.py` | Sesión bot, horarios |
| `config/intents.py` | **Defaults globales** (semilla al crear negocio; el dueño edita en la app) |
| `config/prompts.py` | **Defaults globales** (semilla; el dueño edita en la app) |
| `config/sheets_config.py` | Sync opcional (global); override por negocio en BD |

**Edición del dueño:** siempre vía app Flutter → API `PUT /whatsbot/business/*` → BD. Ver `docs/GUIA_EDICION_APP.md`.

### `.env.example` (añadir)

```env
API_PUBLIC_URL=https://tu-dominio-o-ngrok.ngrok-free.app
CORS_ORIGINS=*

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=whatsapp:+...
ADMIN_WHATSAPP_NUMBER=whatsapp:+...

DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379

JWT_SECRET_KEY=
JWT_EXPIRE_MINUTES=1440

GOOGLE_SHEETS_ENABLED=false
GOOGLE_SERVICE_ACCOUNT_JSON_PATH=
GOOGLE_SHEET_ID_MENU=
GOOGLE_SHEET_ID_ORDERS=
```

---

## 8. GOOGLE SHEETS — OPCIONAL

- Fuente de verdad: PostgreSQL.
- `GOOGLE_SHEETS_ENABLED=false` → todo funciona.
- Sincronización desde API; opcional pantalla Ajustes en Flutter (solo llama API).

---

## 9. FASES DE MIGRACIÓN (orden obligatorio)

> Tras **cada** fase: `python scripts/validate_chatbot.py` (desde Fase 2). Si falla, la fase no cierra.

| Fase | Nombre | Qué hace |
|------|--------|----------|
| **0** | Análisis | Inventario, diagramas, riesgos. **Sin código.** |
| **1** | Scaffold | `final_system/` árbol, configs, `.env.example`, **`final_system/.env` copiado/adaptado del bot en raíz**, credenciales Google si existen |
| **2** | Gateway | Copiar chatbot + `gateway.py` + `validate_chatbot.py` |
| **3** | Config | Centralizar hardcoded → `config/*` (valores desde legacy, no inventados) |
| **4** | API webhook | FastAPI + `whatsapp.py` → gateway + guardar mensaje entrante en BD |
| **5** | Multi-negocio | Models (`business`, `conversation`, `message`, `order`, …) + CRUD API base |
| **6** | Pedidos + admin | Flujo legacy `ADMIN_WHATSAPP_NUMBER` + `notification_service` |
| **7** | API WhatsBot | `whatsbot.py`: auth, chats, mensajes, pedidos + **GET/PUT menú, intents, prompts por negocio** + gateway lee BD |
| **8** | Google Sheets | `sheets_sync_service` opcional |
| **9** | **Flutter WhatsBot** | UI WhatsApp + pantallas **Menú / Intents / Mensajes** (edición por negocio) + `GUIA_EDICION_APP.md` |
| **10** | Cierre | `validate_system.py`, README, `onboard_business.py`, checklist E2E |

### Detalle Fase 4 (importante)
Al recibir webhook, **además** de `handle_incoming_message`:
- Persistir mensaje en `conversation`/`message` para que Flutter lo muestre.

### Detalle Fase 9 (Flutter)
- Proyecto en `final_system/whatsbot_app/`.
- `api_config.dart` → `apiBaseUrl` = `API_PUBLIC_URL` del `.env` migrado (o URL detectada en legacy).
- `flutter analyze` sin errores críticos.
- Probar en emulador o dispositivo: login → ver chat → enviar mensaje → aprobar pedido mock/real.

### Detalle Fase 10
Checklist E2E:
- [ ] Cliente escribe al bot → respuesta automática
- [ ] Mensaje aparece en app Flutter
- [ ] Dueño responde desde Flutter → cliente recibe por Twilio
- [ ] Pedido → notifica admin WhatsApp legacy
- [ ] Dueño aprueba desde Flutter → cliente notificado
- [ ] Dueño aprueba desde `ADMIN_WHATSAPP_NUMBER` → sigue funcionando
- [ ] Sheets deshabilitado → OK
- [ ] Dueño edita menú en app → cliente ve menú nuevo en WhatsApp
- [ ] Dueño edita un intent en app → bot reacciona a la keyword nueva
- [ ] Dueño edita texto de bienvenida en app → cliente recibe el texto nuevo

---

## 10. MAPA DE INTEGRACIONES

```
Cliente (WhatsApp)
       ↓
TWILIO_WHATSAPP_FROM
       ↓
api/routes/whatsapp.py → gateway → chatbot/*
       ↓
conversation_service → PostgreSQL
       ↑
api/routes/whatsbot.py ←—— HTTP JSON ——→ whatsbot_app/ (Flutter)
       ↓
twilio_client (mensaje manual del dueño)

ADMIN_WHATSAPP_NUMBER ← notification_service (legacy confirmación)
```

---

## 11. ENTREGABLES FINALES

1. `final_system/` completo (Python + Flutter).
2. `README.md` con **dos bloques**: arrancar API + arrancar app (`flutter run`).
3. `docs/FLUTTER_APP.md` — URL API, login de prueba, capturas esperadas.
4. `docs/GUIA_NEGOCIOS.md` — alta de negocio (fácil, paso a paso).
5. `docs/GUIA_EDICION_APP.md` — tutorial dueño: editar **menú, intents y mensajes desde WhatsBot** (sin código).
6. `docs/INCREMENTAL_GUIDE.md` — para desarrolladores.
7. `scripts/validate_*.py` ejecutados con salida documentada.
8. **Sin ninguna UI web de WhatsBot.**

### Arranque rápido (plantilla)

```markdown
## Backend
1. cd final_system && pip install -r requirements.txt
2. .env — ya migrado desde el bot original en Fase 1; si falta algo, comparar con .env en la raíz del legacy
3. python scripts/migrate_db.py
4. python -m api.main
5. ngrok o dominio → webhook Twilio → /webhook

## App WhatsBot (Flutter)
1. cd final_system/whatsbot_app
2. Editar lib/config/api_config.dart → API_PUBLIC_URL
3. flutter pub get
4. flutter run

## Probar
1. Mensaje cliente al TWILIO_WHATSAPP_FROM
2. Abrir app → debe aparecer el chat
3. Aprobar pedido desde la app y desde ADMIN_WHATSAPP_NUMBER
4. En app: Menú → cambiar un producto → cliente ve cambio en WhatsApp
5. En app: Mensajes → cambiar bienvenida → probar con cliente
```

---

## 12. LO QUE NO DEBE HACER EL AGENTE

- ❌ Crear UI web para WhatsBot o “dashboard web del dueño”
- ❌ Entregar solo API “para que luego hagas la app”
- ❌ Microservicios, Kafka, RabbitMQ nuevos
- ❌ Reescribir intents
- ❌ Depender de Google Sheets
- ❌ Romper flujo `ADMIN_WHATSAPP_NUMBER`
- ❌ Poner secrets Twilio en Flutter
- ❌ Terminar sin app Flutter compilable
- ❌ Pedir al usuario credenciales que ya existen en el proyecto del bot sin haber buscado antes en todo el repo
- ❌ Dejar `final_system/.env` vacío si el legacy tenía `.env` con valores
- ❌ Documentar al dueño que edite `config/prompts.py` o `config/intents.py` para su negocio (debe ser la app)
- ❌ Entregar MVP sin pantallas Menú / Intents / Mensajes en Flutter

---

## 13. ORDEN DE EJECUCIÓN (resumen)

```
F0 Análisis
 → F1 Scaffold
 → F2 Gateway
 → F3 Config
 → F4 Webhook + persistir mensajes
 → F5 Multi-negocio + modelos
 → F6 Pedidos + admin legacy
 → F7 API REST + edición menú/intents/prompts por negocio (BD)
 → F8 Sheets opcional
 → F9 App Flutter (UI WhatsApp + editores en app)
 → F10 Validación + documentación
```

---

## 14. MÉTRICA DE ÉXITO

Un junior en su primer día puede:

1. Arrancar API y app Flutter con el README.
2. Ver en el móvil los mismos chats que llegan al bot.
3. Responder desde la app y el cliente lo recibe en WhatsApp.
4. Confirmar pedido desde la app **o** desde su WhatsApp personal (admin).
5. Dar de alta un negocio sin tocar código del chatbot.
6. Editar menú, intents y textos del bot **solo desde WhatsBot** (tutorial en `GUIA_EDICION_APP.md`).
7. Saber que **no hay web** — solo Flutter + API.

---

## 15. INSTRUCCIÓN COPIAR AL CHAT (Fase 0)

```
@PROMPT_EVOLUCION_SAAS_WHATSBOT.md

Fase 0 únicamente. Analiza todo el proyecto en la raíz. No modifiques nada.

WhatsBot será app móvil FLUTTER con UI tipo WhatsApp — PROHIBIDO UI web.

Credenciales: localiza .env, JSON Google, constantes; entrega MAPA hacia final_system (sin pegar secrets en el chat).

Entregables: sección 2 del prompt maestro.

¿Procedo con Fase 1? (espera mi Sí)
```
