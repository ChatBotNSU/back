from __future__ import annotations

from typing import Any

from engine.registry import register
from models.flow import Flow
from models.node import Node, NodeType
from models.session import Session


def _normalize(s: str) -> str:
    """Strip a leading slash and lowercase — so "/start" and "start" match."""
    s = (s or "").strip().lower()
    return s[1:] if s.startswith("/") else s


def _matches(expected: str, text: str) -> bool:
    """A configured command matches the leading token of the inbound text.
    Empty config matches anything."""
    expected = _normalize(expected)
    if not expected:
        return True
    first = (text or "").strip().split(None, 1)[0] if text else ""
    return _normalize(first) == expected


def find_command_match(flow: Flow, text: str) -> Node | None:
    """Find a message_trigger node in `flow` whose command matches `text`.

    Used by webhook dispatch to decide whether an inbound message should
    interrupt the current session and re-enter the flow from that trigger
    node (multi-entry-point model). Returns None when no trigger matches
    or only triggers with empty `command` exist (which would match everything
    and shouldn't preempt an ongoing conversation).
    """
    if not text:
        return None
    for node in flow.nodes.values():
        if node.type != NodeType.MESSAGE_TRIGGER:
            continue
        command = str(node.config.get("command", "") or "").strip()
        if not command:
            continue  # bare triggers don't preempt
        if _matches(command, text):
            return node
    return None


class MessageTriggerHandler:
    """Start a flow on an inbound message. With config.command set, the flow
    only proceeds when the message's first token matches that command —
    otherwise the runner halts via __halt__ so the bot stays silent.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        text = str(session.variables.get("text", ""))
        command = str(config.get("command", "") or "")
        matched = _matches(command, text)

        out: dict[str, Any] = {
            "user_id": session.variables.get("user_id", ""),
            "session_id": session.id,
            "text": text,
            "channel": session.channel or session.variables.get("channel", ""),
            "attachments": session.variables.get("attachments", []),
            "user_meta": session.variables.get("user_meta", {}),
            "matched": matched,
            "command": command,
        }
        if not matched:
            # Runner sentinel: stop the flow before any further node runs.
            out["__halt__"] = True
        return out


register(NodeType.MESSAGE_TRIGGER, MessageTriggerHandler())
