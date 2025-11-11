from .engine import Engine

class EngineFactory:
    # Already created engines. Maybe move to redis
    existing_engines : dict[int, Engine] = {}   

    def get_engine(self, execution_id: int, chatbot_id: int) -> Engine:
        if execution_id in self.existing_engines:
            return self.existing_engines[execution_id] 

        # TODO: instatiate engine
        

