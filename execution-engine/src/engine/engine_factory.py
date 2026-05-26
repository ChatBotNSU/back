import logging

from .engine import Engine
from minio_controller.S3Client import S3Client

from models.execution_state import ExecutionState, Frame


logger = logging.getLogger("app")

class EngineFactory:
    '''Singleton class that provides access to created engines and creates new ones when needed'''

    _instance = None
    existing_engines: dict[int, Engine] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EngineFactory, cls).__new__(cls)
        return cls._instance

    def get_engine(self, execution_id: int, chatbot_id: int) -> Engine:
        if execution_id in self.existing_engines:
            return self.existing_engines[execution_id]

        s3client = S3Client.get_instance()

        chatbot = s3client.download_chatbot(chatbot_id)
        root_frame = Frame(
            subgraph_name=None,
            executing_node_id=chatbot.graph.root,
            variable_values={},
        )
        execution = ExecutionState(
            bot_id=chatbot_id,
            execution_id=execution_id,
            call_stack=[root_frame],
        )

        engine = Engine(chatbot, execution)
        self.existing_engines[execution_id] = engine
        logger.info("Engine instatiated")
        return engine
