"""
ARQ worker entry point.

Run with:
    arq worker.WorkerSettings
"""
from __future__ import annotations

import logging
from typing import Any

from config import settings
from tasks import run_flow_task

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    from db.base import build_engine, build_session_factory
    from stores.flow_store import SQLFlowStore
    from stores.session_store import RedisSessionStore
    from stores.dead_letter import RedisDeadLetterStore
    from stores.secret_store import SQLSecretStore
    from stores import data_store as data_store_mod
    from stores import integration_store as integration_store_mod
    from stores.data_store import SQLDataStore
    from stores.integration_store import SQLIntegrationStore
    from services.secrets import get_cipher, set_active_store as set_active_secret_store
    from adapters.registry import load_all as load_adapters
    from engine.registry import load_all_handlers

    load_adapters()
    load_all_handlers()

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    ctx["flow_store"] = SQLFlowStore(session_factory)
    set_active_secret_store(SQLSecretStore(session_factory, get_cipher()))
    data_store_mod.set_active_store(SQLDataStore(session_factory))
    integration_store_mod.set_active_store(SQLIntegrationStore(session_factory))

    # ARQ provides ctx["redis"] — reuse for session + dead-letter stores
    ctx["session_store"] = RedisSessionStore(ctx["redis"], ttl=settings.redis_session_ttl)
    ctx["dead_letter"] = RedisDeadLetterStore(ctx["redis"])
    logger.info("ARQ worker started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker shutting down")


class WorkerSettings:
    functions = [run_flow_task]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
    job_timeout = 300  # 5 min max per flow run
    keep_result = 86_400  # keep job result for 24h

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings  # type: ignore
        return RedisSettings.from_dsn(settings.redis_url)
