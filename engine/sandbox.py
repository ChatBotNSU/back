"""
Docker-isolated execution for the `code` node.

The process sandbox (fork + RLIMIT) caps CPU/memory but is NOT a security
boundary — restricted ``__builtins__`` can be escaped. For untrusted code we run
it in an ephemeral, locked-down container: no network, read-only root fs,
dropped capabilities, non-root user, memory/pids/cpu limits.

Inside the container full builtins are allowed — the container itself is the
boundary, so user code may ``import`` freely without being able to harm the host.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from typing import Any

DEFAULT_IMAGE = "python:3.12-slim"

# Reads {"source", "locals"} from stdin, execs, prints one JSON line to stdout.
_RUNNER = (
    "import sys, json\n"
    "d = json.loads(sys.stdin.read())\n"
    "lv = dict(d.get('locals') or {})\n"
    "lv.setdefault('__result__', None)\n"
    "try:\n"
    "    exec(d['source'] + '\\n', {}, lv)\n"
    "    print(json.dumps({'ok': True, 'result': lv.get('__result__')}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'ok': False, 'error': str(e) or type(e).__name__}))\n"
)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def build_docker_command(
    *,
    image: str = DEFAULT_IMAGE,
    memory_mb: int = 256,
    cpus: float = 1.0,
    pids_limit: int = 64,
) -> list[str]:
    """Assemble the locked-down `docker run` argv (pure → unit-testable)."""
    return [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:size=16m",
        "--memory", f"{memory_mb}m",
        "--memory-swap", f"{memory_mb}m",
        "--cpus", str(cpus),
        "--pids-limit", str(pids_limit),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",  # nobody
        image,
        "python", "-I", "-c", _RUNNER,
    ]


async def run_python_docker(
    source: str,
    local_vars: dict[str, Any],
    *,
    image: str = DEFAULT_IMAGE,
    memory_mb: int = 256,
    cpus: float = 1.0,
    pids_limit: int = 64,
    timeout_ms: int = 5000,
) -> dict[str, Any]:
    cmd = build_docker_command(
        image=image, memory_mb=memory_mb, cpus=cpus, pids_limit=pids_limit
    )
    payload = json.dumps({"source": source, "locals": local_vars}).encode()

    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout_ms / 1000
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"result": None, "error": "Timeout", "duration_ms": timeout_ms}

    duration_ms = round((time.monotonic() - start) * 1000, 2)
    if proc.returncode != 0 and not out:
        msg = err.decode(errors="replace").strip() or "Sandbox container failed"
        return {"result": None, "error": msg, "duration_ms": duration_ms}

    line = out.decode(errors="replace").strip().splitlines()[-1] if out.strip() else ""
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return {"result": None, "error": "Bad sandbox output", "duration_ms": duration_ms}

    if parsed.get("ok"):
        return {"result": parsed.get("result"), "error": None, "duration_ms": duration_ms}
    return {"result": None, "error": parsed.get("error", "error"), "duration_ms": duration_ms}
