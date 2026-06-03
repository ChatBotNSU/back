from __future__ import annotations

from typing import Any

from models.node import Node, ExecCondition
from models.session import Session


def resolve_data_in(node: Node, session: Session) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, port in node.data_in.items():
        if port.from_:
            # "node_id.output_key" or just "node_id" (takes whole output)
            parts = port.from_.split(".", 1)
            source_node_id = parts[0]
            output_key = parts[1] if len(parts) == 2 else None
            node_out = session.node_outputs.get(source_node_id, {})
            result[field] = node_out.get(output_key) if output_key else node_out
        else:
            # fall back to session variables
            result[field] = session.variables.get(field)
    return result


def _get_value(path: str, data_out: dict[str, Any], session: Session) -> Any:
    """
    Resolve a $data.key or $session.key path.
    Plain keys are looked up in data_out first, then session.variables.
    """
    if path.startswith("$data."):
        key = path[len("$data."):]
        return _nested_get(data_out, key)
    if path.startswith("$session."):
        key = path[len("$session."):]
        return _nested_get(session.variables, key)
    # bare name
    if path in data_out:
        return data_out[path]
    return session.variables.get(path)


def _nested_get(obj: Any, key: str) -> Any:
    """Support dot-notation for nested dicts: 'a.b.c'"""
    parts = key.split(".")
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _matches(condition: ExecCondition, value: Any) -> bool:
    if condition.eq is not None:
        return value == condition.eq
    if condition.neq is not None:
        return value != condition.neq
    if condition.gt is not None:
        return value is not None and value > condition.gt
    if condition.lt is not None:
        return value is not None and value < condition.lt
    if condition.contains is not None:
        if isinstance(value, str):
            return condition.contains in value
        if isinstance(value, list):
            return condition.contains in value
        return False
    if condition.exists is not None:
        return (value is not None) == condition.exists
    if condition.not_exists is not None:
        return (value is None) == condition.not_exists
    if condition.in_ is not None:
        return value in condition.in_
    return False


def resolve_exec_out(
    node: Node,
    data_out: dict[str, Any],
    session: Session,
) -> str | None:
    for condition in node.exec_out.conditions:
        value = _get_value(condition.if_, data_out, session)
        if _matches(condition, value):
            return condition.goto
    return node.exec_out.fallback
