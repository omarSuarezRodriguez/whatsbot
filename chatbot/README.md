# Chatbot (Fase 2)

- `app/` — copia del bot legacy (`from app.*` sin cambiar lógica de negocio).
- `gateway.py` — **única puerta:** `handle_incoming_message(payload)`.
- `runtime.py` — wiring de servicios (equivalente a `create_app()`).

El webhook activo en producción sigue en la **raíz** (`POST /bot`) hasta Fase 4.

```bash
cd final_system
python scripts/validate_chatbot.py
```
