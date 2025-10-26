from .base import BaseBlockProcessor
from .dialogue.prompt import PromptProcessor
from .dialogue.choice import ChoiceProcessor
from .control.condition import ConditionProcessor
from .control.loop import LoopProcessor
from .control.switch import SwitchProcessor
from .data.set_var import SetVarProcessor
from .data.answer import AnswerProcessor
from .flow.subflow import SubflowProcessor
from .flow.exit import ExitProcessor
from .flow.start import StartProcessor
from .flow.command import CommandProcessor
from .flow.wait import WaitProcessor
from .script.script import ScriptProcessor

class ProcessorFactory:
    _processors = None
    
    @classmethod
    def get_processors(cls) -> dict:
        if cls._processors is None:
            cls._processors = {
                processor().get_block_type(): processor()
                for processor in [
                    PromptProcessor,
                    ChoiceProcessor,
                    ConditionProcessor,
                    LoopProcessor,
                    SwitchProcessor,
                    SetVarProcessor,
                    AnswerProcessor,
                    SubflowProcessor,
                    ExitProcessor,
                    StartProcessor,
                    CommandProcessor,
                    WaitProcessor,
                    ScriptProcessor
                ]
            }
        return cls._processors
    
    @classmethod
    def get_processor(cls, block_type: str) -> BaseBlockProcessor:
        processors = cls.get_processors()
        return processors.get(block_type)
    
    @classmethod
    def get_available_block_types(cls) -> list:
        processors = cls.get_processors()
        return list(processors.keys())