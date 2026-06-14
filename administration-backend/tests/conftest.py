"""Shared test fixtures for the administration-backend e2e suite.

The admin-backend is heavy on import-time side effects:
- It reads env vars (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, AUTH_SECRET_KEY).
- It constructs an `S3Client` singleton against a live MinIO at module import.
- Its `db.*` modules ship `httpx` calls against the live db-service.

To run e2e tests in isolation we stub all three before importing the FastAPI app:
- Env vars are set early.
- `minio.Minio` is replaced with an in-memory fake so the S3Client constructor
  does not try to reach MinIO.
- Auth middleware is overridden via FastAPI dependency_overrides so we don't
  call the live db-service.
- The db.chatbot_request HTTP calls are stubbed at *both* the source module
  AND the api.chatbot module (which imports the names by value), after the
  FastAPI app has been imported.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import pytest
from unittest.mock import MagicMock, patch
import os


# Insert the backend package onto sys.path so its bare-name imports
# ('from api...', 'from models...', etc.) resolve.
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set required env vars BEFORE any backend module is imported.
os.environ.setdefault("MINIO_ROOT_USER", "test-user")
os.environ.setdefault("MINIO_ROOT_PASSWORD", "test-password")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-for-e2e")


class InMemoryMinio:
    """Drop-in replacement for `minio.Minio` covering the surface S3Client uses."""

    def __init__(self, *args, **kwargs):
        self.buckets: Dict[str, Dict[str, bytes]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.setdefault(bucket, {})

    def put_object(self, bucket: str, obj_name: str, data_stream, length: int = -1, content_type: str = "application/json"):
        payload = data_stream.read() if hasattr(data_stream, "read") else bytes(data_stream)
        self.buckets.setdefault(bucket, {})[obj_name] = payload
        return SimpleNamespace(etag="fake-etag")

    def get_object(self, bucket: str, obj_name: str):
        try:
            payload = self.buckets[bucket][obj_name]
        except KeyError:
            raise FileNotFoundError(f"{bucket}/{obj_name}")
        return SimpleNamespace(read=lambda: payload)

    def remove_object(self, bucket: str, obj_name: str) -> None:
        self.buckets.get(bucket, {}).pop(obj_name, None)

    def stat_object(self, bucket: str, obj_name: str):
        if obj_name not in self.buckets.get(bucket, {}):
            raise FileNotFoundError(f"{bucket}/{obj_name}")
        return SimpleNamespace(object_name=obj_name)

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True):
        for key in list(self.buckets.get(bucket, {}).keys()):
            if key.startswith(prefix):
                yield SimpleNamespace(object_name=key)


@pytest.fixture(scope="session", autouse=True)
def _install_minio_fake():
    """Replace `minio.Minio` with the in-memory fake BEFORE backend imports it."""
    import minio
    original = minio.Minio
    minio.Minio = InMemoryMinio  # type: ignore[assignment]
    try:
        yield
    finally:
        minio.Minio = original  # type: ignore[assignment]


@pytest.fixture
def app_and_user(_install_minio_fake, monkeypatch):
    """Import the FastAPI app fresh per test, stub db-service HTTP, override auth."""
    # Force a clean import every test so the S3 singleton & routers are fresh.
    for mod in [m for m in list(sys.modules) if m.startswith(("api", "models", "minio_controller", "db.", "db", "entities", "config", "utils", "main"))]:
        sys.modules.pop(mod, None)

    import main  # noqa: WPS433
    from api.middleware import get_current_active_user
    from entities.User import User

    # Stub the db-service HTTP helpers AFTER import (api.chatbot pulled the names by value).
    # The state dict mimics db-service: chatbots metadata + a chatbot_versions table.
    from datetime import datetime, timezone
    state: Dict[str, Any] = {
        "chatbots": {},
        "next_id": 100,
        "versions": {},       # version_id -> version record
        "next_version_id": 1,
    }

    async def fake_create_chatbot(user_id, name, description):
        bot_id = state["next_id"]
        state["next_id"] += 1
        record = {"id": bot_id, "name": name, "description": description, "user_id": user_id}
        state["chatbots"][bot_id] = record
        return record

    async def fake_get_chatbots(user_id):
        return [c for c in state["chatbots"].values() if c["user_id"] == user_id]

    async def fake_delete_chatbot(bot_id):
        return state["chatbots"].pop(bot_id, None)

    async def fake_create_version(chatbot_id, author_id, s3_key, parent_id=None, status="DRAFT"):
        vid = state["next_version_id"]
        state["next_version_id"] += 1
        record = {
            "id": vid,
            "chatbot_id": chatbot_id,
            "parent_id": parent_id,
            "s3_key": s3_key,
            "status": status,
            "author_id": author_id,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        state["versions"][vid] = record
        return record

    async def fake_get_latest_version(chatbot_id):
        candidates = [v for v in state["versions"].values() if v["chatbot_id"] == chatbot_id]
        if not candidates:
            return None
        # Newest by id (monotonic in this stub, mirrors created_at DESC in real db).
        return max(candidates, key=lambda v: v["id"])

    async def fake_get_version(version_id):
        return state["versions"].get(version_id)

    async def fake_list_versions(chatbot_id):
        candidates = [v for v in state["versions"].values() if v["chatbot_id"] == chatbot_id]
        return sorted(candidates, key=lambda v: v["id"], reverse=True)

    import api.chatbot as api_chatbot
    import db.chatbot_request as db_chatbot
    stubs = {
        "create_chatbot":     fake_create_chatbot,
        "get_chatbots":       fake_get_chatbots,
        "delete_chatbot":     fake_delete_chatbot,
        "create_version":     fake_create_version,
        "get_latest_version": fake_get_latest_version,
        "get_version":        fake_get_version,
        "list_versions":      fake_list_versions,
    }
    for mod in (api_chatbot, db_chatbot):
        for name, fn in stubs.items():
            monkeypatch.setattr(mod, name, fn, raising=False)

    # ── Subgraph versions: identity is (owner_user_id, subgraph_name).
    state["subgraph_versions"] = {}        # vid -> record
    state["next_subgraph_version_id"] = 1

    async def fake_sub_create_version(owner_user_id, subgraph_name, author_id, s3_key, parent_id=None, status="DRAFT"):
        vid = state["next_subgraph_version_id"]
        state["next_subgraph_version_id"] += 1
        record = {
            "id": vid,
            "owner_user_id": owner_user_id,
            "subgraph_name": subgraph_name,
            "parent_id": parent_id,
            "s3_key": s3_key,
            "status": status,
            "author_id": author_id,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        state["subgraph_versions"][vid] = record
        return record

    async def fake_sub_get_latest_version(owner_user_id, subgraph_name):
        candidates = [
            v for v in state["subgraph_versions"].values()
            if v["owner_user_id"] == owner_user_id and v["subgraph_name"] == subgraph_name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v["id"])

    async def fake_sub_get_version(version_id):
        return state["subgraph_versions"].get(version_id)

    async def fake_sub_list_versions(owner_user_id, subgraph_name):
        candidates = [
            v for v in state["subgraph_versions"].values()
            if v["owner_user_id"] == owner_user_id and v["subgraph_name"] == subgraph_name
        ]
        return sorted(candidates, key=lambda v: v["id"], reverse=True)

    async def fake_sub_list_names(owner_user_id):
        names = {
            v["subgraph_name"]
            for v in state["subgraph_versions"].values()
            if v["owner_user_id"] == owner_user_id
        }
        return sorted(names)

    async def fake_sub_delete(owner_user_id, subgraph_name):
        keys_to_drop = [
            k for k, v in state["subgraph_versions"].items()
            if v["owner_user_id"] == owner_user_id and v["subgraph_name"] == subgraph_name
        ]
        for k in keys_to_drop:
            del state["subgraph_versions"][k]
        return {"deleted_versions": len(keys_to_drop)}

    import api.subgraph as api_subgraph
    import db.subgraph_request as db_subgraph
    sub_stubs = {
        "create_version":      fake_sub_create_version,
        "get_latest_version":  fake_sub_get_latest_version,
        "get_version":         fake_sub_get_version,
        "list_versions":       fake_sub_list_versions,
        "list_subgraph_names": fake_sub_list_names,
        "delete_subgraph":     fake_sub_delete,
    }
    # api.subgraph imported list_subgraph_names/delete_subgraph under aliases.
    for mod in (db_subgraph,):
        for name, fn in sub_stubs.items():
            monkeypatch.setattr(mod, name, fn, raising=False)
    # api.subgraph imports aliases — patch those too.
    monkeypatch.setattr(api_subgraph, "create_version",         fake_sub_create_version,     raising=False)
    monkeypatch.setattr(api_subgraph, "get_latest_version",     fake_sub_get_latest_version, raising=False)
    monkeypatch.setattr(api_subgraph, "get_version",            fake_sub_get_version,        raising=False)
    monkeypatch.setattr(api_subgraph, "list_versions",          fake_sub_list_versions,      raising=False)
    monkeypatch.setattr(api_subgraph, "db_list_subgraph_names", fake_sub_list_names,         raising=False)
    monkeypatch.setattr(api_subgraph, "db_delete_subgraph",     fake_sub_delete,             raising=False)

    fake_user = User(id=42, name="Tester", email="tester@example.com", hashed_password="x")
    main.app.dependency_overrides[get_current_active_user] = lambda: fake_user
    return main.app, fake_user, state


@pytest.fixture
def client(app_and_user):
    from fastapi.testclient import TestClient
    app, _, _ = app_and_user
    return TestClient(app)


@pytest.fixture
def s3(app_and_user):
    from minio_controller.S3Client import S3Client
    return S3Client.get_instance()
"""Pytest fixtures for administration-backend tests."""




@pytest.fixture
def mock_config():
    """Mock configuration fixture."""
    config = MagicMock()
    config.server.host = "localhost"
    config.server.port = 8000
    config.db_service.host = "localhost"
    config.db_service.port = 8001
    config.authentication.secret_key = "test-secret-key"
    config.authentication.algorithm = "HS256"
    config.authentication.access_token_expiration_minutes = 30
    config.s3.host = "localhost"
    config.s3.port = 9000
    config.s3.user = "test-user"
    config.s3.password = "test-password"
    return config


@pytest.fixture
def mock_minio_client():
    """Mock Minio client fixture."""
    with patch('backend.minio_controller.S3Client.Minio') as MockMinio:
        mock_client = MagicMock()
        MockMinio.return_value = mock_client
        mock_client.bucket_exists.return_value = True
        yield mock_client


@pytest.fixture
def test_user():
    """Test user data fixture."""
    return {
        "id": 1,
        "name": "Test User",
        "email": "test@example.com",
        "hashed_password": "hashed_test_password"
    }


@pytest.fixture
def test_chatbot():
    """Test chatbot data fixture."""
    return {
        "bot_id": 1,
        "bot_name": "Test Bot",
        "variables": [],
        "graph": {
            "root": "node1",
            "nodes": {
                "node1": {
                    "type": "text_answer",
                    "text": "Hello"
                }
            }
        }
    }
