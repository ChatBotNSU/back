from __future__ import annotations

import logging
from typing import Any

from engine.registry import register
from integrations.crm import CrmError, build_provider
from models.node import Node, NodeType
from models.session import Session
from services import connections, secrets

logger = logging.getLogger(__name__)


class CrmHandler:
    """
    CRM integration. Routes to a real provider (Bitrix24 / AmoCRM / HubSpot)
    when ``config.provider`` is set and supported; otherwise returns a stub so
    flows remain runnable without credentials.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        # Merge project integration + secret credentials, if referenced.
        config = await connections.resolve(config, session)

        provider: str = config.get("provider", "")
        action: str = config.get("action", "find")
        entity: str = config.get("entity", "contact")
        fields: dict = config.get("fields", {})

        # Resolve {{var}} field values from session/data_in
        resolved: dict[str, Any] = {}
        for key, val in fields.items():
            if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                var_name = val[2:-2].strip()
                resolved[key] = session.variables.get(var_name) or data_in.get(var_name)
            else:
                resolved[key] = val

        client = config.get("__client__")  # test injection hook (httpx client)
        try:
            impl = build_provider(provider, config, client=client)
        except CrmError as exc:
            return self._error(provider, action, entity, str(exc))

        if impl is None:
            return self._stub(provider, action, entity, resolved, session)

        try:
            result = await impl.execute(action, entity, resolved)
        except Exception as exc:  # noqa: BLE001 — surface to the flow, don't crash
            logger.warning("CRM %s %s failed: %s", provider, action, exc)
            return self._error(provider, action, entity, str(exc))

        # Persist a refreshed OAuth token (AmoCRM) back to its secret so the
        # next run uses the fresh token instead of refreshing again.
        new_token = result.pop("refreshed_token", None)
        if new_token and config.get("secret_ref"):
            await secrets.update_bundle(
                getattr(session, "workspace_id", "default"),
                config["secret_ref"], {"token": new_token},
            )
        return result

    @staticmethod
    def _stub(
        provider: str, action: str, entity: str,
        resolved: dict[str, Any], session: Session,
    ) -> dict[str, Any]:
        return {
            "provider": provider, "action": action, "entity": entity,
            "ok": True, "id": session.variables.get("__crm_id__", "stub-id"),
            "found": action == "find", "created": action == "create",
            "fields": resolved, "stub": True,
        }

    @staticmethod
    def _error(provider: str, action: str, entity: str, error: str) -> dict[str, Any]:
        return {
            "provider": provider, "action": action, "entity": entity,
            "ok": False, "id": "", "found": False, "error": error,
        }


register(NodeType.CRM, CrmHandler())
