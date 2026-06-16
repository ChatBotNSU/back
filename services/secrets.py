"""
Encrypted, per-workspace secret storage + resolution.

Credentials for integrations (CRM tokens, OAuth tokens, payment keys) must NOT
live in flow JSON. Instead a node references a secret by name (``secret_ref``)
and the handler resolves it at runtime via the active secret store.

Values are encrypted at rest with Fernet. A secret value is an arbitrary JSON
object (a "credential bundle"), e.g. {"base_url": "...", "token": "..."}.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from config import settings

logger = logging.getLogger(__name__)

# Stable, clearly-insecure key for dev/tests when SECRETS_KEY is unset.
# (urlsafe-base64 of a fixed 32-byte string — valid Fernet key.)
_DEV_KEY = "Y2hhdGJvdC1kZXYtc2VjcmV0LWtleS0wMTIzNDU2Nzg="


class Cipher:
    """Fernet-based encrypt/decrypt with a graceful dev fallback."""

    def __init__(self, key: str = "") -> None:
        from cryptography.fernet import Fernet

        if not key:
            logger.warning(
                "SECRETS_KEY is not set — using an insecure dev key. "
                "Set SECRETS_KEY in production."
            )
            key = _DEV_KEY
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()

    @staticmethod
    def generate_key() -> str:
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()


def get_cipher() -> Cipher:
    return Cipher(settings.secrets_key)


# ─── Store protocol ───────────────────────────────────────────────────────────

@runtime_checkable
class SecretStore(Protocol):
    async def put(self, workspace_id: str, name: str, value: dict[str, Any]) -> str: ...
    async def get_value(self, workspace_id: str, name: str) -> dict[str, Any] | None: ...
    async def list_meta(self, workspace_id: str) -> list[dict[str, Any]]: ...
    async def delete(self, workspace_id: str, name: str) -> bool: ...


# ─── Module-level active store + resolver (handlers reach in here) ─────────────

_active: SecretStore | None = None


def set_active_store(store: SecretStore | None) -> None:
    global _active
    _active = store


async def resolve(workspace_id: str, ref: str) -> dict[str, Any]:
    """Resolve a secret_ref to its credential bundle, or {} when unavailable."""
    if not ref or _active is None:
        return {}
    value = await _active.get_value(workspace_id, ref)
    return value or {}


async def update_bundle(workspace_id: str, ref: str, patch: dict[str, Any]) -> bool:
    """Merge `patch` into a stored secret bundle (e.g. persist a refreshed token)."""
    if not ref or _active is None:
        return False
    current = await _active.get_value(workspace_id, ref)
    if current is None:
        return False
    await _active.put(workspace_id, ref, {**current, **patch})
    return True


async def resolve_config(config: dict[str, Any], session: Any) -> dict[str, Any]:
    """
    Merge a referenced secret bundle into a node config.

    Explicit config keys win over the secret bundle, so inline creds keep
    working and secrets only fill in what's missing.
    """
    ref = config.get("secret_ref")
    if not ref:
        return config
    bundle = await resolve(getattr(session, "workspace_id", "default"), ref)
    return {**bundle, **config}
