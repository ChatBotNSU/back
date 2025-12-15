import logging
import json
from typing import Optional
from itertools import count

import asyncio
from redis.asyncio import Redis


from .redis import get_redis
from sender.preview_sender import PreviewResponseSender
from config import get_config
from models.redis_io_streams import ExecutionRequest, ExecutionResponse

logger = logging.getLogger("app")

class RedisStreamsController:
    _instance: Optional["RedisStreamsController"] = None
    _lock = asyncio.Lock()
    _execution_counter = count(start=0)

    def __init__(self):
        config = get_config()
        self.redis = get_redis()
        self.stream_responses = config.redis.IOStream.stream_responses
        self.stream_requests = config.redis.IOStream.stream_requests
        self.group = config.redis.IOStream.group
        self.consumer = config.redis.IOStream.consumer
        self.sender = PreviewResponseSender.get_instance()
        RedisStreamsController._instance = self
        logger.info("RedisStreamsController initialized")
    
    @staticmethod
    def get_instance() -> "RedisStreamsController":
        if RedisStreamsController._instance is None:
            raise RuntimeError("RedisStreamsController not initialized yet. Expected call of constructor beforehand.")
        return RedisStreamsController._instance
    
    def get_execution_id(self) -> int:
        with RedisStreamsController._lock:
            return next(RedisStreamsController._execution_counter)

    async def put_message(self, request: ExecutionRequest):
        await self.redis.xadd(self.stream_requests,
                              {"payload": request.model_dump_json()})
    
    async def poll_responses(self):
        while True:
            try:
                response = await self.redis.xreadgroup(
                        self.group,
                        self.consumer,
                        streams={self.stream_responses: ">"},
                        count=1,
                        block=5000
                    )
                if not response:
                    logger.info("NO FUCKEN Response")
                    continue

                for stream_name, messages in response:
                    for msg_id, data in messages:
                        logger.info(f"Received shit {msg_id}: {data}")

                        payload = data.get("payload")
                        logger.info(f"Processing payload: {payload}")

                        try:
                            content = json.loads(payload)
                        except Exception as e:
                            logger.info("FUCKEN WRONG JSON")
                            continue
                    
                        try:
                            content = ExecutionResponse(**content)
                        except Exception as e:
                            logger.info(f"It is not ExecutionResponse")
                            continue

                        contains = await self.sender.send_response(content)
                        if not contains:
                            await self.redis.xadd(self.stream_responses,
                              {"payload": content.model_dump_json()})
            except Exception as e:
                logger.info(f"Error: {e}")
                await asyncio.sleep(1)
