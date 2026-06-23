# Graph Report - whatsbot  (2026-06-23)

## Corpus Check
- 105 files · ~78,685 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1271 nodes · 2985 edges · 79 communities (67 shown, 12 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 462 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5ded3c2a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]

## God Nodes (most connected - your core abstractions)
1. `session_scope()` - 54 edges
2. `AdminService` - 47 edges
3. `FlowEngine` - 43 edges
4. `Prompts listos — copiar y pegar en Cursor` - 34 edges
5. `DBStore` - 33 edges
6. `Session` - 31 edges
7. `init_db()` - 31 edges
8. `Guía incremental — registro por fase` - 31 edges
9. `BusinessId` - 30 edges
10. `Message` - 30 edges

## Surprising Connections (you probably didn't know these)
- `DBStore` --uses--> `Customer`  [INFERRED]
  chatbot/app/integrations/db_store.py → models/customer.py
- `Any` --uses--> `Customer`  [INFERRED]
  chatbot/app/integrations/db_store.py → models/customer.py
- `Any` --uses--> `AdminService`  [INFERRED]
  services/notification_service.py → chatbot/app/services/admin_service.py
- `handle_admin_confirmation()` --calls--> `is_admin_confirm()`  [INFERRED]
  services/notification_service.py → chatbot/app/utils/validators.py
- `handle_admin_confirmation()` --calls--> `extract_admin_order_id()`  [INFERRED]
  services/notification_service.py → chatbot/app/utils/validators.py

## Import Cycles
- 1-file cycle: `api/main.py -> api/main.py`
- 1-file cycle: `api/routes/whatsbot.py -> api/routes/whatsbot.py`
- 1-file cycle: `services/realtime_service.py -> services/realtime_service.py`
- 1-file cycle: `services/customer_service.py -> services/customer_service.py`
- 1-file cycle: `services/conversation_service.py -> services/conversation_service.py`
- 1-file cycle: `services/twilio_sync_service.py -> services/twilio_sync_service.py`
- 1-file cycle: `models/business.py -> models/business.py`
- 1-file cycle: `models/conversation.py -> models/conversation.py`
- 1-file cycle: `models/customer.py -> models/customer.py`
- 1-file cycle: `models/menu.py -> models/menu.py`
- 1-file cycle: `models/message.py -> models/message.py`
- 1-file cycle: `models/order.py -> models/order.py`
- 1-file cycle: `models/reservation.py -> models/reservation.py`
- 2-file cycle: `api/main.py -> api/routes/auth.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/businesses.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/customers.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/menus.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/orders.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/realtime.py -> api/main.py`
- 2-file cycle: `api/main.py -> api/routes/whatsapp.py -> api/main.py`

## Communities (79 total, 12 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (64): DeviceToken, Conversation, datetime, Conversation thread per customer WhatsApp line., _utcnow(), Message, datetime, Individual WhatsApp messages (incoming/outgoing) for Flutter history. (+56 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (65): BusinessId, datetime, OrderOut, Response, Session, BusinessMeOut, ConversationOut, DeviceTokenRegister (+57 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (52): WebSocket, get_redis(), _is_enabled(), publish_event(), Any, Redis cache / pub-sub wrapper (OLA 4).  All operations are no-ops when REDIS_ENA, Return async Redis client (singleton). None if Redis disabled or unavailable., Publish JSON event to Redis channel.  Returns False if Redis unavailable. (+44 more)

### Community 3 - "Community 3"
Cohesion: 0.17
Nodes (10): Any, get_active_business_id(), _active_business_id(), DBStore, get_db_store(), _new_order_id(), _order_to_dict(), DB-backed data store for the chatbot engine (replaces Google Sheets).  Single so (+2 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (15): Any, OrderService, Public URL for Twilio status callbacks (sent → delivered → read)., twilio_status_callback_url(), AdminService, Admin notifications, confirmations and reminder scheduler., Código de país ITU (1–3 dígitos); no confunde móvil CO 300… con +300., Solo dígitos nacionales del país del restaurante (sin código de país). (+7 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (39): 0. CONTEXTO DEL PRODUCTO, 10. MAPA DE INTEGRACIONES, 11. ENTREGABLES FINALES, 12. LO QUE NO DEBE HACER EL AGENTE, 13. ORDEN DE EJECUCIÓN (resumen), 14. MÉTRICA DE ÉXITO, 15. INSTRUCCIÓN COPIAR AL CHAT (Fase 0), 1.b MIGRACIÓN DE CREDENCIALES Y CONFIG (desde el bot original) (+31 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (36): Chat: apertura fluida sin saltos (reverse ListView) ✅, Chat: apertura instantánea desde caché (comportamiento WhatsApp) ✅, Chat: apertura sin scroll visible ✅, Chat: mensajes en vivo con chat abierto (FIX UI reactiva) ✅, Chat: mensajes entrantes visibles + capitalización al escribir (v1.17) ✅, Chat: mensajes enviados visibles + orden tipo WhatsApp (v1.24) ✅, Chat: orden cronológico + lista al recibir (v1.18) ✅, Chat: preview al enviar + orden al recibir (v1.19) ✅ (+28 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (50): lifespan(), FastAPI application entry.  Arranque:   python -m api.main  Webhook Twilio:, Any, Session, BusinessId, Session, BusinessId, OrderOut (+42 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (34): Cómo usarlo, Fase 11 — Tiempo real (paridad lógica con WhatsApp) ✅, Fase 12+ — Próximas mejoras (pendiente), Prompt 0 — Verificación al pegar el proyecto (opcional), Prompt 10 — Fase 9: App Flutter WhatsBot (UI WhatsApp), Prompt 11 — Fase 10: Validación final + guías, Prompt 11b — Solo si faltan credenciales tras Fase 1, Prompt 12 — Fase 11.1: Análisis (SIN código) (+26 more)

### Community 9 - "Community 9"
Cohesion: 0.19
Nodes (6): Any, MenuService, OrderService — DB-backed, multi-tenant (via DBStore)., OrderParser, OrderService, Always build fresh from current DB menu (multi-tenant, no stale cache).

### Community 10 - "Community 10"
Cohesion: 0.20
Nodes (3): Any, Reply, FlowEngine

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (60): Base, Business, Business, BusinessIntentConfig, BusinessPromptConfig, datetime, Business (tenant) — maps TWILIO_WHATSAPP_FROM to business_id., _utcnow() (+52 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (25): Alcance ESTRICTO (no negociable), Alcance ESTRICTO (no negociable), Contexto del flujo actual (para no romper nada), Estado actual del código (leer ANTES de planificar — no asumir StreamBuilder), FORMATO DE SALIDA, MÉTODO DE TRABAJO (obligatorio, en este orden), Objetivo, Plan de diagnóstico (ejecutar primero en Plan, sin tocar backend) (+17 more)

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (8): get_prompt(), handle_incoming_message(), _normalize_reply(), Reply, Única puerta de entrada al chatbot (Fase 2).  Entrada payload:   - phone / wa_id, Procesa un mensaje entrante del webhook WhatsApp (Twilio).     No envía Twilio;, _reply_to_response_text(), Chatbot package — única puerta: gateway.handle_incoming_message.

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (21): _apply_schema_patches(), get_db(), get_engine(), get_session_factory(), init_db(), Session, SQLAlchemy engine, session factory and schema bootstrap., FastAPI dependency: yields a DB session. (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.14
Nodes (16): _find_item(), _get_intent_index(), infer_user_intent(), log_parser_errors(), _menu_literal_tokens(), _min_confidence(), _qty_for(), Order Intelligence Engine — natural-language order parser with cart operations. (+8 more)

### Community 16 - "Community 16"
Cohesion: 0.19
Nodes (8): OrderIntelligenceEngine, Production-grade order interpretation pipeline.     Menu is injected at construc, Canonical output contract., Double-check: menu boundary, coherence, no invented products., Category names count as valid menu overlap (e.g. una hamburguesa)., Reduce simple Spanish plurals for matching (pizzas → pizza)., _singularize_token(), _token_keys()

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (21): Alta de un segundo negocio, `Caddyfile`, Checklist rápido antes de dar por bueno producción, Comandos útiles del día a día, `docker-compose.yml`, `Dockerfile`, Firewall del VPS, Paso 1 — Clonar el proyecto en el VPS (+13 more)

### Community 18 - "Community 18"
Cohesion: 0.22
Nodes (5): Any, Thread-safe per-(business, user) state with optional disk persistence., Scope state by (business_id, wa_id) to prevent cross-tenant leakage., Lightweight read copy: deep-copy cart/reservation only when present., StateManager

### Community 19 - "Community 19"
Cohesion: 0.18
Nodes (5): NaturalLanguagePreprocessor, OrderParser, Facade used by OrderService; wraps OrderIntelligenceEngine., Structured output contract for order interpretation., Fast, regex-only canonicalization for conversational WhatsApp input.

### Community 20 - "Community 20"
Cohesion: 0.23
Nodes (18): Customer, Customer, datetime, Customers (WhatsApp users) per business — extended for owner panel., _utcnow(), create_customer(), delete_customer(), get_customer() (+10 more)

### Community 21 - "Community 21"
Cohesion: 0.24
Nodes (18): alias, Any, BusinessId, Session, BusinessCreate, BusinessOut, BusinessCreate, BusinessOut (+10 more)

### Community 22 - "Community 22"
Cohesion: 0.18
Nodes (8): _build_intent_phrase_index(), normalize(), Splits chaotic order text into quantity + product fragments., Fold áéíóú, ñ and other accented characters for stable menu matching., Public lightweight normalizer (backward compatible)., Pre-normalize phrases and token map once at import (hot path in infer)., SegmentEngine, _strip_accents()

### Community 23 - "Community 23"
Cohesion: 0.37
Nodes (17): BusinessId, Session, MenuItemCreate, MenuItemOut, MenuItemUpdate, MenuReplace, MenuItemCreate, MenuItemOut (+9 more)

### Community 24 - "Community 24"
Cohesion: 0.31
Nodes (8): create_app(), main(), Validate FastAPI webhook + DB (Fase 4)., _fail(), main(), _migrate_message_status(), _ok(), End-to-end validation — Fase 10 + realtime Fase 11.

### Community 25 - "Community 25"
Cohesion: 0.19
Nodes (17): get_prompt(), auth_headers(), client(), TestClient, WhatsBot REST API — Fase 7., Gateway debe leer menú y prompts de BD cuando hay business_id., OF-C: reintento con mismo client_id no reenvía Twilio ni duplica fila., test_gateway_uses_db_menu_and_prompts() (+9 more)

### Community 26 - "Community 26"
Cohesion: 0.09
Nodes (21): 0. CONTEXTO, 1. VOCABULARIO DE OUTCOMES (contrato fijo), 2. MAPA DE TRANSICIONES (referencia), 3. CÓMO USAR ESTE DOCUMENTO, 4. ÍNDICE DE PROMPTS, 5. PROMPTS LISTOS (copiar y pegar), 6. ENTREGABLES POR FASE, 7. COMMITS SUGERIDOS (+13 more)

### Community 27 - "Community 27"
Cohesion: 0.22
Nodes (15): _admin_service(), approve_order_from_app(), handle_admin_confirmation(), notify_admin_new_order(), on_order_pending(), _order_dict_from_db_row(), _persist_order_to_db(), Any (+7 more)

### Community 28 - "Community 28"
Cohesion: 0.26
Nodes (4): Any, FuzzyMatcher, First product per category in menu order (for category-name orders)., Real numeric similarity scoring against dynamic menu catalog.

### Community 29 - "Community 29"
Cohesion: 0.21
Nodes (14): Path, Reply, _ensure_worker(), _flush_batch(), _format_bot_reply(), _format_exchange(), _format_role_block(), _LogRecord (+6 more)

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (14): _build_intent_index_for_business(), business_scope(), Per-business request context (Fase 7+, OLA 2).  Activates menu/intents/prompts f, Build and cache the intent index for a given business_id., Activate per-business prompts/menu/intents for one message., intents_json_to_parser_format(), load_intents_json(), load_menu_items() (+6 more)

### Community 31 - "Community 31"
Cohesion: 0.24
Nodes (15): auth_token(), client(), _fresh_test_database(), TestClient, WebSocket realtime — Fase 11.2., Stale SQLite test files skip new columns; recreate from current models., _recv_json(), test_conversations_since_filter() (+7 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (9): Shim hacia config centralizada.  El chatbot importa `app.config` sin cambios;, Path, Bot session defaults — flows, navigation, branding., resolve_flows_path(), Central configuration package (4 modules + .env secrets)., Global intent defaults — migrated from legacy app/core/parser.py (Fase 3)., get_prompt(), Global prompt defaults — from flows/restaurant_flow.json + gateway (Fase 3). (+1 more)

### Community 33 - "Community 33"
Cohesion: 0.15
Nodes (15): date, time, extract_admin_order_id(), is_admin_confirm(), is_confirmation(), is_global_command(), is_greeting(), is_rejection() (+7 more)

### Community 34 - "Community 34"
Cohesion: 0.14
Nodes (13): 1. Editar el flujo en JSON, 2. Transiciones en JSON, 3. Fallbacks y mensajes fuera del flujo, 4. Aplicar cambios, 5. Checklist rápido, Cambiar el flujo del chatbot, Cambiar el orden de los pasos, Cambiar solo el contenido (sin cambiar orden) (+5 more)

### Community 35 - "Community 35"
Cohesion: 0.23
Nodes (5): QuantityEngine, Robust quantity resolver: 2x, x2, digits, number words., Extract quantity from the raw segment, then product text for matching., Advanced normalization pipeline for chaotic WhatsApp input., TextNormalizer

### Community 36 - "Community 36"
Cohesion: 0.17
Nodes (11): Alta de un negocio nuevo, Antes de empezar, Comandos útiles, Guía de negocios — alta fácil, Negocio default (el primero), Paso 1 — Crear el negocio en la base de datos, Paso 2 — Configurar Twilio, Paso 3 — Autenticarse en la API (+3 more)

### Community 37 - "Community 37"
Cohesion: 0.28
Nodes (14): MenuItem, MenuItem, datetime, Menu items per business., _utcnow(), create_menu_item(), delete_menu_item(), get_menu_item() (+6 more)

### Community 38 - "Community 38"
Cohesion: 0.17
Nodes (11): A. Arrancar el backend, Alta de nuevo negocio, Checklist E2E, Documentación, Estructura del proyecto, Guía rápida, Probar flujo completo, Resultados de validación (+3 more)

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (12): APIs y Servicios, Arquitectura Interna, Base de Datos, Calidad del Código, Estado y Gestión de Datos, Estructura del Proyecto, Flujo de Ejecución, Mensajería (MÁXIMA PROFUNDIDAD) (+4 more)

### Community 40 - "Community 40"
Cohesion: 0.14
Nodes (24): Any, Response, Session, is_twilio_whatsapp_sandbox(), Global settings loaded from .env., use_rest_webhook_replies(), build_twiml_response(), deliver_reply() (+16 more)

### Community 41 - "Community 41"
Cohesion: 0.14
Nodes (12): AdminService, MenuService, OrderService, date, time, Any, BotContext, ReservationService (+4 more)

### Community 42 - "Community 42"
Cohesion: 0.31
Nodes (8): Context manager for scripts and services., session_scope(), _get_store(), _init_db(), Flujo confirmación admin (DB-backed, sin Sheets).  Cliente pide → notify admin →, test_admin_confirm_notifies_customer(), test_approve_from_app_notifies_customer(), test_approve_from_app_reports_twilio_failure()

### Community 43 - "Community 43"
Cohesion: 0.20
Nodes (9): Arquitectura WhatsBot, Capas, Componentes, Flujo de mensaje entrante, Flujo de mensaje saliente (dueño → cliente), Modelo de números, Multi-tenant, Prohibiciones (+1 more)

### Community 44 - "Community 44"
Cohesion: 0.27
Nodes (5): Any, MenuService — DB-backed, multi-tenant (via DBStore)., get_active_menu(), Any, MenuService

### Community 45 - "Community 45"
Cohesion: 0.49
Nodes (9): _add_column_if_missing(), downgrade(), _drop_column_if_exists(), _existing_columns(), _existing_tables(), _inspector(), _is_pg(), _is_sqlite() (+1 more)

### Community 46 - "Community 46"
Cohesion: 0.40
Nodes (9): _init_db(), Tests for JSON-driven flow transitions (states format)., _step(), test_global_menu_from_order(), test_order_happy_path_domicilio(), test_order_modify_then_confirm(), test_reservation_full(), test_reservation_rejected_restarts() (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.39
Nodes (7): auth_headers(), client(), TestClient, Message status + mark-read — Fase 11.5., _run_status_migration(), test_mark_read_updates_incoming(), test_owner_message_has_delivered_status()

### Community 48 - "Community 48"
Cohesion: 0.29
Nodes (7): A) Drift watch no dispara actualización UI para el `conversation.id` abierto (ALTA), B) `_reconcileWithStore` pisa o pierde mensajes mergeados por WS (ALTA), C) Doble vía con carrera WS ↔ Drift ↔ `_refresh` (MEDIA), D) WS desconectado en dispositivo real sin fallback percibido (MEDIA), E) Mensajes salientes / ticks como sub-síntoma (MEDIA-BAJA), F) Tests pasan pero producción falla — gap de cobertura (ALTA probabilidad), Hipótesis de causa raíz (priorizadas — actualizadas tras análisis)

### Community 49 - "Community 49"
Cohesion: 0.43
Nodes (6): auth_headers(), client(), TestClient, Tests for Twilio status callback webhook., test_incoming_webhook_dedup_by_sid(), test_status_callback_updates_owner_message()

### Community 50 - "Community 50"
Cohesion: 0.33
Nodes (6): OBJETIVO, PARTE 2 — VEREDICTO ARQUITECTÓNICO (clave para mí), PARTE 3 — APRENDIZAJE, PARTE 4 — EVALUACIÓN FINAL, PARTE 5 — TABLA DE CALIFICACIÓN POR MÓDULO, PARTE 6 — RESUMEN EJECUTIVO + PLAN DE MEJORAS (lo más importante)

### Community 51 - "Community 51"
Cohesion: 0.60
Nodes (4): commit_message(), git(), main(), Git save: add, commit (versión del README), push.

### Community 52 - "Community 52"
Cohesion: 0.40
Nodes (5): A) Anti-patrón StreamBuilder + initialData stale (ALTA probabilidad), B) Doble suscripción que se pisa (MEDIA), C) Dependencia exclusiva de `_refresh()` ante WS (MEDIA), D) Mensajes salientes optimistas / ticks (MEDIA-BAJA, sub-síntoma), Hipótesis de causa raíz (priorizadas)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (12): get_bot_context(), Lazy singleton wiring for chatbot services (DB-backed, no Sheets)., Build or return cached bot services (all DB-backed)., Clear singleton (tests only)., reset_bot_context(), _fail(), main(), _ok() (+4 more)

### Community 55 - "Community 55"
Cohesion: 0.50
Nodes (7): main(), _normalize_flow(), _parse_ref(), Any, Validate conversational flow JSON (stdlib only)., _step_exists(), validate_flow()

### Community 56 - "Community 56"
Cohesion: 0.50
Nodes (4): 1. Lista de chats no se actualiza (pero suena la push), 2. Tus mensajes humanos quedan “enviando” (reloj ⏱), Diagnóstico (sin tocar código), Resumen de cambios (2 archivos principales)

## Knowledge Gaps
- **243 isolated node(s):** `HTTPAuthorizationCredentials`, `Depends`, `_bearer`, `Header`, `alias` (+238 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_bot_context()` connect `Community 54` to `Community 1`, `Community 3`, `Community 4`, `Community 40`, `Community 41`, `Community 10`, `Community 11`, `Community 42`, `Community 13`, `Community 46`, `Community 24`, `Community 27`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Why does `AdminService` connect `Community 4` to `Community 3`, `Community 41`, `Community 10`, `Community 9`, `Community 19`, `Community 27`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `session_scope()` connect `Community 42` to `Community 0`, `Community 3`, `Community 7`, `Community 11`, `Community 14`, `Community 46`, `Community 47`, `Community 49`, `Community 24`, `Community 25`, `Community 27`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `AdminService` (e.g. with `AdminService` and `Any`) actually correct?**
  _`AdminService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `FlowEngine` (e.g. with `BotContext` and `get_bot_context()`) actually correct?**
  _`FlowEngine` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Alembic environment configuration — auto-generates migrations from SQLAlchemy mo`, `FastAPI application package — Fase 4+.`, `FastAPI application entry.  Arranque:   python -m api.main  Webhook Twilio:` to the rest of the system?**
  _421 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.0635814889336016 - nodes in this community are weakly interconnected._