import json
from typing import Literal, Union
import os

from pathlib import Path
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()

class ServerConfig(BaseModel):
    host: str
    port: int

class DatabaseServiceConfig(BaseModel):
    host: str
    port: int

class AuthenticationConfig(BaseModel):
    secret_key: str
    algorithm: Literal["HS256", "HS384", "HS512"]
    access_token_expiration_minutes: int

class S3Config(BaseModel):
    host: str
    port: int
    user: str
    password: str

class AppConfig(BaseModel):
    server: ServerConfig
    db_service: DatabaseServiceConfig
    authentication: AuthenticationConfig
    s3: S3Config


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
    except ValidationError as e:
        print("Ошибка валидации конфига:")
        print(e.json())
        raise
    

    try:
        data["authentication"]["secret_key"] = os.getenv("AUTH_SECRET_KEY")
        if data is None:
            raise ValidationError("Please setup SECRET_KEY in .env file")

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
