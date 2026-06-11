Backend (el bot):

FastAPI — API REST + webhook de WhatsApp (único framework web)
SQLAlchemy + Alembic — ORM y migraciones
SQLite (dev) / PostgreSQL (producción)
Twilio — integración WhatsApp
Redis — pub/sub para WebSockets y multi-worker
WebSockets — tiempo real tipo WhatsApp
JWT + bcrypt — autenticación por negocio con PIN
Firebase/FCM — push notifications (opcional)
RapidFuzz — fuzzy matching para intents del chatbot
Google Sheets — espejo opcional (desactivado por defecto)