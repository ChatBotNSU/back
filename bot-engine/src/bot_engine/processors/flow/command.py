from ..base import BaseBlockProcessor
from typing import Any, Dict
from ...models import BotBlock, RedisMessage, ProcessingResult

class CommandProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Command"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        command = block.config.command or ""
        keywords = block.config.keywords or []
        description = block.config.description or ""
        
        user_message = message.message.strip()
        
        # Проверяем, соответствует ли сообщение команде или ключевым словам
        is_command_match = (
            user_message == command or
            any(user_message.lower() == keyword.lower() for keyword in keywords) or
            any(keyword.lower() in user_message.lower() for keyword in keywords if len(keyword) > 3)
        )
        
        if is_command_match:
            # Команда распознана - передаем управление следующему блоку
            next_block_id = self.get_next_block_id(block, context)
            
            return ProcessingResult(
                response_message=None,
                next_block_id=next_block_id,
                outputs={
                    "command_matched": True,
                    "matched_command": command,
                    "user_message": user_message
                }
            )
        else:
            # Команда не распознана - не делаем ничего
            return ProcessingResult(
                response_message=None,
                next_block_id=None,
                outputs={
                    "command_matched": False
                }
            )