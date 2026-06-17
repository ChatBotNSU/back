from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com/v18.0"


def _split_token(token: str) -> tuple[str, str]:
    """Bot token is "PHONE_NUMBER_ID:ACCESS_TOKEN" for the WhatsApp Cloud API."""
    phone_number_id, _, access_token = token.partition(":")
    return phone_number_id, access_token


class WhatsAppAdapter:
    channel = "whatsapp"

    async def send(self, token: str, recipient: str, message: dict[str, Any]) -> dict[str, Any]:
        phone_number_id, access_token = _split_token(token)
        content_type = message.get("content_type", "text")
        body = self._build_body(recipient, content_type, message)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_GRAPH}/{phone_number_id}/messages",
                    json=body,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                data = resp.json()
            msg_id = ""
            msgs = data.get("messages")
            if isinstance(msgs, list) and msgs:
                msg_id = str(msgs[0].get("id", ""))
            return {"ok": resp.status_code < 400, "message_id": msg_id}
        except Exception as exc:  # noqa: BLE001
            logger.error("WhatsApp send failed: %s", exc)
            return {"ok": False, "message_id": "", "error": str(exc)}

    def _build_body(self, to: str, content_type: str, message: dict[str, Any]) -> dict[str, Any]:
        base = {"messaging_product": "whatsapp", "to": to}
        if content_type == "image":
            return {**base, "type": "image",
                    "image": {"link": message.get("media_url", ""), "caption": message.get("text", "")}}
        if content_type == "buttons":
            buttons = message.get("buttons", [])[:3]  # WhatsApp allows up to 3 reply buttons
            return {**base, "type": "interactive", "interactive": {
                "type": "button",
                "body": {"text": message.get("text", " ")},
                "action": {"buttons": [
                    {"type": "reply", "reply": {
                        "id": b.get("value", b.get("label", "")),
                        "title": b.get("label", b.get("text", "")),
                    }} for b in buttons
                ]},
            }}
        return {**base, "type": "text", "text": {"body": message.get("text", "")}}
