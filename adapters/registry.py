from __future__ import annotations

from typing import Any

from adapters.base import ChannelAdapter

_registry: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    _registry[adapter.channel] = adapter


def get(channel: str) -> ChannelAdapter | None:
    return _registry.get(channel)


async def send(
    channel: str,
    token: str,
    recipient: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    adapter = get(channel)
    if adapter is None:
        return {"ok": False, "message_id": "", "error": f"No adapter for channel {channel!r}"}
    return await adapter.send(token, recipient, message)


def load_all() -> None:
    from adapters.telegram import TelegramAdapter
    from adapters.whatsapp import WhatsAppAdapter
    from adapters.vk import VKAdapter
    from adapters.viber import ViberAdapter
    register(TelegramAdapter())
    register(WhatsAppAdapter())
    register(VKAdapter())
    register(ViberAdapter())
