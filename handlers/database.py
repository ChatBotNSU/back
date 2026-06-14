from __future__ import annotations

from typing import Any

from engine.registry import register
from models.node import Node, NodeType
from models.session import Session
from stores import data_store


def _render(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return ctx.get(value[2:-2].strip())
    if isinstance(value, dict):
        return {k: _render(v, ctx) for k, v in value.items()}
    return value


class DatabaseHandler:
    """
    CRUD over a project's built-in data tables.

    config: {action: insert|get|query|update|delete, table, data, where, record_id, output_var}
    Scopes to session.project_id (or config.project_id override).
    """

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        store = data_store.active()
        if store is None:
            return {"ok": False, "error": "data store unavailable", "record": None, "records": []}

        project_id = config.get("project_id") or session.project_id
        if not project_id:
            return {"ok": False, "error": "no project_id in session", "record": None, "records": []}

        action = config.get("action", "query")
        table = config.get("table", "")
        ctx = {**session.variables, **data_in}
        data = _render(config.get("data", {}), ctx) or {}
        where = _render(config.get("where", {}), ctx) or {}
        record_id = _render(config.get("record_id"), ctx)

        result: dict[str, Any]
        if action == "insert":
            rec = await store.insert(project_id, table, data)
            result = {"ok": True, "record": rec.to_dict(), "records": []}
        elif action == "get":
            rec = await store.get(project_id, table, record_id) if record_id else None
            result = {"ok": rec is not None, "record": rec.to_dict() if rec else None, "records": []}
        elif action == "update":
            rec = await store.update(project_id, table, record_id, data) if record_id else None
            result = {"ok": rec is not None, "record": rec.to_dict() if rec else None, "records": []}
        elif action == "delete":
            ok = await store.delete(project_id, table, record_id) if record_id else False
            result = {"ok": ok, "record": None, "records": []}
        else:  # query
            recs = await store.query(project_id, table, where, limit=int(config.get("limit", 100)))
            result = {"ok": True, "record": None, "records": [r.to_dict() for r in recs],
                      "count": len(recs)}

        output_var = config.get("output_var")
        if output_var:
            session.variables[output_var] = result.get("records") or result.get("record")
        return result


register(NodeType.DATABASE, DatabaseHandler())
