"""
FastAPI application entry (Fase 4).

Arranque:
  cd final_system
  python -m api.main

Webhook Twilio:
  POST {API_PUBLIC_URL}/webhook  (alias: /bot)
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# final_system on path
_FS = Path(__file__).resolve().parent.parent
if str(_FS) not in sys.path:
    sys.path.insert(0, str(_FS))

from api.routes import (  # noqa: E402
    auth,
    businesses,
    menus,
    orders,
    realtime,
    sheets,
    whatsapp,
    whatsbot,
)
from config.settings import (  # noqa: E402
    API_PUBLIC_URL,
    CORS_ORIGINS,
    DEBUG,
    DEFAULT_BUSINESS_ID,
    HOST,
    PORT,
    FCM_ENABLED,
    REALTIME_ENABLED,
    RESTAURANT_NAME,
)
from infrastructure.database import init_db, session_scope  # noqa: E402
from services.business_service import ensure_default_business  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        with session_scope() as db:
            biz = ensure_default_business(db)
            logger.info(
                "Default business seeded: %s (twilio=%s)",
                biz.id,
                biz.twilio_whatsapp_from,
            )
    except Exception:
        logger.exception("Default business seed failed (API still starts)")
    logger.info("WhatsBot API started — %s", API_PUBLIC_URL)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="WhatsBot API",
        description="Backend JSON + webhook Twilio (sin UI web)",
        version="0.9.0",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(whatsapp.router)
    app.include_router(auth.router)
    app.include_router(realtime.router)
    app.include_router(whatsbot.router)
    app.include_router(businesses.router)
    app.include_router(menus.router)
    app.include_router(orders.router)
    app.include_router(sheets.router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "whatsbot-api",
            "version": "0.9.0",
            "restaurant": RESTAURANT_NAME,
            "default_business_id": DEFAULT_BUSINESS_ID,
            "api_public_url": API_PUBLIC_URL,
            "realtime_enabled": REALTIME_ENABLED,
            "fcm_enabled": FCM_ENABLED,
        }

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
    )


if __name__ == "__main__":
    main()
