from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.core import nats as nats_client
from app.routers import auth, pods, credits, admin
from app.services.orchestrator_client import orchestrator_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await orchestrator_client.connect()
    await nats_client.connect()

    # Import here to avoid circular — starts NATS subscriptions
    from app.services.billing_consumer import start_billing_consumer
    await start_billing_consumer()

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(pods.router, prefix="/pods", tags=["pods"])
    app.include_router(credits.router, prefix="/credits", tags=["credits"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ready"}

    return app


app = create_app()
