from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.chatbot import create_chatbot, list_chatbots_by_user, delete_chatbot, get_chatbot, update_chatbot
from db.schemas.user import UserCreate, UserRead

router = APIRouter()


@router.get("/list")
async def list_chatbots(user_id: int,session: AsyncSession = Depends(get_session)):
    users = await list_chatbots_by_user(session, user_id=user_id)
    return users


@router.post("/create")
async def create_chatbot_endpoint(user_id: int, name: str, description: str, session: AsyncSession = Depends(get_session)):
    new_chatbot = await create_chatbot(session, name, description, user_id)
    return new_chatbot

@router.post("/modify")
async def modify_chatbot_endpoint(bot_id: int, name: str, description: str, session: AsyncSession = Depends(get_session)):
    new_chatbot = await update_chatbot(session, bot_id, name=name, description=description)
    return new_chatbot

@router.delete("/delete")
async def delete_chatbot_endpoint(bot_id: int, session: AsyncSession = Depends(get_session)):
    result = await delete_chatbot(session, bot_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Chatbot with id '{bot_id}' not found")
    return result

@router.get("/get_by_id")
async def get_chatbot_endpoint(bot_id: int, session: AsyncSession = Depends(get_session)):
    chatbot = await get_chatbot(session, bot_id)
    if not chatbot:
        raise HTTPException(status_code=404, detail=f"Chatbot with id '{bot_id}' not found")
    return chatbot
