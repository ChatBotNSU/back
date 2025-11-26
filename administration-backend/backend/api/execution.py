from datetime import datetime
import json
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from config import get_config
from dto import InMessage, ExecutionRequest, ExecutionResponse
from dto.execution import ExecutionCreate, ExecutionRead, ExecutionUpdate
from auth import get_current_active_user
from entities.User import User

from db.exec_request import create_execution, update_execution

router = APIRouter()


_redis = None

async def get_redis() -> Redis:
    global _redis
    config = get_config()
    
    if _redis is None:
        _redis = Redis(
            host=config.redis.host, 
            port=config.redis.port, 
            decode_responses=True
        )
    
    return _redis

async def wait_for_response(execution_id: int, redis: Redis, timeout: int = 30000) -> ExecutionResponse:
    config = get_config()
    stream_responses = config.redis.IOStream.stream_responses
    
    start_time = datetime.now().timestamp() * 1000
    last_id = "0-0"
    
    while (datetime.now().timestamp() * 1000 - start_time) < timeout:
        response = await redis.xread(
            streams={stream_responses: last_id},
            count=10,
            block=5000
        )
        
        if response:
            for stream_name, messages in response:
                for msg_id, data in messages:
                    payload = data.get("payload")
                    if payload:
                        try:
                            content = json.loads(payload)
                            if content.get("execution_id") == execution_id:
                                return ExecutionResponse(**content)
                        except json.JSONDecodeError:
                            continue
                    last_id = msg_id
        
        if (datetime.now().timestamp() * 1000 - start_time) >= timeout:
            break
    
    raise HTTPException(
        status_code=status.HTTP_408_REQUEST_TIMEOUT,
        detail="Response timeout from engine service"
    )

@router.post("/send", response_model=ExecutionResponse)
async def send_message(
    message: InMessage,
    chatbot_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    timeout: int = 30000,
    redis: Redis = Depends(get_redis)
):
    try:
        config = get_config()
        stream_requests = config.redis.IOStream.stream_requests
        
        execution = await create_execution(
            chatbot_id=chatbot_id,
            user_id=current_user.id
        )
        
        execution_request = ExecutionRequest(
            execution_id=execution.id,
            chatbot_id=chatbot_id,
            message=message
        )
        
        message_id = await redis.xadd(
            stream_requests,
            {"payload": execution_request.model_dump_json()},
            maxlen=1000
        )
        
        print(f"Message sent to Redis: execution_id={execution.id}, redis_id={message_id}")
        
        response = await wait_for_response(execution.id, redis, timeout)
        
        if response.message and hasattr(response.message, 'variable_values'):
            await update_execution(
                execution_id=str(execution.id),
                variable_values=response.message.variable_values
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )
