from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TG_API = "https://api.telegram.org/bot{token}/{method}"


def _url(token: str, method: str) -> str:
    return _TG_API.format(token=token, method=method)


class TelegramAdapter:
    channel = "telegram"

    async def send(
        self,
        token: str,
        recipient: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        content_type = message.get("content_type", "text")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if content_type == "text":
                    return await self._send_text(client, token, recipient, message)
                if content_type == "image":
                    return await self._send_image(client, token, recipient, message)
                if content_type == "buttons":
                    return await self._send_buttons(client, token, recipient, message)
                if content_type == "carousel":
                    return await self._send_carousel(client, token, recipient, message)
                # fallback: send as plain text
                return await self._send_text(client, token, recipient, message)
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return {"ok": False, "message_id": "", "error": str(exc)}

    async def set_webhook(
        self,
        token: str,
        url: str,
        secret: str = "",
    ) -> dict[str, Any]:
        """Register `url` as the bot's webhook via Telegram Bot API."""
        payload: dict[str, Any] = {"url": url}
        if secret:
            payload["secret_token"] = secret
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_url(token, "setWebhook"), json=payload)
            return resp.json()

    async def delete_webhook(self, token: str) -> dict[str, Any]:
        """Remove the bot's webhook via Telegram Bot API."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_url(token, "deleteWebhook"), json={})
            return resp.json()

    async def _send_text(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": message.get("text", ""),
            "parse_mode": "HTML",
        }
        resp = await client.post(_url(token, "sendMessage"), json=payload)
        data = resp.json()
        return {
            "ok": data.get("ok", False),
            "message_id": str(data.get("result", {}).get("message_id", "")),
        }

    async def _send_image(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": message.get("media_url", ""),
            "caption": message.get("text", ""),
        }
        resp = await client.post(_url(token, "sendPhoto"), json=payload)
        data = resp.json()
        return {
            "ok": data.get("ok", False),
            "message_id": str(data.get("result", {}).get("message_id", "")),
        }

    async def _send_buttons(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        buttons = message.get("buttons", [])
        keyboard = {
            "inline_keyboard": [
                [{"text": b.get("label", b.get("text", "")), "callback_data": b.get("value", b.get("label", ""))}]
                for b in buttons
            ]
        }
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": message.get("text", "Choose:"),
            "reply_markup": keyboard,
            "parse_mode": "HTML",
        }
        resp = await client.post(_url(token, "sendMessage"), json=payload)
        data = resp.json()
        return {
            "ok": data.get("ok", False),
            "message_id": str(data.get("result", {}).get("message_id", "")),
        }

    async def _send_carousel(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        # Telegram doesn't have native carousel; send as media group or sequential messages
        cards = message.get("cards", [])
        last_result: dict[str, Any] = {"ok": True, "message_id": ""}
        for card in cards:
            text = f"<b>{card.get('title', '')}</b>\n{card.get('description', '')}"
            payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            if card.get("image_url"):
                payload = {"chat_id": chat_id, "photo": card["image_url"], "caption": text, "parse_mode": "HTML"}
                resp = await client.post(_url(token, "sendPhoto"), json=payload)
            else:
                resp = await client.post(_url(token, "sendMessage"), json=payload)
            last_result = resp.json()
        return {
            "ok": last_result.get("ok", False),
            "message_id": str(last_result.get("result", {}).get("message_id", "")),
        }
