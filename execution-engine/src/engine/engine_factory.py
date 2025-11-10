from .engine import Engine

# Already created engines. Maybe move to redis
existing_engines : dict[int, Engine] = {}

class EngineFactory:
    # Already created engines. Maybe move to redis
    existing_engines : dict[int, Engine] = {}   

    def get_engine(self, execution_id: int) -> Engine:
        if execution_id in existing_engines:
            return existing_engines[execution_id] 

        # TODO: instatiate engine
        

