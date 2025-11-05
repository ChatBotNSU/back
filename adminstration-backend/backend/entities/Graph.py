from pydantic import BaseModel
from datetime import datetime

class Graph(BaseModel):
    id: int
    name: str
    s3_path: str | None = None
    created_at: datetime
    updated_at: datetime