from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from db.crud.chatbot import get_chatbot, delete_chatbot, create_chatbot, list_chatbots_by_user
from db.schemas.chatbot import ChatBotCreate, ChatBotRead

router = APIRouter()

@router.post("/", response_model=ChatBotRead)
async def create_chatbot_endpoint(
    session: AsyncSession,
    chatbot: ChatBotCreate
):
    new_chatbot = await create_chatbot(session, chatbot.name, chatbot.description, chatbot.user_id)
    return new_chatbot

@router.get("/{chatbot_name}", response_model=ChatBotRead)
async def get_chatbot_by_name(
    session: AsyncSession,
    chatbot_name: str,
    user_id: int
):
    chatbot = await get_chatbot(session, chatbot_name, user_id)
    return chatbot

@router.get("/{user_id}", response_model=ChatBotRead)
async def list_users(session: AsyncSession, user_id: int):
    result = await list_chatbots_by_user(session, user_id)
    return result

@router.get("/delete", response_model=ChatBotRead)
async def delete_user(
    session: AsyncSession,
    chatbot_name: str,
    user_id: int
):
    return await delete_chatbot(session, chatbot_name, user_id)
    