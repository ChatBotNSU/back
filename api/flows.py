from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_key, WorkspaceDep
from api.deps import BotStoreDep, FlowStoreDep, SessionStoreDep
from config import settings
from engine.loader import make_flow_loader
from engine.runner import resume_flow, start_flow
from engine.validation import validate_flow_graph
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from models.session import Session, SessionState
from services import llm
from services.flow_ai import FlowGenerationError, generate_flow, improve_flow

router = APIRouter(prefix="/api/flows", tags=["flows"], dependencies=[Depends(require_api_key)])


# ─── Request / Response schemas ───────────────────────────────────────────────

class NodeIn(BaseModel):
    id: str
    type: NodeType
    label: str = ""
    data_in: dict[str, Any] = {}
    data_out: dict[str, str] = {}
    config: dict[str, Any] = {}
    exec_out: dict[str, Any] = {}
    position: dict[str, float] = {"x": 0, "y": 0}


class FlowCreate(BaseModel):
    name: str
    description: str = ""
    project_id: str = ""
    nodes: list[NodeIn] = []
    start_node: str | None = None
    metadata: dict[str, Any] = {}


class FlowGenerateRequest(BaseModel):
    prompt: str
    model: str | None = None
    project_id: str = ""
    save: bool = True


class FlowImproveRequest(BaseModel):
    chat_history: list[dict[str, Any]] = []
    model: str | None = None


class FlowImproveResponse(BaseModel):
    flow_id: str
    suggestions: list[dict[str, Any]]
    summary: str = ""


class FlowRunRequest(BaseModel):
    message: str = ""
    session_id: str | None = None


class FlowRunResponse(BaseModel):
    session_id: str
    state: SessionState
    waiting: bool
    current_node: str | None
    messages: list[dict[str, Any]]
    slot_question: str | None = None
    error: str | None = None


class FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list[NodeIn] | None = None
    start_node: str | None = None
    metadata: dict[str, Any] | None = None


class FlowSummary(BaseModel):
    id: str
    name: str
    description: str
    project_id: str = ""
    node_count: int
    start_node: str | None
    version: int = 1
    created_at: datetime
    updated_at: datetime


class FlowDetail(FlowSummary):
    nodes: list[dict[str, Any]]
    metadata: dict[str, Any]


class FlowVersionInfo(BaseModel):
    version: int
    created_at: datetime


class FlowVersionsResponse(BaseModel):
    latest: int
    versions: list[FlowVersionInfo]
    # True when the working draft has changes not captured in the latest version.
    draft_dirty: bool = False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _flow_to_detail(flow: Flow) -> FlowDetail:
    return FlowDetail(
        id=flow.id,
        name=flow.name,
        description=flow.description,
        project_id=flow.project_id,
        node_count=len(flow.nodes),
        start_node=flow.start_node,
        version=flow.version,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
        nodes=[n.model_dump(by_alias=True) for n in flow.nodes.values()],
        metadata=flow.metadata,
    )


def _content_fingerprint(flow: Flow) -> Any:
    """The parts of a flow that define its behaviour, for draft-vs-version
    comparison (ignores id / timestamps / version number)."""
    dump = flow.model_dump(mode="json")
    return {k: dump.get(k) for k in ("name", "description", "start_node", "nodes", "metadata")}


def _nodes_from_input(nodes_in: list[NodeIn]) -> dict[str, Node]:
    result: dict[str, Node] = {}
    for n in nodes_in:
        raw = n.model_dump()
        exec_out_raw = raw.pop("exec_out", {})
        node = Node(
            id=n.id,
            type=n.type,
            label=n.label,
            config=n.config,
            exec_out=ExecOut(**exec_out_raw) if exec_out_raw else ExecOut(),
            position=n.position,  # type: ignore[arg-type]
        )
        result[node.id] = node
    return result


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("", response_model=list[FlowSummary])
async def list_flows(
    flows: FlowStoreDep, workspace: WorkspaceDep, project_id: str | None = None
) -> list[FlowSummary]:
    all_flows = await flows.list_all(workspace_id=workspace, project_id=project_id)
    return [
        FlowSummary(
            id=f.id,
            name=f.name,
            description=f.description,
            project_id=f.project_id,
            node_count=len(f.nodes),
            start_node=f.start_node,
            version=f.version,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in all_flows
    ]


@router.get("/usage")
async def flows_usage(
    flows: FlowStoreDep, bots: BotStoreDep, workspace: WorkspaceDep, project_id: str | None = None
) -> dict[str, dict[str, int]]:
    """Per-flow usage: how many bots publish it and how many flows call it as a subgraph."""
    all_flows = await flows.list_all(workspace_id=workspace, project_id=project_id, limit=1000)
    all_bots = await bots.list_all(workspace_id=workspace, project_id=project_id)

    usage: dict[str, dict[str, int]] = {f.id: {"bots": 0, "subgraph_refs": 0} for f in all_flows}

    for bot in all_bots:
        if bot.flow_id in usage:
            usage[bot.flow_id]["bots"] += 1

    for f in all_flows:
        for node in f.nodes.values():
            if node.type == NodeType.SUBGRAPH:
                ref = str(node.config.get("flow_id", "")).split("@")[0]
                if ref in usage:
                    usage[ref]["subgraph_refs"] += 1

    return usage


@router.post("", response_model=FlowDetail, status_code=201)
async def create_flow(body: FlowCreate, flows: FlowStoreDep, workspace: WorkspaceDep) -> FlowDetail:
    flow = Flow(
        workspace_id=workspace,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        nodes=_nodes_from_input(body.nodes),
        start_node=body.start_node,
        metadata=body.metadata,
    )
    await flows.save(flow)
    # Commit an initial baseline version so the flow always has v1 to pin/restore.
    snap = await flows.create_version(flow.id, workspace_id=workspace)
    return _flow_to_detail(snap or flow)


@router.post("/generate", response_model=FlowDetail, status_code=201)
async def generate_flow_endpoint(
    body: FlowGenerateRequest, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowDetail:
    """AI-generate a runnable flow from a natural-language prompt (main feature)."""
    if not body.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt must not be empty")
    try:
        flow = await generate_flow(body.prompt, model=body.model or settings.llm_model)
    except FlowGenerationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.last_errors},
        )
    flow.workspace_id = workspace
    flow.project_id = body.project_id
    if body.save:
        await flows.save(flow)
        snap = await flows.create_version(flow.id, workspace_id=workspace)
        if snap:
            flow = snap
    return _flow_to_detail(flow)


@router.get("/{flow_id}", response_model=FlowDetail)
async def get_flow(flow_id: str, flows: FlowStoreDep, workspace: WorkspaceDep) -> FlowDetail:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _flow_to_detail(flow)


@router.get("/{flow_id}/versions", response_model=FlowVersionsResponse)
async def list_flow_versions(
    flow_id: str, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowVersionsResponse:
    """Available immutable versions of a flow — used by subgraph nodes to pin
    (or to warn when a pinned version is no longer the latest)."""
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    versions = await flows.list_versions(flow_id)
    latest_snapshot = await flows.get_version(flow_id, flow.version)
    draft_dirty = (
        latest_snapshot is None
        or _content_fingerprint(flow) != _content_fingerprint(latest_snapshot)
    )
    return FlowVersionsResponse(
        latest=flow.version,
        versions=[FlowVersionInfo(**v) for v in versions],
        draft_dirty=draft_dirty,
    )


@router.get("/{flow_id}/versions/{version}", response_model=FlowDetail)
async def get_flow_version(
    flow_id: str, version: int, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowDetail:
    """Full immutable snapshot of a specific flow version — lets the editor
    preview what a subgraph would run at a pinned version."""
    # Workspace guard via the live flow before exposing any snapshot.
    current = await flows.get(flow_id, workspace_id=workspace)
    if current is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    snapshot = await flows.get_version(flow_id, version)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Flow version not found")
    return _flow_to_detail(snapshot)


@router.post("/{flow_id}/versions", response_model=FlowVersionInfo, status_code=201)
async def create_flow_version(
    flow_id: str, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowVersionInfo:
    """Commit the current working draft as a new immutable version. A plain
    save (PUT) only overwrites the draft — versions are created on demand."""
    snap = await flows.create_version(flow_id, workspace_id=workspace)
    if snap is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return FlowVersionInfo(version=snap.version, created_at=snap.updated_at)


@router.put("/{flow_id}", response_model=FlowDetail)
async def update_flow(
    flow_id: str, body: FlowUpdate, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowDetail:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    if body.name is not None:
        flow.name = body.name
    if body.description is not None:
        flow.description = body.description
    if body.nodes is not None:
        flow.nodes = _nodes_from_input(body.nodes)
    if body.start_node is not None:
        flow.start_node = body.start_node
    if body.metadata is not None:
        flow.metadata = body.metadata

    await flows.save(flow)
    return _flow_to_detail(flow)


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(flow_id: str, flows: FlowStoreDep, workspace: WorkspaceDep) -> None:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    await flows.delete(flow_id, workspace_id=workspace)


@router.post("/{flow_id}/validate")
async def validate_flow(flow_id: str, flows: FlowStoreDep, workspace: WorkspaceDep) -> dict[str, Any]:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    errors = validate_flow_graph(flow)
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/{flow_id}/improve", response_model=FlowImproveResponse)
async def improve_flow_endpoint(
    flow_id: str, body: FlowImproveRequest, flows: FlowStoreDep, workspace: WorkspaceDep
) -> FlowImproveResponse:
    """Analyse a flow (optionally with chat history) and suggest improvements."""
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = await improve_flow(
            flow, body.chat_history, model=body.model or settings.llm_model
        )
    except llm.LLMUnavailable:
        raise HTTPException(status_code=503, detail="LLM backend not configured")
    return FlowImproveResponse(
        flow_id=flow_id,
        suggestions=result.get("suggestions", []),
        summary=result.get("summary", ""),
    )


@router.post("/{flow_id}/run", response_model=FlowRunResponse)
async def run_flow_demo(
    flow_id: str,
    body: FlowRunRequest,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    workspace: WorkspaceDep,
) -> FlowRunResponse:
    """
    Synchronous in-browser playground: start a fresh session or resume a waiting
    one with `message`, run it to the next pause, and return the bot's messages.
    """
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    loader = make_flow_loader(flows)

    session: Session | None = None
    if body.session_id:
        session = await sessions.get(body.session_id)
        if session and session.workspace_id != workspace:
            session = None

    if session and session.state == SessionState.WAITING:
        session = await resume_flow(session, flow, body.message, flow_loader=loader)
    else:
        session = Session(flow_id=flow.id, workspace_id=workspace, project_id=flow.project_id)
        session.variables.update({
            "text": body.message,
            "channel": "demo",
            "user_id": "demo",
            "__session_key__": f"demo:{flow.id}",
        })
        session = await start_flow(session, flow, flow_loader=loader)

    await sessions.save(session)
    return FlowRunResponse(
        session_id=session.id,
        state=session.state,
        waiting=session.state == SessionState.WAITING,
        current_node=session.current_node,
        messages=session.variables.get("__messages__", []),
        slot_question=session.variables.get("__slot_question__"),
        error=session.error,
    )
