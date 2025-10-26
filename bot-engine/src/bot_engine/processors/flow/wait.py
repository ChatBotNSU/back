import time
from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class WaitProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Wait"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        duration = block.config.duration or 1000  # milliseconds
        wait_message = block.config.message or "Ожидайте..."
        
        # Конвертируем в секунды и ждем
        time.sleep(duration / 1000.0)
        
        next_block_id = self.get_next_block_id(block, context)
        
        return ProcessingResult(
            response_message=wait_message,
            next_block_id=next_block_id,
            outputs={}
        )