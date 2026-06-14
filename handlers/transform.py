from __future__ import annotations

import re
from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


def _render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replacer(m: re.Match) -> str:
            key = m.group(1).strip()
            parts = key.split(".")
            v: Any = variables
            for p in parts:
                if isinstance(v, dict):
                    v = v.get(p)
                else:
                    v = None
                    break
            return str(v) if v is not None else m.group(0)
        return re.sub(r"\{\{(.+?)\}\}", replacer, value)
    if isinstance(value, dict):
        return {k: _render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    return value


class TransformHandler:
    """
    Maps fields from session/data_in to a new output object.
    Each mapping: { "from": "{{var.key}}", "to": "output_field" }
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        vars_ctx = {**session.variables, **data_in}
        mappings: list[dict[str, Any]] = config.get("mappings", [])
        result: dict[str, Any] = {}

        for mapping in mappings:
            source = mapping.get("from", "")
            dest = mapping.get("to", "")
            if not dest:
                continue
            rendered = _render(source, vars_ctx)
            result[dest] = rendered

        output_var = config.get("output_var")
        if output_var:
            session.variables[output_var] = result

        return {"result": result}


register(NodeType.TRANSFORM, TransformHandler())
