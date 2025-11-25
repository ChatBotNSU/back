from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status, Body
from fastapi import APIRouter

from entities.Token import Token
from utils.minio import save_json_to_minio, update_json_in_minio, delete_json_from_minio, get_json_from_minio
from db.chatbot_request import create_chatbot, get_chatbot_by_name, get_chatbots_by_user, delete_chatbot, update_chatbot
from entities.User import User
from dto.chatbot import ChatBotCreateRequest, ChatBotListResponse, ChatBotResponse, ChatBotUpdateRequest
from config import get_config
from .auth import get_current_active_user

config = get_config()
router = APIRouter()

@router.post("/", response_model=ChatBotResponse)
async def create_chatbot_endpoint(
    chatbot_data: ChatBotCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        chatbot = await create_chatbot(
            name=chatbot_data.name,
            description=chatbot_data.description,
            user_id=current_user.id,
            key=f"json/{chatbot_data.name}_{current_user.id}.json"
        )
        
        object_key = save_json_to_minio(
            data=chatbot_data.config,
            bot_name=chatbot_data.name,
            user_id=current_user.id
        )
        
        return ChatBotResponse(
            id=chatbot.id,
            name=chatbot.name,
            description=chatbot.description,
            user_id=chatbot.user_id,
            config=chatbot_data.config
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании чатбота: {str(e)}"
        )

@router.get("/{chatbot_name}", response_model=ChatBotResponse)
async def get_chatbot_endpoint(
    chatbot_name: str,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        chatbot = await get_chatbot_by_name(chatbot_name, current_user.id)
        
        object_key = f"json/{chatbot_name}_{current_user.id}.json"
        config_data = get_json_from_minio(object_key)
        
        return ChatBotResponse(
            id=chatbot.id,
            name=chatbot.name,
            description=chatbot.description,
            user_id=chatbot.user_id,
            config=config_data
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Чатбот не найден: {str(e)}"
        )

@router.get("/user/me", response_model=ChatBotListResponse)
async def get_my_chatbots_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        chatbots = await get_chatbots_by_user(current_user.id)
        
        chatbot_responses = []
        for chatbot in chatbots:
            try:
                object_key = f"json/{chatbot.name}_{current_user.id}.json"
                config_data = get_json_from_minio(object_key)
            except:
                config_data = {}
                
            chatbot_responses.append(ChatBotResponse(
                id=chatbot.id,
                name=chatbot.name,
                description=chatbot.description,
                user_id=chatbot.user_id,
                config=config_data
            ))
        
        return ChatBotListResponse(chatbots=chatbot_responses)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении чатботов: {str(e)}"
        )

@router.put("/{chatbot_name}", response_model=ChatBotResponse)
async def update_chatbot_endpoint(
    chatbot_name: str,
    update_data: ChatBotUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        chatbot = await update_chatbot(
            chatbot_name=chatbot_name,
            user_id=current_user.id,
            description=update_data.description
        )
        
        object_key = f"json/{chatbot_name}_{current_user.id}.json"
        update_json_in_minio(object_key, update_data.config)
        
        return ChatBotResponse(
            id=chatbot.id,
            name=chatbot.name,
            description=chatbot.description,
            user_id=chatbot.user_id,
            config=update_data.config
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении чатбота: {str(e)}"
        )

@router.delete("/{chatbot_name}")
async def delete_chatbot_endpoint(
    chatbot_name: str,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    try:
        delete_result = await delete_chatbot(chatbot_name, current_user.id)
        
        object_key = f"json/{chatbot_name}_{current_user.id}.json"
        delete_json_from_minio(object_key)
        
        return {"message": "Чатбот успешно удален", "success": delete_result}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при удалении чатбота: {str(e)}"
        )