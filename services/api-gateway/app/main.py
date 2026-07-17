from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import engine
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core import nats as nats_client
from app.middleware.audit import AuditMiddleware
from app.routers import auth, pods, credits, admin, files, issues, notifications, ssh_keys, usage
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
    from app.services.session_reaper import run_session_reaper
    reaper_stop = asyncio.Event()
    reaper_task = asyncio.create_task(run_session_reaper(reaper_stop), name="session-reaper")
    print(">>> Startup: complete.", flush=True)
    yield
    reaper_stop.set()
    await reaper_task
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
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
    app.include_router(ssh_keys.router, prefix="/ssh-keys", tags=["ssh-keys"])
    app.include_router(files.router, prefix="/files", tags=["files"])
    app.include_router(issues.router, prefix="/issues", tags=["issues"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
    app.include_router(usage.router, prefix="/usage", tags=["usage"])
    # HEAD is registered explicitly. FastAPI's @app.get doesn't dispatch HEAD
    # to the GET handler — load balancers and uptime probes that issue HEAD
    # would see 405 without this. Same body, same status, no payload.
    #
    # /healthz is deliberately shallow: it is the LIVENESS signal, and
    # restarting this pod cannot fix a down database or NATS — deep checks
    # here would just restart-loop the gateway during an infra outage.
    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz():
        return {"status": "ok"}

    # /readyz is the READINESS signal: deep checks on every dependency the
    # gateway needs to serve real traffic. K8s pulls the pod out of the
    # Service while any of these fail, without killing it.
    @app.api_route("/readyz", methods=["GET", "HEAD"])
    async def readyz():
        from sqlalchemy import text
        from fastapi.responses import JSONResponse
        from app.services.orchestrator_client import orchestrator_client as orch

        checks: dict[str, bool] = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:
            logger.warning("readyz: database check failed", exc_info=True)
            checks["database"] = False

        checks["nats"] = nats_client.nc is not None and nats_client.nc.is_connected

        # Reported but NOT gating: the orchestrator is only needed for VM
        # create/terminate. Pulling the whole gateway out of the Service
        # (auth, dashboard, credits, ...) whenever the orchestrator restarts
        # would turn every orchestrator deploy into a full site outage.
        checks["orchestrator"] = await orch.healthy()

        ready = checks["database"] and checks["nats"]
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "degraded", "checks": checks},
        )

    return app


app = create_app()
