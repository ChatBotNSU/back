"""
Calendar integrations: Google Calendar (v3) and Calendly (v2).

Credentials (OAuth/personal token) come from node config or a referenced secret.
"""
from __future__ import annotations

from typing import Any

import httpx

_GOOGLE = "https://www.googleapis.com/calendar/v3"
_CALENDLY = "https://api.calendly.com"


class CalendarError(RuntimeError):
    pass


def _client(client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    if client is not None:
        return client, False
    return httpx.AsyncClient(timeout=15), True


class GoogleCalendarProvider:
    name = "google"

    def __init__(self, token: str, calendar_id: str = "primary", client: httpx.AsyncClient | None = None) -> None:
        if not token:
            raise CalendarError("google calendar: token is required")
        self.token = token
        self.calendar_id = calendar_id or "primary"
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        client, owned = _client(self._client)
        base = f"{_GOOGLE}/calendars/{self.calendar_id}/events"
        try:
            if action == "slots":  # list upcoming events as busy slots
                resp = await client.get(
                    base, params={"timeMin": params.get("time_min"), "timeMax": params.get("time_max")},
                    headers=self._headers,
                )
                data = resp.json()
                return {
                    "provider": self.name, "action": action, "ok": resp.status_code < 400,
                    "slots": [e.get("start", {}).get("dateTime") for e in data.get("items", [])],
                    "event": None, "cancelled": False, "raw": data,
                }
            if action == "cancel":
                resp = await client.delete(f"{base}/{params.get('event_id')}", headers=self._headers)
                return {
                    "provider": self.name, "action": action, "ok": resp.status_code < 400,
                    "event": None, "slots": [], "cancelled": resp.status_code < 400,
                }
            # create
            body = {
                "summary": params.get("title", ""),
                "start": {"dateTime": params.get("start")},
                "end": {"dateTime": params.get("end")},
            }
            if params.get("attendee_email"):
                body["attendees"] = [{"email": params["attendee_email"]}]
            resp = await client.post(base, json=body, headers=self._headers)
            data = resp.json()
            return {
                "provider": self.name, "action": action, "ok": resp.status_code < 400,
                "event": {"id": data.get("id"), "title": params.get("title", "")},
                "slots": [], "cancelled": False, "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


class CalendlyProvider:
    name = "calendly"

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        if not token:
            raise CalendarError("calendly: token is required")
        self.token = token
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        client, owned = _client(self._client)
        try:
            # Calendly is link-based; expose available event types as "slots".
            resp = await client.get(
                f"{_CALENDLY}/event_types",
                params={"user": params.get("user", "")}, headers=self._headers,
            )
            data = resp.json()
            return {
                "provider": self.name, "action": action, "ok": resp.status_code < 400,
                "slots": [c.get("scheduling_url") for c in data.get("collection", [])],
                "event": None, "cancelled": False, "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


def build_provider(
    name: str, config: dict[str, Any], client: httpx.AsyncClient | None = None
):
    name = (name or "google").lower()
    if name == "google":
        return GoogleCalendarProvider(
            config.get("token", ""), config.get("calendar_id", "primary"), client=client
        )
    if name == "calendly":
        return CalendlyProvider(config.get("token", ""), client=client)
    return None
