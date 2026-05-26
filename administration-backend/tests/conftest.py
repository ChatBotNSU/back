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
    state: Dict[str, Any] = {"chatbots": {}, "next_id": 100}

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

    import api.chatbot as api_chatbot
    import db.chatbot_request as db_chatbot
    for mod in (api_chatbot, db_chatbot):
        monkeypatch.setattr(mod, "create_chatbot", fake_create_chatbot, raising=False)
        monkeypatch.setattr(mod, "get_chatbots", fake_get_chatbots, raising=False)
        monkeypatch.setattr(mod, "delete_chatbot", fake_delete_chatbot, raising=False)

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
