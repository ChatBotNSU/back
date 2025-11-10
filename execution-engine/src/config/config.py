import json
from typing import Literal, Union
import os

from pathlib import Path
from pydantic import BaseModel, ValidationError 

from dotenv import load_dotenv
load_dotenv()

class DatabaseServiceConfig(BaseModel):
    host: str
    port: int

class RedisStreamConfig(BaseModel):
    stream_requests: str
    stream_responses: str
    group: str
    consumer: str

class RedisConfig(BaseModel):
    host: str
    port: int
    IOStream: RedisStreamConfig

class S3Config(BaseModel):
    host: str
    port: int
    user: str
    password: str

class AppConfig(BaseModel):
    redis: RedisConfig
    s3: S3Config
    #db_service: DatabaseServiceConfig


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"AppConfig file {path} not found")
    
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    try:
        data["s3"]["user"] = os.getenv("MINIO_ROOT_USER")
        data["s3"]["password"] = os.getenv("MINIO_ROOT_PASSWORD")
        if data["s3"]["user"] is None or data["s3"]["password"] is None:
            raise ValidationError("Please setup MINIO_ROOT_USER and MINIO_ROOT_PASSWORD in .env file")
        cfg = AppConfig(**data)
    except ValidationError as e:
        print("Ошибка валидации конфига:")
        print(e.json())
        raise
    
    return cfg


_config = None

def get_config(path: Union[str, Path, None] = None) -> AppConfig:
    if path is None:
        here = Path(__file__).resolve().parent
        path = here / "config.json"

    global _config
    if _config is None:
        _config = load_config(path)
    return _config
