from __future__ import annotations

from models.flow import Flow


def validate_flow_graph(flow: Flow) -> list[str]:
    """
    Structural validation of a flow graph.

    Returns a list of human-readable error strings; empty list ⇒ valid.
    Shared by the `/validate` endpoint and the AI-generation retry loop.
    """
    errors: list[str] = []

    if not flow.nodes:
        errors.append("Flow has no nodes")

    if flow.start_node is None:
        errors.append("Flow has no start_node")
    elif flow.start_node not in flow.nodes:
        errors.append(f"start_node '{flow.start_node}' not found in nodes")

    for node_id, node in flow.nodes.items():
        for cond in node.exec_out.conditions:
            if cond.goto not in flow.nodes:
                errors.append(
                    f"Node '{node_id}': condition goto '{cond.goto}' not found"
                )
        if node.exec_out.fallback and node.exec_out.fallback not in flow.nodes:
            errors.append(
                f"Node '{node_id}': fallback '{node.exec_out.fallback}' not found"
            )

    return errors
