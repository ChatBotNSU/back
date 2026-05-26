from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException

from api.middleware import get_current_active_user
from entities.User import User
from models.chatbot import Subgraph

from minio_controller.S3Client import S3Client


router = APIRouter()


@router.get("/subgraphs", response_model=List[str])
async def list_subgraphs(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """List names of all subgraphs owned by the current user."""
    return S3Client.get_instance().list_subgraph_names(current_user.id)


@router.post("/subgraphs", response_model=Subgraph, status_code=201)
async def create_subgraph(
    subgraph: Subgraph,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Create a new subgraph under the current user's namespace.

    Fails with 409 if a subgraph with the same name already exists.
    """
    s3 = S3Client.get_instance()
    if s3.subgraph_exists(current_user.id, subgraph.name):
        raise HTTPException(
            status_code=409,
            detail=f"Subgraph '{subgraph.name}' already exists",
        )
    s3.upload_subgraph(current_user.id, subgraph)
    return subgraph


@router.get("/subgraph/{name}", response_model=Subgraph)
async def read_subgraph(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    s3 = S3Client.get_instance()
    if not s3.subgraph_exists(current_user.id, name):
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")
    return s3.download_subgraph(current_user.id, name)


@router.put("/subgraph/{name}", response_model=Subgraph)
async def update_subgraph(
    name: str,
    subgraph: Subgraph,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    if subgraph.name != name:
        raise HTTPException(
            status_code=400,
            detail=f"Path name '{name}' does not match body name '{subgraph.name}'",
        )
    s3 = S3Client.get_instance()
    if not s3.subgraph_exists(current_user.id, name):
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")
    s3.upload_subgraph(current_user.id, subgraph)
    return subgraph


@router.delete("/subgraph/{name}")
async def delete_subgraph(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    s3 = S3Client.get_instance()
    if not s3.subgraph_exists(current_user.id, name):
        raise HTTPException(status_code=404, detail=f"Subgraph '{name}' not found")
    s3.delete_subgraph(current_user.id, name)
    return {"ok": True, "name": name}
