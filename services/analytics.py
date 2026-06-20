from __future__ import annotations

from collections import Counter
from typing import Any

from models.flow import Flow
from models.node import NodeType
from models.session import Session


def _reached_end(flow: Flow, session: Session) -> bool:
    """A session 'converted' if it executed any END node."""
    for nid in session.node_outputs:
        node = flow.nodes.get(nid)
        if node is not None and node.type == NodeType.END:
            return True
    return False


def _last_node(session: Session) -> str | None:
    if session.current_node:
        return session.current_node
    if session.node_outputs:
        return list(session.node_outputs)[-1]
    return None


def compute_overview(flow: Flow, sessions: list[Session]) -> dict[str, Any]:
    total = len(sessions)
    by_state: Counter[str] = Counter()
    node_visits: Counter[str] = Counter()
    messages_sent = 0
    completed = 0
    total_steps = 0

    msg_node_ids = {
        nid for nid, n in flow.nodes.items() if n.type == NodeType.SEND_MESSAGE
    }

    for s in sessions:
        by_state[s.state.value] += 1
        total_steps += s.steps_count
        for nid in s.node_outputs:
            node_visits[nid] += 1
            if nid in msg_node_ids:
                messages_sent += 1
        if _reached_end(flow, s):
            completed += 1

    return {
        "flow_id": flow.id,
        "total_sessions": total,
        "by_state": dict(by_state),
        "completed": completed,
        "conversion_rate": round(completed / total, 4) if total else 0.0,
        "messages_sent": messages_sent,
        "avg_steps": round(total_steps / total, 2) if total else 0.0,
        "node_visits": dict(node_visits),
    }


def compute_dropoff(flow: Flow, sessions: list[Session]) -> list[dict[str, Any]]:
    """Where non-converting sessions stopped, most frequent first."""
    counter: Counter[str] = Counter()
    for s in sessions:
        if _reached_end(flow, s):
            continue
        node_id = _last_node(s)
        if node_id:
            counter[node_id] += 1

    rows: list[dict[str, Any]] = []
    for node_id, count in counter.most_common():
        node = flow.nodes.get(node_id)
        rows.append(
            {
                "node_id": node_id,
                "label": node.label if node else "",
                "type": node.type.value if node else None,
                "count": count,
            }
        )
    return rows
