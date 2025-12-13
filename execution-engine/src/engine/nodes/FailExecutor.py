from models.execution_state import RunTimeExecutionState


class FailExecutor:
    def execute(self, execution_state: RunTimeExecutionState, error_message: str, idiot:str="DEVELOPER") -> None:
        execution_state.out_message.text = f"IT IS FAILED BECAUSE {idiot} IS AN IDIOT: {error_message}"
        execution_state.send_message_flag = True
