from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import engine
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core import nats as nats_client
from app.middleware.audit import AuditMiddleware
from app.routers import auth, pods, credits, admin
from app.routers import settings as settings_router
from app.services.orchestrator_client import orchestrator_client
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    print(">>> Startup: connecting to orchestrator...", flush=True)
    await orchestrator_client.connect()
    print(">>> Startup: connecting to NATS...", flush=True)
    await nats_client.connect()
    print(">>> Startup: starting billing consumer...", flush=True)
    from app.services.billing_consumer import start_billing_consumer
    await start_billing_consumer()
    print(">>> Startup: complete.", flush=True)
    yield
    await nats_client.disconnect()
    await orchestrator_client.close()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hopper API",
        description="VM Cloud Platform — Slice & share compute resources",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Reject the unsafe combination of allow_credentials + wildcard origin.
    # FastAPI's CORS middleware silently echoes the request Origin back when
    # given "*" + credentials, defeating the same-origin policy entirely.
    if "*" in settings.cors_origins:
        raise RuntimeError(
            "HOPPER_CORS_ORIGINS must list explicit origins; '*' is unsafe with cookies"
        )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(AuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(pods.router, prefix="/pods", tags=["pods"])
    app.include_router(credits.router, prefix="/credits", tags=["credits"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ready"}

    return app


app = create_app()
