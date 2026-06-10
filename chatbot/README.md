# Chatbot (Fase 2)

- `app/` — copia del bot legacy (`from app.*` sin cambiar lógica de negocio).
- `gateway.py` — **única puerta:** `handle_incoming_message(payload)`.
- `runtime.py` — wiring de servicios (equivalente a `create_app()`).

El webhook activo está en FastAPI: `POST /webhook` (alias `POST /bot`) en `api/routes/whatsapp.py`.

```bash
cd final_system
python scripts/validate_chatbot.py
```
