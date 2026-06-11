Backend (el bot):

FastAPI — API REST + webhook de WhatsApp (único framework web)
SQLAlchemy + Alembic — ORM y migraciones
SQLite (dev) / PostgreSQL (producción)
Twilio — integración WhatsApp
Redis — pub/sub para WebSockets y multi-worker
WebSockets — tiempo real
JWT + bcrypt — autenticación por negocio con PIN
Firebase/FCM — push notifications (opcional)
RapidFuzz — fuzzy matching para intents del chatbot
Google Sheets — espejo opcional (desactivado por defecto)



## Multi-tenant 

Modelo Business en la BD — cada negocio tiene su propio ID, Twilio, PIN, menú, intents y mensajes
Auth JWT por negocio — cada dueño solo ve sus datos
business_id en conversaciones, pedidos y mensajes — todo está aislado por negocio
Script onboard_business.py para dar de alta nuevos negocios
El webhook de Twilio identifica el negocio por el número Twilio que recibe el mensaje



## Estado actual

Arquitectura limpia y separada por capas
Multi-tenant en el diseño desde el inicio
Tiempo real con WebSockets
Auth JWT
BD relacional con migraciones
Tests y scripts de validación
Lo que queda para crecer es operacional y de escala:

Probar con múltiples negocios reales
Subir a producción (servidor + dominio + HTTPS)
Activar PostgreSQL en lugar de SQLite
Activar Redis real para multi-worker
Activar FCM si se quiere push (requiere cliente que registre device token)
