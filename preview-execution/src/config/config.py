import json
from typing import Literal, Union
import os

from pathlib import Path
from pydantic import BaseModel, ValidationError 

from dotenv import load_dotenv
load_dotenv()

class RedisStreamConfig(BaseModel):
    stream_requests: str
    stream_responses: str
    group: str
    consumer: str

class RedisConfig(BaseModel):
    host: str
    port: int
    IOStream: RedisStreamConfig

class ServerConfig(BaseModel):
    host: str
    port: int

class AppConfig(BaseModel):
    redis: RedisConfig
    server: ServerConfig


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"AppConfig file {path} not found")
    
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    return AppConfig(**data)


_config = None

def get_config(path: Union[str, Path, None] = None) -> AppConfig:
    if path is None:
        here = Path(__file__).resolve().parent
        path = here / "config.json"

    global _config
    if _config is None:
        _config = load_config(path)
    return _config
