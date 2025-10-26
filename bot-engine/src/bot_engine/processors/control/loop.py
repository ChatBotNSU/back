from ..base import BaseBlockProcessor
from typing import Any, Dict, List
from ...models import BotBlock, RedisMessage, ProcessingResult

class LoopProcessor(BaseBlockProcessor):
    def get_block_type(self) -> str:
        return "Loop"
    
    def process(self, block: BotBlock, message: RedisMessage, context: Dict[str, Any]) -> Dict[str, Any]:
        loop_type = block.config.get("type", "foreach")
        
        # Инициализация или продолжение цикла
        loop_state = context.setdefault("_loop_state", {})
        current_loop = loop_state.get(block.id, {})
        
        if not current_loop:
            # Начало цикла
            current_loop = self._initialize_loop(block, context)
            loop_state[block.id] = current_loop
        
        if current_loop.get("completed", False):
            # Цикл завершен
            next_block_id = self.get_next_block_id(block, context)
            # Очищаем состояние цикла
            loop_state.pop(block.id, None)
            
            return {
                "response_message": None,
                "next_block_id": next_block_id,
                "outputs": current_loop.get("final_outputs", {})
            }
        else:
            # Следующая итерация
            iteration_result = self._process_iteration(block, current_loop, context)
            return {
                "response_message": None,
                "next_block_id": block.config.get("childBlocks", [""])[0],  # Первый дочерний блок
                "outputs": iteration_result,
                "in_loop": True,
                "loop_iteration": current_loop["current_iteration"]
            }
    
    def _initialize_loop(self, block: BotBlock, context: Dict[str, Any]) -> Dict[str, Any]:
        """Инициализирует состояние цикла"""
        loop_type = block.config.get("type", "foreach")
        
        if loop_type == "foreach":
            items = context.get(block.config.get("items", "").strip("{{}}"), [])
            return {
                "type": "foreach",
                "items": items,
                "current_index": 0,
                "current_iteration": 0,
                "completed": len(items) == 0,
                "item_variable": block.config.get("itemVariable", "current_item")
            }
        elif loop_type == "while":
            condition = block.config.get("condition", "true")
            max_iterations = block.config.get("maxIterations", 100)
            return {
                "type": "while",
                "condition": condition,
                "current_iteration": 0,
                "max_iterations": max_iterations,
                "completed": False
            }
        else:
            return {"completed": True}
    
    def _process_iteration(self, block: BotBlock, loop_state: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Обрабатывает одну итерацию цикла"""
        outputs = {}
        
        if loop_state["type"] == "foreach":
            items = loop_state["items"]
            current_index = loop_state["current_index"]
            
            if current_index < len(items):
                # Устанавливаем текущий элемент
                item_var = loop_state["item_variable"]
                outputs[item_var] = items[current_index]
                outputs["loop_index"] = current_index
                
                # Подготавливаем следующую итерацию
                loop_state["current_index"] += 1
                loop_state["current_iteration"] += 1
            else:
                loop_state["completed"] = True
                outputs = loop_state.get("final_outputs", {})
                
        elif loop_state["type"] == "while":
            current_iteration = loop_state["current_iteration"]
            max_iterations = loop_state["max_iterations"]
            condition = loop_state["condition"]
            
            if (current_iteration < max_iterations and 
                self._evaluate_condition(condition, context)):
                
                outputs["loop_index"] = current_iteration
                loop_state["current_iteration"] += 1
            else:
                loop_state["completed"] = True
                
        return outputs