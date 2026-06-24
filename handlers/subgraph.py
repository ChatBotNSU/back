from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session


class SubgraphHandler:
    """
    Signals the runner to switch to another flow. The runner reads
    `input_mapping`, `output_mapping` and `isolated` from `node.config` to
    decide whether to enter the child flow in an isolated variable scope
    (function-call semantics) or in the legacy shared-scope mode.

    For back-compat, when `isolated` is false (or absent and no mappings are
    set), the legacy behavior is preserved: the `inputs` dict on the config
    is written directly into the shared session variables before entering.
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        flow_id: str = config.get("flow_id", "")
        flow_version = config.get("flow_version")  # optional → pin child version

        # Legacy shared-scope `inputs` writing (only when isolation is NOT on).
        if not _is_isolated(config):
            ctx = {**session.variables, **data_in}
            for key, val in (config.get("inputs") or {}).items():
                if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                    var_name = val[2:-2].strip()
                    session.variables[key] = ctx.get(var_name)
                else:
                    session.variables[key] = val

        # Encode pinned version as "flow_id@version"; loader resolves the snapshot.
        ref = f"{flow_id}@{flow_version}" if flow_version is not None else flow_id

        return {
            "__subgraph_flow_id__": ref,
            "outputs": {},
            "status": "started",
            "duration_ms": 0,
        }


def _is_isolated(config: dict[str, Any]) -> bool:
    """A subgraph runs isolated when either the user opted in explicitly via
    `isolated: true`, or when an input/output mapping is configured."""
    if config.get("isolated"):
        return True
    if config.get("input_mapping"):
        return True
    if config.get("output_mapping"):
        return True
    return False


register(NodeType.SUBGRAPH, SubgraphHandler())
