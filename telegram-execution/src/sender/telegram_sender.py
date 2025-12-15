import logging
from typing import Dict, Optional
import asyncio
from asyncio import Future

from models.redis_io_streams import ExecutionResponse

logger = logging.getLogger("app")


class TelegramResponseSender:
    _instance: Optional["TelegramResponseSender"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._pending_responses: Dict[int, Future] = {}
        TelegramResponseSender._instance = self
        logger.info("TelegramResponseSender initialized")

    @staticmethod
    def get_instance() -> "TelegramResponseSender":
        if TelegramResponseSender._instance is None:
            raise RuntimeError("PreviewResponseSender not initialized")
        return TelegramResponseSender._instance

    async def add_future(self, execution_id: int) -> asyncio.Future:
        future = asyncio.Future()
        
        async with self._lock:
            self._pending_responses[execution_id] = future
        
        return future

    async def send_response(self, response: ExecutionResponse) -> bool:
        execution_id = response.execution_id
        
        async with self._lock:
            future = self._pending_responses.get(execution_id)
            
        if future and not future.done():
            future.set_result(response.message)
            async with self._lock:
                self._pending_responses.pop(execution_id, None)
            logger.info(f"Response sent for execution_id={execution_id}")
            return True
        else:
            logger.warning(f"No pending request found for execution_id={execution_id}")
            return False