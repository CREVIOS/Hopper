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
from app.routers import (
    auth, pods, credits, admin, courses, files, issues, notifications, ssh_keys, usage,
)
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
    print(">>> Startup: starting metrics consumer...", flush=True)
    from app.services.metrics_consumer import start_metrics_consumer
    await start_metrics_consumer()
    print(">>> Startup: starting audit retention job...", flush=True)
    from app.services.audit_retention import start_audit_retention
    await start_audit_retention()
    print(">>> Startup: starting session reaper...", flush=True)
    from app.services.session_reaper import start_session_reaper
    await start_session_reaper()
    print(">>> Startup: starting credit grace monitor...", flush=True)
    from app.services.credit_alerts import start_credit_grace_monitor
    await start_credit_grace_monitor()
    print(">>> Startup: complete.", flush=True)
    yield
    from app.services.credit_alerts import stop_credit_grace_monitor
    await stop_credit_grace_monitor()
    from app.services.session_reaper import stop_session_reaper
    await stop_session_reaper()
    from app.services.audit_retention import stop_audit_retention
    await stop_audit_retention()
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

    # Baseline security headers applied to every response. nginx-ingress
    # adds HSTS at the edge; we add the rest here so they're present even
    # on responses that bypass the edge (e.g. internal port-forward calls
    # used by the test harness).
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(pods.router, prefix="/pods", tags=["pods"])
    app.include_router(credits.router, prefix="/credits", tags=["credits"])
    app.include_router(courses.router, prefix="/courses", tags=["courses"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
    app.include_router(ssh_keys.router, prefix="/ssh-keys", tags=["ssh-keys"])
    app.include_router(files.router, prefix="/files", tags=["files"])
    app.include_router(issues.router, prefix="/issues", tags=["issues"])
    app.include_router(usage.router, prefix="/usage", tags=["usage"])
    # HEAD is registered explicitly. FastAPI's @app.get doesn't dispatch HEAD
    # to the GET handler — load balancers and uptime probes that issue HEAD
    # would see 405 without this. Same body, same status, no payload.
    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz():
        return {"status": "ok"}

    @app.api_route("/readyz", methods=["GET", "HEAD"])
    async def readyz():
        return {"status": "ready"}

    return app


app = create_app()
