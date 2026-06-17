"""
Inbound update normalization per channel.

Each parser maps a provider-specific webhook payload to a common shape the
engine understands: {user_id, chat_id, text, attachments, user_meta, raw}.
Returns None when the update isn't a user message (status callbacks, etc.).
"""
from __future__ import annotations

from typing import Any


def _normalized(user_id: str, text: str, chat_id: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "user_id": str(user_id),
        "chat_id": str(chat_id or user_id),
        "text": text or "",
        "attachments": extra.get("attachments", []),
        "user_meta": extra.get("user_meta", {}),
    }


def parse_whatsapp(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None  # status update / delivery receipt
        msg = messages[0]
        sender = msg.get("from", "")
        text = ""
        if msg.get("type") == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg.get("type") == "interactive":
            interactive = msg.get("interactive", {})
            text = (interactive.get("button_reply") or interactive.get("list_reply") or {}).get("title", "")
        contacts = value.get("contacts") or [{}]
        name = contacts[0].get("profile", {}).get("name", "")
        return _normalized(sender, text, user_meta={"first_name": name})
    except (KeyError, IndexError, TypeError):
        return None


def parse_vk(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("type") != "message_new":
        return None
    obj = payload.get("object", {})
    msg = obj.get("message", obj)  # API 5.103+ wraps in "message"
    peer = msg.get("peer_id") or msg.get("from_id", "")
    return _normalized(msg.get("from_id", peer), msg.get("text", ""), chat_id=peer)


def parse_viber(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("event") != "message":
        return None
    sender = payload.get("sender", {})
    message = payload.get("message", {})
    return _normalized(
        sender.get("id", ""), message.get("text", ""),
        user_meta={"first_name": sender.get("name", "")},
    )


_PARSERS = {
    "whatsapp": parse_whatsapp,
    "vk": parse_vk,
    "viber": parse_viber,
}


def supported(channel: str) -> bool:
    return channel in _PARSERS


def parse(channel: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    parser = _PARSERS.get(channel)
    return parser(payload) if parser else None
