from ..base import BaseBlockProcessor
from ...models import BotBlock, RedisMessage, ProcessingResult
from typing import Any, Dict

class ChoiceProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Choice"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> ProcessingResult:
        question = block.config.question or ""
        options = block.config.options or []
        
        # Заменяем переменные в вопросе
        question = self._replace_variables(question, context)
        
        # Обрабатываем варианты ответов
        processed_options = []
        for option in options:
            processed_option = option.copy()
            processed_option["label"] = self._replace_variables(option.get("label", ""), context)
            processed_options.append(processed_option)
        
        # Формируем сообщение с вариантами выбора
        response_lines = [question, ""]
        for i, option in enumerate(processed_options, 1):
            response_lines.append(f"{i}. {option['label']}")
        
        response_message = "\n".join(response_lines)
        
        # Сохраняем варианты выбора в контекст для последующей обработки
        context["_current_choices"] = processed_options
        
        return ProcessingResult(
            response_message=response_message,
            next_block_id=None,  # Будет определен после выбора пользователя
            outputs={},
            waiting_for_choice=True,
            choices=processed_options
        )