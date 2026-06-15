"""
Unified config resolution for integration nodes.

Merges, in order of increasing precedence:
  1. a named project integration (config["integration"]) — provider/base_url/etc,
  2. a referenced secret bundle (config["secret_ref"]) — credentials,
  3. the node's explicit config.

So a node can just say {"integration": "main-bitrix", "action": "create", ...}
and the provider + credentials are filled in from the project.
"""
from __future__ import annotations

from typing import Any

from services import secrets
from stores import integration_store


async def resolve(config: dict[str, Any], session: Any) -> dict[str, Any]:
    name = config.get("integration")
    if name:
        integ = await integration_store.resolve(getattr(session, "project_id", ""), name)
        if integ is not None:
            config = {**integ.config, **config}
    return await secrets.resolve_config(config, session)
