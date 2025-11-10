from minio import Minio
from typing import Optional
import threading

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

    # ----------------------
    # Методы для execution
    # ----------------------
    def upload_execution(self, execution_id: int, data: bytes):
        obj_name = f"execution-{execution_id}"
        self.client.put_object(self.bucket, obj_name, data, length=len(data))

    def download_execution(self, execution_id: int) -> bytes:
        obj_name = f"execution-{execution_id}"
        response = self.client.get_object(self.bucket, obj_name)
        return response.read()

    # ----------------------
    # Методы для chatbot
    # ----------------------
    def upload_chatbot(self, chatbot_id: int, data: bytes):
        obj_name = f"chatbot-{chatbot_id}"
        self.client.put_object(self.bucket, obj_name, data, length=len(data))

    def download_chatbot(self, chatbot_id: int) -> bytes:
        obj_name = f"chatbot-{chatbot_id}"
        response = self.client.get_object(self.bucket, obj_name)
        return response.read()
