"""
Google service-account OAuth2 token minting.

Trades a JSON service-account key (downloaded from Google Cloud → IAM →
Service accounts → Keys → add JSON) for a short-lived access_token via the
JWT bearer flow. Tokens are cached per (client_email, scope) until ~30s
before expiry so we don't hammer the token endpoint on every Sheets call.

The user is expected to share the target spreadsheet with the SA's
`client_email` (Editor role) — otherwise the API returns 403 even with a
valid token.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_DEFAULT_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# In-process token cache. Safe for single-worker deployments; for multi-worker
# the worst case is each worker mints its own token.
_cache: dict[tuple[str, str], tuple[str, float]] = {}


class GoogleAuthError(RuntimeError):
    pass


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_jwt(sa: dict[str, Any], scope: str) -> str:
    """Build and sign the JWT bearer assertion."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    client_email = sa.get("client_email")
    private_key_pem = sa.get("private_key")
    if not client_email or not private_key_pem:
        raise GoogleAuthError("service account JSON missing client_email/private_key")

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    if sa.get("private_key_id"):
        header["kid"] = sa["private_key_id"]
    claims = {
        "iss": client_email,
        "scope": scope,
        "aud": _TOKEN_URL,
        "exp": now + 3600,
        "iat": now,
    }
    signing_input = (
        _b64u(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64u(json.dumps(claims, separators=(",", ":")).encode())
    )
    key = serialization.load_pem_private_key(
        private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem,
        password=None,
    )
    sig = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64u(sig)}"


async def get_access_token(
    sa: dict[str, Any],
    scope: str = _DEFAULT_SCOPE,
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Return a valid OAuth2 access token, minting (and caching) it on demand."""
    if not isinstance(sa, dict):
        raise GoogleAuthError("service_account_json must be a JSON object")

    cache_key = (sa.get("client_email", ""), scope)
    cached = _cache.get(cache_key)
    now = time.time()
    if cached and cached[1] - 30 > now:
        return cached[0]

    assertion = _make_jwt(sa, scope)
    owned = client is None
    cli = client or httpx.AsyncClient(timeout=15)
    try:
        resp = await cli.post(
            _TOKEN_URL,
            data={"grant_type": _GRANT, "assertion": assertion},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code >= 400:
            raise GoogleAuthError(f"token exchange failed: {resp.status_code} {resp.text}")
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        if not token:
            raise GoogleAuthError(f"no access_token in response: {data}")
    finally:
        if owned:
            await cli.aclose()

    _cache[cache_key] = (token, now + expires_in)
    return token


def looks_like_service_account(bundle: dict[str, Any]) -> bool:
    """Heuristic: does this dict look like a Google service-account key?"""
    return (
        isinstance(bundle, dict)
        and bundle.get("type") == "service_account"
        and "client_email" in bundle
        and "private_key" in bundle
    )
