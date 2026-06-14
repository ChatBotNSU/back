from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class LoopHandler:
    """
    Iterates over array_var, runs body_node for each item (sequentially),
    and collects results.

    NOTE: The actual body execution is delegated to the runner via a special
    __loop_items__ signal.  The runner recognises this and orchestrates the
    sub-cycles itself.  Here we just set up the iteration context.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        array_var = config.get("array_var", "")
        item_var = config.get("item_var", "item")
        filter_expr = config.get("filter")
        max_items: int = int(config.get("max_items", 100))
        body_node: str = config.get("body_node", "")

        items: list[Any] = (
            data_in.get(array_var)
            or session.variables.get(array_var)
            or []
        )

        if not isinstance(items, list):
            items = list(items) if hasattr(items, "__iter__") else []

        # Apply simple equality filter: {"field": "value"}
        if filter_expr and isinstance(filter_expr, dict):
            filtered = []
            for item in items:
                if isinstance(item, dict):
                    if all(item.get(k) == v for k, v in filter_expr.items()):
                        filtered.append(item)
            items = filtered

        items = items[:max_items]

        results: list[Any] = []
        for item in items:
            session.variables[item_var] = item
            # body_node is noted here; full sub-execution is done by the runner
            # when it sees __loop_body__ in the output.
            results.append(item)  # placeholder — real results come from sub-runs

        return {
            "results": results,
            "count": len(results),
            "__loop_body__": body_node,
            "__loop_items__": items,
            "__loop_item_var__": item_var,
        }


register(NodeType.LOOP, LoopHandler())
