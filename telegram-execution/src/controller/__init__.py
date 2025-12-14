import asyncio
from .redis_streams import RedisStreamsController

RedisStreamsController()

asyncio.create_task(RedisStreamsController.get_instance().poll_responses())