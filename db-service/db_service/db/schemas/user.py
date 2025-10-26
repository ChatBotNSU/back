from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password_hash: str


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    hashed_password: str

    model_config = {
        "from_attributes": True
    }
