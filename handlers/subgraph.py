from __future__ import annotations

from typing import Any, TYPE_CHECKING

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session

if TYPE_CHECKING:
    pass


class SubgraphHandler:
    """
    Pushes the current position onto the call stack and redirects execution
    to another flow's start node.  The runner handles the stack pop when it
    reaches an `end` node with a non-empty call_stack.

    The child flow must be loaded by the runner ahead of time and passed
    through session.variables['__subgraph_flows__'][flow_id].
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        flow_id: str = config.get("flow_id", "")
        flow_version = config.get("flow_version")  # optional int → pin child version
        inputs: dict = config.get("inputs", {})

        ctx = {**session.variables, **data_in}
        for key, val in inputs.items():
            if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                var_name = val[2:-2].strip()
                session.variables[key] = ctx.get(var_name)
            else:
                session.variables[key] = val

        # Encode a pinned version as "flow_id@version"; the runner's flow_loader
        # resolves the snapshot. Without a version it loads the latest flow.
        ref = f"{flow_id}@{flow_version}" if flow_version is not None else flow_id

        # The runner will see __subgraph_flow_id__ and switch flows
        return {
            "__subgraph_flow_id__": ref,
            "outputs": {},
            "status": "started",
            "duration_ms": 0,
        }


register(NodeType.SUBGRAPH, SubgraphHandler())
