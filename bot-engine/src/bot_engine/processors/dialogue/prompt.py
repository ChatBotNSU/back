from ..base import BaseBlockProcessor
from ...models import BotBlock, RedisMessage, ProcessingResult
from typing import Any, Dict

class PromptProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Prompt"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        # Обращаемся к атрибутам модели, а не используем .get()
        response_message = block.config.message or ""
        
        # Заменяем переменные в сообщении
        response_message = self._replace_variables(response_message, context)
        
        # Обрабатываем quick replies если есть
        quick_replies = block.config.quick_replies or []
        processed_quick_replies = [
            self._replace_variables(reply, context) 
            for reply in quick_replies
        ]
        
        return ProcessingResult(
            response_message=response_message,
            next_block_id=self.get_next_block_id(block, context),
            outputs={},
            quick_replies=processed_quick_replies if processed_quick_replies else None
        )