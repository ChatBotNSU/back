from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.execution import create_execution, list_executions_for_chatbot, get_execution, update_execution_variables, delete_execution
from db.schemas.excution import ExecutionCreate, ExecutionRead, ExecutionUpdate

router = APIRouter()


@router.post("/", response_model=ExecutionRead)
async def create_exec_endpoint(
    exec: ExecutionCreate,
    session: AsyncSession = Depends(get_session)
):
    new_exec = await create_execution(session, exec.chatbot_id, exec.user_id)
    return new_exec

@router.get("/", response_model=ExecutionRead)
async def get_execution(
    execution_id: str,
    session: AsyncSession = Depends(get_session)
):
    exec = await get_execution(session, execution_id)
    return exec

@router.get("/{chatbot_id}", response_model=list[ExecutionRead])
async def list_execution(chatbot_id: int, session: AsyncSession = Depends(get_session)):
    result = await list_executions_for_chatbot(session, chatbot_id)
    return result

@router.get("/delete")
async def delete_execution(
    execution_id: str,
    session: AsyncSession = Depends(get_session)
):
    return await delete_execution(session, execution_id)

@router.put("/{exec_id}", response_model=ExecutionRead)
async def update_execution(
    exec_id: str,
    update: ExecutionUpdate,
    session: AsyncSession = Depends(get_session)
):    
    exec = await update_execution_variables(
        session, exec_id, update.executing_node_id, update.variable_values
        )
    return exec