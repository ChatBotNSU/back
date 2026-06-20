from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from adapters.registry import load_all as load_adapters
from api import (
    account, analytics, data, dlq, flows, integrations as integrations_api, projects,
    secrets as secrets_api, sessions, webhooks, bots,
)
from api.ratelimit import RedisRateLimiter
from config import settings
from db.base import Base, build_engine, build_session_factory
from engine.registry import load_all_handlers
from stores.bot_store import InMemoryBotStore, SQLBotStore
from stores.flow_store import InMemoryFlowStore, SQLFlowStore
from services import metrics
from services.logging_config import configure_logging, request_id_var
from services.secrets import get_cipher, set_active_store as set_active_secret_store
from stores.dead_letter import InMemoryDeadLetterStore, RedisDeadLetterStore
from stores import data_store as data_store_mod
from stores import integration_store as integration_store_mod
from stores.data_store import InMemoryDataStore, SQLDataStore
from stores.integration_store import InMemoryIntegrationStore, SQLIntegrationStore
from stores.project_store import InMemoryProjectStore, SQLProjectStore
from stores.secret_store import InMemorySecretStore, SQLSecretStore
from stores.session_store import InMemorySessionStore, RedisSessionStore
from stores.user_store import InMemoryUserStore, SQLUserStore

configure_logging(settings.log_format, settings.log_level)
logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk  # type: ignore
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0)
        logger.info("Sentry initialized")
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry_sdk not installed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _init_sentry()
    load_all_handlers()
    load_adapters()

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    try:
        engine = build_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = build_session_factory(engine)
        app.state.flow_store = SQLFlowStore(sf)
        app.state.bot_store = SQLBotStore(sf)
        app.state.secret_store = SQLSecretStore(sf, get_cipher())
        app.state.project_store = SQLProjectStore(sf)
        app.state.data_store = SQLDataStore(sf)
        app.state.integration_store = SQLIntegrationStore(sf)
        app.state.user_store = SQLUserStore(sf)
        logger.info("PostgreSQL connected")
    except Exception as exc:
        logger.warning("PostgreSQL unavailable (%s) — using in-memory stores", exc)
        app.state.flow_store = InMemoryFlowStore()
        app.state.bot_store = InMemoryBotStore()
        app.state.secret_store = InMemorySecretStore(get_cipher())
        app.state.project_store = InMemoryProjectStore()
        app.state.data_store = InMemoryDataStore()
        app.state.integration_store = InMemoryIntegrationStore()
        app.state.user_store = InMemoryUserStore()

    # Make stores reachable from node handlers.
    set_active_secret_store(app.state.secret_store)
    data_store_mod.set_active_store(app.state.data_store)
    integration_store_mod.set_active_store(app.state.integration_store)

    # ── Redis (sessions + ARQ pool) ────────────────────────────────────────────
    try:
        from redis.asyncio import from_url as redis_from_url  # type: ignore
        redis = redis_from_url(settings.redis_url, decode_responses=False)
        await redis.ping()
        app.state.session_store = RedisSessionStore(redis, ttl=settings.redis_session_ttl)
        app.state.dead_letter = RedisDeadLetterStore(redis)
        webhooks.set_rate_limiter(
            RedisRateLimiter(redis, settings.webhook_rate_limit, settings.webhook_rate_window)
        )
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — using in-memory session store", exc)
        app.state.session_store = InMemorySessionStore()
        app.state.dead_letter = InMemoryDeadLetterStore()

    try:
        from arq import create_pool  # type: ignore
        from arq.connections import RedisSettings  # type: ignore
        arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        app.state.arq_pool = arq_pool
        logger.info("ARQ pool created")
    except Exception as exc:
        logger.warning("ARQ unavailable (%s) — background tasks used instead", exc)
        app.state.arq_pool = None

    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chatbot Builder API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(account.router)
    app.include_router(webhooks.router)
    app.include_router(flows.router)
    app.include_router(sessions.router)
    app.include_router(bots.router)
    app.include_router(analytics.router)
    app.include_router(dlq.router)
    app.include_router(secrets_api.router)
    app.include_router(projects.router)
    app.include_router(data.router)
    app.include_router(integrations_api.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def prometheus_metrics() -> Response:
        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        """Readiness probe: verifies Postgres + Redis are actually reachable."""
        checks: dict[str, bool] = {"postgres": False, "redis": False}

        flow_store = getattr(request.app.state, "flow_store", None)
        try:
            if isinstance(flow_store, SQLFlowStore):
                await flow_store.list_all(limit=1)
                checks["postgres"] = True
        except Exception:  # noqa: BLE001
            checks["postgres"] = False

        session_store = getattr(request.app.state, "session_store", None)
        try:
            if isinstance(session_store, RedisSessionStore):
                await session_store._r.ping()
                checks["redis"] = True
        except Exception:  # noqa: BLE001
            checks["redis"] = False

        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ready": ok, "checks": checks},
        )

    return app


app = create_app()
