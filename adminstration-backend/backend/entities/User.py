from typing import Optional

from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    email: str
    hashed_password: str

class UserHashedPassword(BaseModel):
    hashed_password: str
