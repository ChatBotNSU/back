# Хз, это написала гптшка. Вроде все должно правильно работать
# Общий принцип. Не лезть в __init__ и get_instance. Они нужны, чтобы правильно работал синглтон
# Изначально S3Client инится в main.py, потом на нем просто вызывается get_instance и больше ничего трогать не надо
# Методы download_execution и download_chatbot на момент написания этого текста нигде не используются. 
# Скорее всего, есть смысл переделать их на работу не с байтами, а на работу объектами Chatbot и Execution, чтобы полностью изолировать этот кусок 
import io

from minio import Minio
from typing import Optional, List
import threading

from models import Chatbot, ExecutionState
from models.chatbot import Subgraph


class S3Client:
    _instance: Optional["S3Client"] = None
    _lock = threading.Lock()

    _instance = None

    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
        self.bucket = "chatbot-bucket"
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        S3Client._instance = self
        print("S3Client initialized")

    @staticmethod
    def get_instance() -> "S3Client":
        if S3Client._instance is None:
            raise RuntimeError("S3Client not initialized yet. Expected call of constructor beforehand.")
        return S3Client._instance


    def upload(self, obj_name: str, data: bytes):
        data_stream = io.BytesIO(data)

        self.client.put_object(
            self.bucket,
            obj_name,
            data_stream,
            length=len(data),
            content_type="application/json",
        )

    def download(self, obj_name: str) -> bytes:
        response = self.client.get_object(self.bucket, obj_name)
        return response.read()
    

    def upload_chatbot(self, chatbot_id: int, chatbot: Chatbot):
        obj_name = f"chatbot-{chatbot_id}.json"
        data = chatbot.model_dump_json().encode("utf-8")
        self.upload(obj_name, data)

    def download_chatbot(self, chatbot_id: int) -> Chatbot:
        obj_name = f"chatbot-{chatbot_id}.json"
        data = self.download(obj_name)
        return Chatbot.model_validate_json(data)

    def upload_chatbot_by_key(self, s3_key: str, chatbot: Chatbot):
        data = chatbot.model_dump_json().encode("utf-8")
        self.upload(s3_key, data)

    def download_chatbot_by_key(self, s3_key: str) -> Chatbot:
        data = self.download(s3_key)
        return Chatbot.model_validate_json(data)


    def upload_execution(self, execution_id: int, execution_state: ExecutionState):
        obj_name = f"execution-{execution_id}.json"
        data = execution_state.model_dump_json().encode("utf-8")
        self.upload(obj_name, data)

    def download_execution(self, execution_id: int) -> ExecutionState:
        obj_name = f"execution-{execution_id}.json"
        data = self.download(obj_name)
        return ExecutionState.model_validate_json(data)

    # --- Subgraphs: user-scoped JSON files in S3. No DB row.
    # Key format: subgraph-{user_id}-{name}.json

    @staticmethod
    def _subgraph_key(user_id: int, name: str) -> str:
        return f"subgraph-{user_id}-{name}.json"

    def upload_subgraph(self, user_id: int, subgraph: Subgraph):
        obj_name = self._subgraph_key(user_id, subgraph.name)
        data = subgraph.model_dump_json().encode("utf-8")
        self.upload(obj_name, data)

    def download_subgraph(self, user_id: int, name: str) -> Subgraph:
        obj_name = self._subgraph_key(user_id, name)
        data = self.download(obj_name)
        return Subgraph.model_validate_json(data)

    def delete_subgraph(self, user_id: int, name: str) -> None:
        obj_name = self._subgraph_key(user_id, name)
        self.client.remove_object(self.bucket, obj_name)

    def list_subgraph_names(self, user_id: int) -> List[str]:
        prefix = f"subgraph-{user_id}-"
        suffix = ".json"
        result: List[str] = []
        for obj in self.client.list_objects(self.bucket, prefix=prefix, recursive=True):
            key = obj.object_name
            if key and key.startswith(prefix) and key.endswith(suffix):
                result.append(key[len(prefix):-len(suffix)])
        return result

    def subgraph_exists(self, user_id: int, name: str) -> bool:
        obj_name = self._subgraph_key(user_id, name)
        try:
            self.client.stat_object(self.bucket, obj_name)
            return True
        except Exception:
            return False
