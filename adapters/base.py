from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChannelAdapter(Protocol):
    channel: str

    async def send(
        self,
        token: str,
        recipient: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send a message to a recipient.

        Args:
            token:     bot credential (Telegram bot token, etc.)
            recipient: chat_id / user_id / phone number
            message:   dict produced by send_message handler

        Returns:
            {"ok": bool, "message_id": str, ...}
        """
        ...
