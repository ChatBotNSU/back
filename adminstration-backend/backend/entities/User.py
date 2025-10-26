from typing import Optional

from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    email: str
    hashed_password: str
    refresh_token: str
    disabled: bool = True

class UserHashedPassword(BaseModel):
    hashed_password: str
