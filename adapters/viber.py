from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API = "https://chatapi.viber.com/pa/send_message"


class ViberAdapter:
    channel = "viber"

    async def send(self, token: str, recipient: str, message: dict[str, Any]) -> dict[str, Any]:
        content_type = message.get("content_type", "text")
        body: dict[str, Any] = {
            "receiver": recipient,
            "sender": {"name": message.get("sender_name", "Bot")},
        }
        if content_type == "image" and message.get("media_url"):
            body.update({"type": "picture", "text": message.get("text", ""), "media": message["media_url"]})
        else:
            body.update({"type": "text", "text": message.get("text", "")})

        if content_type == "buttons":
            body["keyboard"] = self._keyboard(message.get("buttons", []))

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    _API, json=body, headers={"X-Viber-Auth-Token": token}
                )
                data = resp.json()
            # Viber returns status=0 on success.
            ok = resp.status_code < 400 and data.get("status", 1) == 0
            return {"ok": ok, "message_id": str(data.get("message_token", "")),
                    **({} if ok else {"error": data.get("status_message", "error")})}
        except Exception as exc:  # noqa: BLE001
            logger.error("Viber send failed: %s", exc)
            return {"ok": False, "message_id": "", "error": str(exc)}

    def _keyboard(self, buttons: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "Type": "keyboard",
            "Buttons": [{
                "ActionType": "reply",
                "ActionBody": b.get("value", b.get("label", "")),
                "Text": b.get("label", b.get("text", "")),
            } for b in buttons],
        }
