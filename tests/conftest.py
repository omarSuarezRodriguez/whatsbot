"""Guardia global de aislamiento de tests — se importa ANTES de cualquier
test_*.py de este directorio (garantia de pytest para conftest.py).

Incidente (2026-08-05): todos los test_*.py aislan su propia BD con
``os.environ.setdefault("DATABASE_URL", ...)``, pero ``config/settings.py``
hacia ``load_dotenv(..., override=True)`` sin condicion, que SIEMPRE pisaba
esa variable con el valor real de ``.env`` (``sqlite:///data/whatsbot.db``)
en el momento en que ``config.settings`` se importaba. Resultado: toda
corrida de pytest escribia, sin darse cuenta, sobre la base de datos real de
produccion.

``WHATSBOT_TEST_MODE=1`` le dice a ``config/settings.py`` que NO pise el
DATABASE_URL (ni otras env vars) que cada test ya seteo.
"""

from __future__ import annotations

import os

os.environ["WHATSBOT_TEST_MODE"] = "1"
