# Migraciones (Fase 5)

Esquema gestionado con SQLAlchemy `create_all` + script idempotente.

```bash
cd final_system
python scripts/migrate_db.py
```

Incluye:

- Creación/actualización de tablas (`businesses`, `business_intents`, `business_prompts`, `menu_items`, `orders`, `customers`, …)
- Semilla del negocio `default` desde `.env` legacy + `config/intents.py` + `config/prompts.py`

Para Alembic completo: Fase 10+.
