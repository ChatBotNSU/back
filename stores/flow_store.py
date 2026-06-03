from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from db.models import FlowRow, FlowVersionRow
from models.flow import Flow
from models.node import Node, NodeType, ExecOut, ExecCondition, DataInPort, NodePosition


# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class FlowStore(Protocol):
    async def get(self, flow_id: str, workspace_id: str | None = None) -> Flow | None: ...
    async def get_version(self, flow_id: str, version: int) -> Flow | None: ...
    async def list_versions(self, flow_id: str) -> list[dict[str, Any]]: ...
    async def save(self, flow: Flow) -> None: ...
    async def create_version(self, flow_id: str, workspace_id: str | None = None) -> Flow | None: ...
    async def delete(self, flow_id: str, workspace_id: str | None = None) -> None: ...
    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None, limit: int = 100
    ) -> list[Flow]: ...


# ─── Serialisation helpers ────────────────────────────────────────────────────

def _nodes_to_json(flow: Flow) -> dict[str, Any]:
    return {nid: n.model_dump(by_alias=True) for nid, n in flow.nodes.items()}


def _nodes_from_json(raw_nodes: dict[str, Any]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for nid, raw in (raw_nodes or {}).items():
        exec_out_raw = raw.pop("exec_out", {}) if isinstance(raw, dict) else {}
        conditions = [ExecCondition(**c) for c in exec_out_raw.get("conditions", [])]
        exec_out = ExecOut(conditions=conditions, fallback=exec_out_raw.get("fallback"))
        data_in: dict[str, DataInPort] = {}
        for fname, fraw in (raw.get("data_in") or {}).items():
            data_in[fname] = DataInPort(**fraw)
        pos_raw = raw.get("position", {}) or {}
        nodes[nid] = Node(
            id=raw.get("id", nid),
            type=NodeType(raw["type"]),
            label=raw.get("label", ""),
            data_in=data_in,
            data_out=raw.get("data_out", {}),
            config=raw.get("config", {}),
            exec_out=exec_out,
            position=NodePosition(x=pos_raw.get("x", 0), y=pos_raw.get("y", 0)),
        )
    return nodes


def _flow_to_row(flow: Flow) -> FlowRow:
    return FlowRow(
        id=flow.id,
        workspace_id=flow.workspace_id,
        project_id=flow.project_id,
        name=flow.name,
        description=flow.description,
        nodes=_nodes_to_json(flow),
        start_node=flow.start_node,
        version=flow.version,
        meta=flow.metadata,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
    )


def _snapshot_data(flow: Flow) -> dict[str, Any]:
    return {
        "workspace_id": flow.workspace_id,
        "project_id": flow.project_id,
        "name": flow.name,
        "description": flow.description,
        "nodes": _nodes_to_json(flow),
        "start_node": flow.start_node,
        "version": flow.version,
        "metadata": flow.metadata,
    }


def _flow_from_snapshot(flow_id: str, data: dict[str, Any]) -> Flow:
    return Flow(
        id=flow_id,
        workspace_id=data.get("workspace_id", "default"),
        project_id=data.get("project_id", ""),
        name=data.get("name", ""),
        description=data.get("description", ""),
        nodes=_nodes_from_json(data.get("nodes", {})),
        start_node=data.get("start_node"),
        version=data.get("version", 1),
        metadata=data.get("metadata", {}),
    )


def _row_to_flow(row: FlowRow) -> Flow:
    return Flow(
        id=row.id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        nodes=_nodes_from_json(row.nodes or {}),
        start_node=row.start_node,
        version=row.version,
        metadata=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _update_row(row: FlowRow, flow: Flow) -> None:
    row.project_id = flow.project_id
    row.name = flow.name
    row.description = flow.description
    row.nodes = _nodes_to_json(flow)
    row.start_node = flow.start_node
    row.version = flow.version
    row.meta = flow.metadata
    row.updated_at = datetime.now(timezone.utc)


# ─── SQL implementation ───────────────────────────────────────────────────────

class SQLFlowStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, flow_id: str, workspace_id: str | None = None) -> Flow | None:
        async with self._sf() as session:
            row = await session.get(FlowRow, flow_id)
            if row is None:
                return None
            if workspace_id is not None and row.workspace_id != workspace_id:
                return None
            return _row_to_flow(row)

    async def get_version(self, flow_id: str, version: int) -> Flow | None:
        async with self._sf() as session:
            row = await session.get(FlowVersionRow, (flow_id, version))
            return _flow_from_snapshot(flow_id, row.data) if row else None

    async def list_versions(self, flow_id: str) -> list[dict[str, Any]]:
        async with self._sf() as session:
            stmt = (
                select(FlowVersionRow.version, FlowVersionRow.created_at)
                .where(FlowVersionRow.flow_id == flow_id)
                .order_by(FlowVersionRow.version.desc())
            )
            result = await session.execute(stmt)
            return [{"version": v, "created_at": c} for v, c in result.all()]

    async def save(self, flow: Flow) -> None:
        """Upsert the working draft. Versions are committed explicitly via
        :meth:`create_version`; a plain save never snapshots."""
        async with self._sf() as session:
            async with session.begin():
                existing = await session.get(FlowRow, flow.id)
                if existing:
                    flow.version = existing.version  # preserve committed version
                    _update_row(existing, flow)
                else:
                    flow.version = 0  # no committed versions yet
                    session.add(_flow_to_row(flow))

    async def create_version(
        self, flow_id: str, workspace_id: str | None = None
    ) -> Flow | None:
        """Commit the current working draft as a new immutable version."""
        async with self._sf() as session:
            async with session.begin():
                row = await session.get(FlowRow, flow_id)
                if row is None:
                    return None
                if workspace_id is not None and row.workspace_id != workspace_id:
                    return None
                max_version = await session.scalar(
                    select(func.max(FlowVersionRow.version)).where(
                        FlowVersionRow.flow_id == flow_id
                    )
                )
                now = datetime.now(timezone.utc)
                row.version = (max_version or 0) + 1
                row.updated_at = now
                flow = _row_to_flow(row)
                session.add(
                    FlowVersionRow(
                        flow_id=flow_id,
                        version=flow.version,
                        data=_snapshot_data(flow),
                        created_at=now,
                    )
                )
                return flow

    async def delete(self, flow_id: str, workspace_id: str | None = None) -> None:
        async with self._sf() as session:
            async with session.begin():
                if workspace_id is not None:
                    row = await session.get(FlowRow, flow_id)
                    if row is None or row.workspace_id != workspace_id:
                        return
                await session.execute(delete(FlowRow).where(FlowRow.id == flow_id))
                await session.execute(
                    delete(FlowVersionRow).where(FlowVersionRow.flow_id == flow_id)
                )

    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None, limit: int = 100
    ) -> list[Flow]:
        async with self._sf() as session:
            stmt = select(FlowRow)
            if workspace_id is not None:
                stmt = stmt.where(FlowRow.workspace_id == workspace_id)
            if project_id is not None:
                stmt = stmt.where(FlowRow.project_id == project_id)
            stmt = stmt.order_by(FlowRow.updated_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return [_row_to_flow(row) for row in result.scalars()]


# ─── In-memory fallback ───────────────────────────────────────────────────────

class InMemoryFlowStore:
    def __init__(self) -> None:
        self._data: dict[str, Flow] = {}
        self._versions: dict[tuple[str, int], Flow] = {}

    async def get(self, flow_id: str, workspace_id: str | None = None) -> Flow | None:
        flow = self._data.get(flow_id)
        if flow is None:
            return None
        if workspace_id is not None and flow.workspace_id != workspace_id:
            return None
        return flow

    async def get_version(self, flow_id: str, version: int) -> Flow | None:
        return self._versions.get((flow_id, version))

    async def list_versions(self, flow_id: str) -> list[dict[str, Any]]:
        versions = [
            {"version": v, "created_at": flow.updated_at}
            for (fid, v), flow in self._versions.items()
            if fid == flow_id
        ]
        versions.sort(key=lambda x: x["version"], reverse=True)
        return versions

    async def save(self, flow: Flow) -> None:
        """Upsert the working draft only — no version snapshot."""
        existing = self._data.get(flow.id)
        flow.version = existing.version if existing else 0
        self._data[flow.id] = flow

    async def create_version(
        self, flow_id: str, workspace_id: str | None = None
    ) -> Flow | None:
        flow = self._data.get(flow_id)
        if flow is None:
            return None
        if workspace_id is not None and flow.workspace_id != workspace_id:
            return None
        max_version = max(
            (v for (fid, v) in self._versions if fid == flow_id), default=0
        )
        flow.version = max_version + 1
        flow.updated_at = datetime.now(timezone.utc)
        # Store an immutable snapshot copy.
        self._versions[(flow_id, flow.version)] = flow.model_copy(deep=True)
        return flow

    async def delete(self, flow_id: str, workspace_id: str | None = None) -> None:
        flow = self._data.get(flow_id)
        if flow is None:
            return
        if workspace_id is not None and flow.workspace_id != workspace_id:
            return
        self._data.pop(flow_id, None)
        for key in [k for k in self._versions if k[0] == flow_id]:
            self._versions.pop(key, None)

    async def list_all(
        self, workspace_id: str | None = None, project_id: str | None = None, limit: int = 100
    ) -> list[Flow]:
        flows = [
            f for f in self._data.values()
            if (workspace_id is None or f.workspace_id == workspace_id)
            and (project_id is None or f.project_id == project_id)
        ]
        flows.sort(key=lambda f: f.updated_at, reverse=True)
        return flows[:limit]
