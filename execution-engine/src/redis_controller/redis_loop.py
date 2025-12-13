import logging
import json
from typing import Callable, Awaitable

import asyncio
from redis.asyncio import Redis
from redis.exceptions import ResponseError


from .redis import get_redis
from config import get_config
from models import ExecutionRequest, ExecutionResponse

logger = logging.getLogger("app")


async def redis_router(request_processor: Callable[[ExecutionRequest], Awaitable[ExecutionResponse]]):
    redis = get_redis()
    config = get_config()
    stream_responses = config.redis.IOStream.stream_responses
    stream_requests = config.redis.IOStream.stream_requests
    group = config.redis.IOStream.group
    consumer = config.redis.IOStream.consumer


    # This part of code recreates readers group
    # We do that because we restart redis container everytime we restart the engine
    # Therefore, there is no need to recreate the group manually. We are good with that
    try:
        await redis.xgroup_create(name=stream_requests, groupname=group, id="$", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise

    # Redis loop
    # Waits for ExecutionRequest -> sends it request_processor -> sends ExecutionResponse
    while True:
        logger.info("I BEG YOU!!!")
        try:
            response = await redis.xreadgroup(
                group,
                consumer,
                streams={stream_requests: ">"},
                count=1,
                block=5000
            )
            if not response:
                logger.info("NO FUCKEN REQUEST")
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
                        content = ExecutionRequest(**content)
                    except Exception as e:
                        logger.info(f"It is not ExecutionRequest")
                        continue
                    
                    response = await request_processor(content)

                    await redis.xadd(stream_responses,
                                      {"payload": response.model_dump_json()})


                    await redis.xack(stream_requests, group, msg_id)
                    print(f"Acked message {msg_id}")

        except Exception as e:
            logger.info(f"Error: {e}")
            await asyncio.sleep(1)
