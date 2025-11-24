from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.chatbot import get_chatbot, delete_chatbot, create_chatbot, list_chatbots_by_user, update_chatbot
from db.schemas.chatbot import ChatBotCreate, ChatBotRead

router = APIRouter()

@router.post("/", response_model=ChatBotRead)
async def create_chatbot_endpoint(
    chatbot: ChatBotCreate,
    session: AsyncSession = Depends(get_session)
):
    new_chatbot = await create_chatbot(session, chatbot.name, chatbot.description, chatbot.user_id)
    return new_chatbot

@router.get("/{chatbot_name}", response_model=ChatBotRead)
async def get_chatbot_by_name(
    chatbot_name: str,
    user_id: int,
    session: AsyncSession = Depends(get_session)
):
    chatbot = await get_chatbot(session, chatbot_name, user_id)
    return chatbot

@router.get("/{user_id}", response_model=list[ChatBotRead])
async def list_users(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await list_chatbots_by_user(session, user_id)
    return result

@router.get("/delete")
async def delete_user(
    chatbot_name: str,
    user_id: int,
    session: AsyncSession = Depends(get_session)
):
    return await delete_chatbot(session, chatbot_name, user_id)

@router.put("/{chatbot_name}", response_model=ChatBotRead)
async def update_chatbot(
    chatbot_name: str,
    user_id: int,
    description: str,
    session: AsyncSession = Depends(get_session)
):    
    bot = await update_chatbot(session, chatbot_name, user_id, description)
    return bot