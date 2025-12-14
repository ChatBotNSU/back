import logging
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from controller.redis_streams import RedisStreamsController
from sender.preview_sender import PreviewResponseSender
from models.message import OutMessage, InMessage
from models.redis_io_streams import ExecutionRequest, ExecutionResponse

logger = logging.getLogger("app")

router = APIRouter()

controller = RedisStreamsController.get_instance()
poller = PreviewResponseSender.get_instance()

@router.post("/process", response_model=OutMessage)
async def process_preview(chatbot_id: int, execution_id: int, message: InMessage) -> OutMessage:
    request = ExecutionRequest(
        execution_id = execution_id,
        chatbot_id = chatbot_id,
        message = message
    )
        
    future = await poller.add_future(execution_id)
        
    await controller.put_message(request)
    
    result = await asyncio.wait_for(future)
    return result


@router.get("/get_execution_id", response_model=int)
async def get_execution_id() -> int:
    return controller.get_execution_id()