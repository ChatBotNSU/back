from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional, Union

class RedisMessage(BaseModel):
    """Модель входящего сообщения из Redis"""
    message: str
    bot_id: str = Field(..., alias='botId')
    block_id: str = Field(..., alias='blockId')
    user_id: Optional[str] = Field(None, alias='userId')
    session_id: Optional[str] = Field(None, alias='sessionId')

    # Новая конфигурация Pydantic v2
    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore'
    )

class NextBlock(BaseModel):
    """Модель связи между блоками"""
    source_handle: str = Field(..., alias='sourceHandle')
    target_block_id: str = Field(..., alias='targetBlockId')
    condition: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True
    )

class BlockConfig(BaseModel):
    """Конфигурация блока (динамическая, зависит от типа блока)"""
    # Общие поля для многих блоков
    message: Optional[str] = None
    question: Optional[str] = None
    variable: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    expression: Optional[str] = None
    condition: Optional[str] = None
    type: Optional[str] = None  # для Loop блока
    items: Optional[str] = None  # для Loop блока
    item_variable: Optional[str] = Field(None, alias='itemVariable')
    max_iterations: Optional[int] = Field(None, alias='maxIterations')
    
    # Специфичные поля
    options: Optional[List[Dict[str, Any]]] = None
    quick_replies: Optional[List[str]] = Field(None, alias='quickReplies')
    validation: Optional[Dict[str, Any]] = None
    flow_id: Optional[str] = Field(None, alias='flowId')
    inputs: Optional[Dict[str, str]] = None
    duration: Optional[int] = None
    language: Optional[str] = None
    code: Optional[str] = None
    environment: Optional[Dict[str, Any]] = None
    
    # Новые поля для добавленных блоков
    command: Optional[str] = None
    keywords: Optional[List[str]] = None
    description: Optional[str] = None
    cases: Optional[List[Dict[str, Any]]] = None
    default_case: Optional[Dict[str, Any]] = Field(None, alias='defaultCase')
    clear_context: Optional[bool] = Field(None, alias='clearContext')
    reason: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore'  # Игнорировать лишние поля
    )

class BotBlock(BaseModel):
    """Модель блока сценария"""
    id: str
    type: str
    config: BlockConfig
    next_blocks: List[NextBlock] = Field(default_factory=list, alias='nextBlocks')
    outputs: Dict[str, str] = Field(default_factory=dict)
    child_blocks: Optional[List[str]] = Field(None, alias='childBlocks')
    position: Optional[Dict[str, float]] = None

    model_config = ConfigDict(
        populate_by_name=True
    )

class BotScenario(BaseModel):
    """Модель полного сценария бота"""
    id: str
    name: str
    description: Optional[str] = None
    start_block_id: str = Field(..., alias='startBlockId')
    blocks: Dict[str, BotBlock]
    variables: Dict[str, Any] = Field(default_factory=dict)
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(
        populate_by_name=True
    )

class ProcessingResult(BaseModel):
    """Результат обработки блока"""
    response_message: Optional[str] = None
    next_block_id: Optional[str] = Field(None, alias='nextBlockId')
    outputs: Dict[str, Any] = Field(default_factory=dict)
    waiting_for_input: bool = Field(False, alias='waitingForInput')
    expected_variable: Optional[str] = Field(None, alias='expectedVariable')
    in_loop: bool = Field(False, alias='inLoop')
    loop_iteration: Optional[int] = Field(None, alias='loopIteration')
    condition_evaluated: Optional[bool] = Field(None, alias='conditionEvaluated')
    quick_replies: Optional[List[str]] = Field(None, alias='quickReplies')
    choices: Optional[List[Dict[str, Any]]] = None
    exit_flow: bool = Field(False, alias='exitFlow')
    clear_context: bool = Field(False, alias='clearContext')

    model_config = ConfigDict(
        populate_by_name=True
    )

class UserSession(BaseModel):
    """Модель сессии пользователя"""
    user_id: str = Field(..., alias='userId')
    session_id: str = Field(..., alias='sessionId')
    variables: Dict[str, Any] = Field(default_factory=dict)
    current_block: Optional[str] = Field(None, alias='currentBlock')
    waiting_for_input: bool = Field(False, alias='waitingForInput')
    expected_variable: Optional[str] = Field(None, alias='expectedVariable')
    loop_state: Dict[str, Any] = Field(default_factory=dict, alias='loopState')
    created_at: float = Field(..., alias='createdAt')
    updated_at: float = Field(..., alias='updatedAt')

    model_config = ConfigDict(
        populate_by_name=True
    )

class BotResponse(BaseModel):
    """Модель ответа бота"""
    bot_id: str = Field(..., alias='botId')
    user_id: Optional[str] = Field(None, alias='userId')
    session_id: Optional[str] = Field(None, alias='sessionId')
    response: Optional[str] = None
    next_block_id: Optional[str] = Field(None, alias='nextBlockId')
    outputs: Dict[str, Any] = Field(default_factory=dict)
    quick_replies: Optional[List[str]] = Field(None, alias='quickReplies')
    error: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True
    )