from pydantic import BaseModel
from datetime import datetime

class GraphBase(BaseModel):
    name: str
    s3_path: str | None = None

class GraphCreate(GraphBase):
    pass

class GraphRead(GraphBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True