from typing import Annotated

from fastapi import Depends, APIRouter
from api.middleware import get_current_active_user
from entities.User import User
from models.chatbot import Chatbot, ChatbotUnassigned

from db.chatbot_request import get_chatbots, create_chatbot, delete_chatbot

from minio_controller.S3Client import S3Client


router = APIRouter()

@router.get("/chatbots")
async def read_chatbots(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await get_chatbots(current_user.id)

@router.post("/chatbots", response_model=Chatbot)
async def create_chatbot_endpoint(
    chatbot: ChatbotUnassigned,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    name = chatbot.bot_name
    description="Chatbots dont have descriptions and dont cry"

    result = await create_chatbot(current_user.id, name, description)

    chatbot_cool = Chatbot(**chatbot.model_dump(), bot_id=result["id"])
    S3Client.get_instance().upload_chatbot(result["id"], chatbot_cool)

    return chatbot_cool


@router.get("/chatbot/{chatbot_id}", response_model=Chatbot)
async def read_chatbot(
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: check ownership
    return S3Client.get_instance().download_chatbot(chatbot_id)

@router.post("/chatbot/{chatbot_id}", response_model=Chatbot)
async def update_chatbot(
    chatbot_id: int,
    chatbot: ChatbotUnassigned,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: Check ownership
    chatbot_cool = Chatbot(**chatbot.model_dump(), bot_id=chatbot_id)
    S3Client.get_instance().upload_chatbot(chatbot_id, chatbot_cool)
    return chatbot_cool

@router.delete("/chatbot/{chatbot_id}")
async def delete_chatbot_endpoint(
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    # TODO: Check ownership
    await delete_chatbot(chatbot_id)
