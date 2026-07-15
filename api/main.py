"""
FastAPI application entry.

Arranque:
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

_FS = Path(__file__).resolve().parent.parent
if str(_FS) not in sys.path:
    sys.path.insert(0, str(_FS))

from api.routes import (  # noqa: E402
    auth,
    businesses,
    customers,
    menus,
    orders,
    realtime,
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
    TWILIO_ACCOUNT_SID,
    TWILIO_WHATSAPP_FROM,
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
    logger.info(
        "Twilio outbound only: account=%s from=%s",
        (TWILIO_ACCOUNT_SID or "")[:10] or "(none)",
        TWILIO_WHATSAPP_FROM or "(none)",
    )
    logger.info("WhatsBot API started — %s", API_PUBLIC_URL)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="WhatsBot API",
        description="Backend JSON + webhook Twilio (sin UI web)",
        version="1.0.0",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    allow_all = origins == ["*"] or not origins
    # Wildcard origin + allow_credentials=True is rejected by browsers and is unsafe.
    # Only enable credentials when an explicit origin allowlist is configured.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(whatsapp.router)
    app.include_router(auth.router)
    app.include_router(realtime.router)
    app.include_router(whatsbot.router)
    app.include_router(businesses.router)
    app.include_router(customers.router)
    app.include_router(menus.router)
    app.include_router(orders.router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "whatsbot-api",
            "version": "1.0.0",
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
