from __future__ import annotations
import os
import uuid
from typing import Dict, Optional
import httpx

from .schemas import RunRequest, RunResponse

DEFAULT_URL = os.getenv("PY_RUNNER_URL", "http://py-runner:8080/run")

class PyRunnerClient:
    def __init__(self, base_url: str | None = None, timeout: float = 15.0):
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.timeout = timeout

    def run(
        self,
        code: str,
        variables: Dict[str, str | int],
        schema: Dict[str, str],
        *,
        job_id: Optional[str] = None,
        timeout_seconds: int = 8,
        memory_mb: int = 256,
        allow_imports: Optional[list[str]] = None,
    ) -> RunResponse:
        req = RunRequest(
            job_id=job_id or str(uuid.uuid4()),
            code=code,
            variables=variables,
            schema=schema,
            timeout_seconds=timeout_seconds,
            memory_mb=memory_mb,
        )
        if allow_imports:
            req.package_policy.allow_imports = allow_imports

        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/run" if self.base_url.endswith("/run") is False else self.base_url, json=req.model_dump())
            r.raise_for_status()
            return RunResponse.model_validate(r.json())
