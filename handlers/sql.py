from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session
from services import connections

logger = logging.getLogger(__name__)

_MAX_ROWS = 1000


def _render(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return ctx.get(value[2:-2].strip())
    if isinstance(value, dict):
        return {k: _render(v, ctx) for k, v in value.items()}
    return value


class SqlHandler:
    """
    Runs parameterized SQL against an external DB defined by a project `db`
    integration (DSN comes from a referenced secret). The query is the flow
    author's own SQL against their own database; values are bound parameters.

    config: {connection|integration: name, sql: "... :param ...", params: {...}, output_var}
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        # Allow `connection` as an alias for `integration`.
        if "connection" in config and "integration" not in config:
            config = {**config, "integration": config["connection"]}
        config = await connections.resolve(config, session)

        dsn = config.get("dsn")
        if not dsn:
            return {"ok": False, "error": "no DSN configured", "rows": []}

        query = config.get("sql", "")
        ctx = {**session.variables, **data_in}
        params = _render(config.get("params", {}), ctx) or {}

        engine = None
        try:
            engine = create_async_engine(dsn)
            async with engine.begin() as conn:
                result = await conn.execute(text(query), params)
                if result.returns_rows:
                    rows = [dict(r._mapping) for r in result.fetchmany(_MAX_ROWS)]
                    out: dict[str, Any] = {"ok": True, "rows": rows, "count": len(rows)}
                else:
                    out = {"ok": True, "rows": [], "rowcount": result.rowcount}
        except Exception as exc:  # noqa: BLE001
            logger.warning("SQL node failed: %s", exc)
            return {"ok": False, "error": str(exc), "rows": []}
        finally:
            if engine is not None:
                await engine.dispose()

        output_var = config.get("output_var")
        if output_var:
            session.variables[output_var] = out["rows"]
        return out


register(NodeType.SQL, SqlHandler())
