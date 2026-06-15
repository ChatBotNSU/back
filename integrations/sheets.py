"""
Google Sheets API v4 integration.

Credentials (an OAuth2 access token + spreadsheet id) come from the node config
or a referenced secret. Token refresh is the caller's responsibility — store a
fresh access_token in the secret, or extend this with a refresh_token flow.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(RuntimeError):
    pass


def _client(client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    if client is not None:
        return client, False
    return httpx.AsyncClient(timeout=15), True


class GoogleSheetsProvider:
    name = "google"

    def __init__(self, token: str, spreadsheet_id: str, client: httpx.AsyncClient | None = None) -> None:
        if not token or not spreadsheet_id:
            raise SheetsError("google sheets: token and spreadsheet_id are required")
        self.token = token
        self.spreadsheet_id = spreadsheet_id
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def execute(
        self, action: str, sheet_range: str, values: list[list[Any]] | None = None
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        url = f"{_BASE}/{self.spreadsheet_id}/values/{sheet_range}"
        try:
            if action == "read":
                resp = await client.get(url, headers=self._headers)
                data = resp.json()
                return {
                    "provider": self.name, "action": action,
                    "ok": resp.status_code < 400, "rows": data.get("values", []), "raw": data,
                }
            if action == "update":
                resp = await client.put(
                    url, params={"valueInputOption": "RAW"},
                    json={"values": values or []}, headers=self._headers,
                )
            else:  # append
                resp = await client.post(
                    f"{url}:append", params={"valueInputOption": "RAW"},
                    json={"values": values or []}, headers=self._headers,
                )
            data = resp.json()
            return {
                "provider": self.name, "action": action,
                "ok": resp.status_code < 400, "rows": values or [], "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


def build_provider(
    name: str, config: dict[str, Any], client: httpx.AsyncClient | None = None
) -> GoogleSheetsProvider | None:
    if (name or "google").lower() == "google":
        return GoogleSheetsProvider(
            config.get("token", ""), config.get("spreadsheet_id", ""), client=client
        )
    return None
