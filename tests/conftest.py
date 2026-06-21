from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.auth import current_workspace, require_api_key
from api.deps import (
    get_bot_store,
    get_data_store,
    get_dead_letter_store,
    get_flow_store,
    get_integration_store,
    get_project_store,
    get_secret_store,
    get_session_store,
    get_user_store,
)
from db.base import Base
from main import create_app
from services import secrets as secrets_mod
from stores.bot_store import SQLBotStore
from stores.dead_letter import InMemoryDeadLetterStore
from stores import data_store as data_store_mod
from stores import integration_store as integration_store_mod
from stores.data_store import SQLDataStore
from stores.integration_store import SQLIntegrationStore
from stores.flow_store import SQLFlowStore
from stores.project_store import SQLProjectStore
from stores.secret_store import InMemorySecretStore
from stores.session_store import RedisSessionStore
from stores.user_store import InMemoryUserStore

DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Keep the per-process webhook rate limiter isolated between tests."""
    import api.webhooks as wh
    if hasattr(wh._rate_limiter, "reset"):
        wh._rate_limiter.reset()
    yield
    if hasattr(wh._rate_limiter, "reset"):
        wh._rate_limiter.reset()


# ─── Database ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine(DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ─── Redis (fakeredis) ────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def redis_client():
    from fakeredis.aioredis import FakeRedis  # type: ignore
    client = FakeRedis()
    yield client
    await client.aclose()


# ─── Store instances ──────────────────────────────────────────────────────────

@pytest.fixture()
def flow_store(db_session_factory):
    return SQLFlowStore(db_session_factory)


@pytest.fixture()
def bot_store(db_session_factory):
    return SQLBotStore(db_session_factory)


@pytest.fixture()
def project_store(db_session_factory):
    return SQLProjectStore(db_session_factory)


@pytest.fixture()
def data_store(db_session_factory):
    store = SQLDataStore(db_session_factory)
    data_store_mod.set_active_store(store)
    yield store
    data_store_mod.set_active_store(None)


@pytest.fixture()
def integration_store(db_session_factory):
    store = SQLIntegrationStore(db_session_factory)
    integration_store_mod.set_active_store(store)
    yield store
    integration_store_mod.set_active_store(None)


@pytest.fixture()
def session_store(redis_client):
    return RedisSessionStore(redis_client, ttl=3600)


@pytest.fixture()
def dead_letter_store():
    return InMemoryDeadLetterStore()


@pytest.fixture()
def user_store():
    return InMemoryUserStore()


@pytest.fixture()
def secret_store():
    store = InMemorySecretStore()
    secrets_mod.set_active_store(store)
    yield store
    secrets_mod.set_active_store(None)


# ─── FastAPI test client ──────────────────────────────────────────────────────

@pytest.fixture()
def client(flow_store, session_store, bot_store, dead_letter_store, secret_store,
           project_store, data_store, integration_store, user_store):
    app = create_app()
    # Inject test stores
    app.dependency_overrides[get_flow_store] = lambda: flow_store
    app.dependency_overrides[get_session_store] = lambda: session_store
    app.dependency_overrides[get_bot_store] = lambda: bot_store
    app.dependency_overrides[get_dead_letter_store] = lambda: dead_letter_store
    app.dependency_overrides[get_secret_store] = lambda: secret_store
    app.dependency_overrides[get_project_store] = lambda: project_store
    app.dependency_overrides[get_data_store] = lambda: data_store
    app.dependency_overrides[get_integration_store] = lambda: integration_store
    app.dependency_overrides[get_user_store] = lambda: user_store
    # Bypass API key auth in tests; default everything to the "default" workspace
    app.dependency_overrides[require_api_key] = lambda: "test-key"
    app.dependency_overrides[current_workspace] = lambda: "default"
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
