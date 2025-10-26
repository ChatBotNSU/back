from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class ExitProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Exit"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        exit_message = block.config.message or "Диалог завершен"
        clear_context = block.config.clear_context or False
        exit_reason = block.config.reason or "completed"
        
        # Формируем финальное сообщение
        response_message = exit_message
        
        # Очищаем сессию если нужно
        if clear_context:
            # В реальной реализации здесь будет очистка сессии
            pass
        
        return ProcessingResult(
            response_message=response_message,
            next_block_id=None,  # Exit блок не имеет следующего блока
            outputs={
                "exit_reason": exit_reason,
                "conversation_completed": True
            }
        )