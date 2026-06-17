from __future__ import annotations

import json
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API = "https://api.vk.com/method/messages.send"
_API_VERSION = "5.199"


class VKAdapter:
    channel = "vk"

    async def send(self, token: str, recipient: str, message: dict[str, Any]) -> dict[str, Any]:
        content_type = message.get("content_type", "text")
        params: dict[str, Any] = {
            "access_token": token,
            "v": _API_VERSION,
            "peer_id": recipient,
            "random_id": random.randint(1, 2_000_000_000),
            "message": message.get("text", ""),
        }
        if content_type == "image" and message.get("media_url"):
            # VK needs uploaded attachments; fall back to a link in the text.
            params["message"] = f"{params['message']}\n{message['media_url']}".strip()
        if content_type == "buttons":
            params["keyboard"] = json.dumps(self._keyboard(message.get("buttons", [])), ensure_ascii=False)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(_API, data=params)
                data = resp.json()
            if "error" in data:
                return {"ok": False, "message_id": "", "error": str(data["error"])}
            return {"ok": True, "message_id": str(data.get("response", ""))}
        except Exception as exc:  # noqa: BLE001
            logger.error("VK send failed: %s", exc)
            return {"ok": False, "message_id": "", "error": str(exc)}

    def _keyboard(self, buttons: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "inline": True,
            "buttons": [[{
                "action": {
                    "type": "text",
                    "label": b.get("label", b.get("text", "")),
                    "payload": json.dumps({"value": b.get("value", b.get("label", ""))}),
                },
            }] for b in buttons],
        }
