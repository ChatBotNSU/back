from typing import Dict, Literal, Optional, List
from pydantic import BaseModel, Field

Status = Literal[
    "OK", "TIMEOUT", "OOM", "RUNTIME_ERROR", "POLICY_VIOLATION", "TYPE_ERROR"
]

class NetPolicy(BaseModel):
    egress: List[Literal["http", "https"]] = ["https"]
    deny_private_ips: bool = True
    allow_ports: List[int] = [80, 443]

class PackagePolicy(BaseModel):
    allow_imports: List[str] = ["requests", "httpx", "json", "re", "datetime", "math"]

class RunRequest(BaseModel):
    job_id: str
    code: str
    variables: Dict[str, str | int]
    schema: Dict[str, Literal["str", "int"]]
    timeout_seconds: int = 8
    memory_mb: int = 256
    net_policy: NetPolicy = Field(default_factory=NetPolicy)
    package_policy: PackagePolicy = Field(default_factory=PackagePolicy)

class ErrorInfo(BaseModel):
    type: str
    message: str
    traceback: str = ""

class Logs(BaseModel):
    stdout: str = ""
    stderr: str = ""

class Metrics(BaseModel):
    wall_ms: int
    cpu_sec: Optional[float] = None
    max_rss_mb: Optional[int] = None

class RunResponse(BaseModel):
    job_id: str
    status: Status
    variables: Dict[str, str | int] | None = None
    added_variables: Dict[str, str | int] = {}
    removed_variables: List[str] = []
    error: Optional[ErrorInfo] = None
    logs: Logs = Field(default_factory=Logs)
    metrics: Metrics
