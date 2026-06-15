"""
Real CRM provider integrations (Bitrix24, AmoCRM, HubSpot).

Each provider speaks its own REST dialect but exposes the same
``execute(action, entity, fields)`` contract and returns a normalized dict:

    {"provider", "action", "entity", "ok", "id", "found", "raw"}

Providers accept an optional httpx client so tests can inject
``httpx.MockTransport`` without hitting the network.
"""
from __future__ import annotations

from typing import Any

import httpx


class CrmError(RuntimeError):
    pass


def _client(client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    if client is not None:
        return client, False
    return httpx.AsyncClient(timeout=15), True


class Bitrix24Provider:
    """Inbound-webhook REST API: base_url already contains the auth token,
    e.g. ``https://acme.bitrix24.ru/rest/1/abctoken/``."""

    name = "bitrix24"

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        if not base_url:
            raise CrmError("bitrix24: base_url is required")
        self.base_url = base_url.rstrip("/") + "/"
        self._client = client

    def _method(self, action: str, entity: str) -> str:
        verb = {"find": "list", "create": "add", "update": "update"}.get(action, "list")
        return f"crm.{entity}.{verb}.json"

    async def execute(
        self, action: str, entity: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        url = self.base_url + self._method(action, entity)
        if action == "find":
            payload: dict[str, Any] = {"filter": fields}
        elif action == "update":
            payload = {"id": fields.get("id"), "fields": fields}
        else:  # create
            payload = {"fields": fields}
        try:
            resp = await client.post(url, json=payload)
            data = resp.json()
        finally:
            if owned:
                await client.aclose()

        result = data.get("result")
        found = bool(result) if action == "find" else False
        entity_id = ""
        if action == "find" and isinstance(result, list) and result:
            entity_id = str(result[0].get("ID", ""))
        elif result is not None and not isinstance(result, list):
            entity_id = str(result)
        return {
            "provider": self.name, "action": action, "entity": entity,
            "ok": "error" not in data, "id": entity_id, "found": found, "raw": data,
        }


class AmoCrmProvider:
    """
    AmoCRM API v4. base_url like ``https://acme.amocrm.ru`` + OAuth bearer.

    Access tokens expire in 24h. Pass ``refresh`` ({client_id, client_secret,
    refresh_token, redirect_uri}) to auto-refresh once on a 401 and retry. The
    new token is exposed as ``self.token`` / in the result so the caller can
    persist it back to the secret store.
    """

    name = "amocrm"

    def __init__(
        self,
        base_url: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        refresh: dict[str, Any] | None = None,
    ) -> None:
        if not base_url or not token:
            raise CrmError("amocrm: base_url and token are required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client
        self._refresh = refresh or {}
        self.refreshed_token: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _refresh_token(self, client: httpx.AsyncClient) -> bool:
        if not self._refresh.get("refresh_token"):
            return False
        resp = await client.post(f"{self.base_url}/oauth2/access_token", json={
            "client_id": self._refresh.get("client_id", ""),
            "client_secret": self._refresh.get("client_secret", ""),
            "grant_type": "refresh_token",
            "refresh_token": self._refresh["refresh_token"],
            "redirect_uri": self._refresh.get("redirect_uri", ""),
        })
        if resp.status_code >= 400:
            return False
        new_token = resp.json().get("access_token")
        if not new_token:
            return False
        self.token = new_token
        self.refreshed_token = new_token
        return True

    async def execute(
        self, action: str, entity: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        collection = f"{entity}s"  # contacts / leads / companies
        try:
            resp = await self._call(client, action, collection, fields)
            if resp.status_code == 401 and await self._refresh_token(client):
                resp = await self._call(client, action, collection, fields)

            data = resp.json()
            items = (data.get("_embedded") or {}).get(collection, [])
            result = {
                "provider": self.name, "action": action, "entity": entity,
                "ok": resp.status_code < 400, "id": str(items[0]["id"]) if items else "",
                "found": bool(items) if action == "find" else False, "raw": data,
            }
            if self.refreshed_token:
                result["refreshed_token"] = self.refreshed_token
            return result
        finally:
            if owned:
                await client.aclose()

    async def _call(self, client, action, collection, fields):
        url = f"{self.base_url}/api/v4/{collection}"
        if action == "find":
            return await client.get(url, params={"query": fields.get("query", "")},
                                    headers=self._headers())
        method = "patch" if action == "update" else "post"
        return await client.request(method, url, json=[fields], headers=self._headers())


class HubSpotProvider:
    """HubSpot CRM v3 with a private-app bearer token."""

    name = "hubspot"
    base_url = "https://api.hubapi.com"

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        if not token:
            raise CrmError("hubspot: token is required")
        self.token = token
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def execute(
        self, action: str, entity: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        obj = f"{entity}s"  # contacts / deals / companies
        try:
            if action == "find":
                resp = await client.post(
                    f"{self.base_url}/crm/v3/objects/{obj}/search",
                    json={"filterGroups": [{"filters": [
                        {"propertyName": k, "operator": "EQ", "value": v}
                        for k, v in fields.items()
                    ]}]},
                    headers=self._headers,
                )
                data = resp.json()
                results = data.get("results", [])
                return {
                    "provider": self.name, "action": action, "entity": entity,
                    "ok": resp.status_code < 400, "id": str(results[0]["id"]) if results else "",
                    "found": bool(results), "raw": data,
                }
            if action == "update":
                resp = await client.patch(
                    f"{self.base_url}/crm/v3/objects/{obj}/{fields.get('id')}",
                    json={"properties": fields}, headers=self._headers,
                )
            else:
                resp = await client.post(
                    f"{self.base_url}/crm/v3/objects/{obj}",
                    json={"properties": fields}, headers=self._headers,
                )
            data = resp.json()
            return {
                "provider": self.name, "action": action, "entity": entity,
                "ok": resp.status_code < 400, "id": str(data.get("id", "")),
                "found": False, "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


class SalesforceProvider:
    """Salesforce REST API. base_url = instance URL, OAuth bearer token."""

    name = "salesforce"
    api_version = "v59.0"

    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient | None = None) -> None:
        if not base_url or not token:
            raise CrmError("salesforce: base_url and token are required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _sobject(self, entity: str) -> str:
        return entity.capitalize()  # contact → Contact, lead → Lead

    async def execute(
        self, action: str, entity: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        sobject = self._sobject(entity)
        base = f"{self.base_url}/services/data/{self.api_version}"
        try:
            if action == "find":
                where = " AND ".join(f"{k}='{v}'" for k, v in fields.items()) or "Id != null"
                soql = f"SELECT Id FROM {sobject} WHERE {where} LIMIT 1"
                resp = await client.get(f"{base}/query", params={"q": soql}, headers=self._headers)
                data = resp.json()
                records = data.get("records", [])
                return {
                    "provider": self.name, "action": action, "entity": entity,
                    "ok": resp.status_code < 400, "id": str(records[0]["Id"]) if records else "",
                    "found": bool(records), "raw": data,
                }
            if action == "update":
                rec_id = fields.pop("id", fields.pop("Id", ""))
                resp = await client.patch(
                    f"{base}/sobjects/{sobject}/{rec_id}", json=fields, headers=self._headers
                )
                ok = resp.status_code < 400
                return {"provider": self.name, "action": action, "entity": entity,
                        "ok": ok, "id": str(rec_id), "found": False, "raw": {}}
            resp = await client.post(f"{base}/sobjects/{sobject}", json=fields, headers=self._headers)
            data = resp.json()
            return {
                "provider": self.name, "action": action, "entity": entity,
                "ok": resp.status_code < 400, "id": str(data.get("id", "")),
                "found": False, "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


def build_provider(
    name: str, config: dict[str, Any], client: httpx.AsyncClient | None = None
):
    """Construct a provider from a node's config, or None if unsupported."""
    name = (name or "").lower()
    if name == "bitrix24":
        return Bitrix24Provider(config.get("base_url", ""), client=client)
    if name == "amocrm":
        return AmoCrmProvider(
            config.get("base_url", ""), config.get("token", ""),
            client=client, refresh=config.get("refresh"),
        )
    if name == "hubspot":
        return HubSpotProvider(config.get("token", ""), client=client)
    if name == "salesforce":
        return SalesforceProvider(config.get("base_url", ""), config.get("token", ""), client=client)
    return None
