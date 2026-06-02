from __future__ import annotations

import hashlib
import hmac

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WORKSPACE = "default"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/chatbot"
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl: int = 604_800  # 7 days
    debug: bool = False

    # Observability
    log_format: str = "text"   # "text" | "json"
    log_level: str = "INFO"
    sentry_dsn: str = ""       # empty → Sentry disabled

    # Public base URL of this API (used for Telegram setWebhook).
    base_url: str = "https://yourdomain.com"

    # Comma-separated allowed CORS origins. "*" allows all (dev only).
    cors_origins: str = "*"

    # LLM provider: "" / "openai" → litellm; "yandex" → YandexGPT REST.
    llm_provider: str = ""
    llm_model: str = "gpt-4o-mini"

    # YandexGPT (Yandex Cloud Foundation Models)
    yandex_api_key: str = ""
    yandex_folder_id: str = ""

    # Fernet key (urlsafe base64, 32 bytes) for encrypting stored secrets.
    # Empty → an insecure dev key is used (logs a warning). MUST be set in prod.
    secrets_key: str = ""

    # JWT signing secret for user auth. Empty → falls back to a dev secret.
    jwt_secret: str = ""
    jwt_ttl_seconds: int = 604_800  # 7 days

    def jwt_signing_secret(self) -> str:
        return self.jwt_secret or "dev-insecure-jwt-secret-change-me"

    # Webhook rate limit: requests per window (per bot/session key). 0 = off.
    webhook_rate_limit: int = 30
    webhook_rate_window: int = 60  # seconds

    # Code-node sandbox: "process" (fork + rlimit), "docker" (isolated container),
    # or "auto" (docker when available, else process).
    code_sandbox_mode: str = "process"
    code_docker_image: str = "python:3.12-slim"
    code_memory_mb: int = 256
    code_cpus: float = 1.0
    code_pids_limit: int = 64

    # Comma-separated API keys. Each entry is one of:
    #   key                      → workspace = default
    #   key:workspace            → multitenancy
    #   sha256:<hex>             → hashed key (no plaintext in env), workspace = default
    #   sha256:<hex>:workspace
    # Empty string → auth disabled (dev mode), everything maps to DEFAULT_WORKSPACE.
    api_keys: str = ""

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    def _entries(self) -> list[tuple[str, str, str]]:
        """Parse API_KEYS into (kind, secret, workspace) tuples.

        kind is "plain" or "sha256"; secret is the plaintext key or hex digest.
        """
        out: list[tuple[str, str, str]] = []
        for raw in self.api_keys.split(","):
            entry = raw.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if parts[0] == "sha256" and len(parts) >= 2:
                workspace = parts[2].strip() if len(parts) > 2 and parts[2].strip() else DEFAULT_WORKSPACE
                out.append(("sha256", parts[1].strip().lower(), workspace))
            else:
                key = parts[0].strip()
                workspace = parts[1].strip() if len(parts) > 1 and parts[1].strip() else DEFAULT_WORKSPACE
                if key:
                    out.append(("plain", key, workspace))
        return out

    def _match(self, key: str) -> tuple[str, str, str] | None:
        """Constant-time match of a presented key against configured entries."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        for kind, secret, workspace in self._entries():
            candidate = key_hash if kind == "sha256" else key
            if hmac.compare_digest(candidate, secret):
                return (kind, secret, workspace)
        return None

    def is_valid_api_key(self, key: str) -> bool:
        if not self._entries():
            return True  # auth disabled when no keys configured
        return self._match(key) is not None

    def workspace_for_key(self, key: str) -> str:
        """Resolve the workspace for an API key (DEFAULT_WORKSPACE in dev mode)."""
        match = self._match(key)
        return match[2] if match else DEFAULT_WORKSPACE


settings = Settings()
