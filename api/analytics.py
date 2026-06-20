from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_api_key, WorkspaceDep
from api.deps import FlowStoreDep, ProjectStoreDep, SessionStoreDep
from services.analytics import compute_dropoff, compute_overview

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/projects/{project_id}")
async def project_overview(
    project_id: str,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    projects: ProjectStoreDep,
    workspace: WorkspaceDep,
    limit: int = 500,
) -> dict[str, Any]:
    """Aggregate analytics across all flows of a project + a per-flow breakdown."""
    if await projects.get(project_id, workspace_id=workspace) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_flows = await flows.list_all(workspace_id=workspace, project_id=project_id, limit=1000)

    per_flow: list[dict[str, Any]] = []
    total_sessions = total_completed = total_messages = 0

    for flow in project_flows:
        sess = await sessions.list_by_flow(flow.id, limit=limit)
        ov = compute_overview(flow, sess)
        per_flow.append({
            "flow_id": flow.id,
            "name": flow.name,
            "total_sessions": ov["total_sessions"],
            "completed": ov["completed"],
            "conversion_rate": ov["conversion_rate"],
            "messages_sent": ov["messages_sent"],
        })
        total_sessions += ov["total_sessions"]
        total_completed += ov["completed"]
        total_messages += ov["messages_sent"]

    per_flow.sort(key=lambda f: f["total_sessions"], reverse=True)
    return {
        "project_id": project_id,
        "totals": {
            "flows": len(project_flows),
            "sessions": total_sessions,
            "completed": total_completed,
            "messages_sent": total_messages,
            "conversion_rate": round(total_completed / total_sessions, 4) if total_sessions else 0.0,
        },
        "flows": per_flow,
    }


@router.get("/flows/{flow_id}/overview")
async def flow_overview(
    flow_id: str,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    workspace: WorkspaceDep,
    limit: int = 500,
) -> dict[str, Any]:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    all_sessions = await sessions.list_by_flow(flow_id, limit=limit)
    return compute_overview(flow, all_sessions)


@router.get("/flows/{flow_id}/dropoff")
async def flow_dropoff(
    flow_id: str,
    flows: FlowStoreDep,
    sessions: SessionStoreDep,
    workspace: WorkspaceDep,
    limit: int = 500,
) -> dict[str, Any]:
    flow = await flows.get(flow_id, workspace_id=workspace)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    all_sessions = await sessions.list_by_flow(flow_id, limit=limit)
    return {"flow_id": flow_id, "dropoff": compute_dropoff(flow, all_sessions)}
