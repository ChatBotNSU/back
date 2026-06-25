from __future__ import annotations

import asyncio
import math
import multiprocessing
import time
from typing import Any

from config import settings
from engine import sandbox
from engine.registry import register
from models.node import Node, NodeType
from models.session import Session

try:  # POSIX-only resource limits
    import resource  # type: ignore
    _HAS_RESOURCE = True
except ImportError:  # pragma: no cover - non-POSIX
    _HAS_RESOURCE = False

# Fork lets us hand the worker live objects without pickling and apply rlimits
# in the child before running untrusted code. Falls back to in-thread exec when
# unavailable (e.g. Windows / spawn-only platforms).
try:
    _MP_CTX: multiprocessing.context.BaseContext | None = multiprocessing.get_context("fork")
except ValueError:  # pragma: no cover - no fork available
    _MP_CTX = None

_DEFAULT_MEMORY_MB = 256

_SANDBOX_GLOBALS = {
    "__builtins__": {
        "len": len,
        "range": range,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "print": print,
        "isinstance": isinstance,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "sorted": sorted,
        "min": min,
        "max": max,
        "sum": sum,
        "abs": abs,
        "round": round,
    }
}


def _sandbox_worker(
    conn: Any,
    source: str,
    local_vars: dict[str, Any],
    mem_bytes: int,
    cpu_seconds: int,
) -> None:
    """Runs in the forked child: apply rlimits, exec, ship the result back."""
    try:
        if _HAS_RESOURCE:
            if cpu_seconds > 0:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            if mem_bytes > 0:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        globals_copy = dict(_SANDBOX_GLOBALS)
        lv = dict(local_vars)
        lv.setdefault("__result__", None)
        exec(source + "\n", globals_copy, lv)
        conn.send(("ok", lv.get("__result__")))
    except MemoryError:
        conn.send(("error", "Memory limit exceeded"))
    except BaseException as exc:  # noqa: BLE001 — report everything to parent
        conn.send(("error", str(exc) or type(exc).__name__))
    finally:
        conn.close()


class CodeHandler:
    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        source: str = config.get("source", "")
        input_vars: list[str] = config.get("input_vars", [])
        timeout_ms: int = int(config.get("timeout_ms", 5000))
        memory_mb: int = int(config.get("memory_mb", _DEFAULT_MEMORY_MB))

        ctx = {**session.variables, **data_in}
        local_vars = {k: ctx.get(k) for k in input_vars}
        mode = config.get("sandbox") or settings.code_sandbox_mode
        if mode == "docker" or (mode == "auto" and sandbox.docker_available()):
            return await sandbox.run_python_docker(
                source, local_vars,
                image=settings.code_docker_image,
                memory_mb=memory_mb,
                cpus=settings.code_cpus,
                pids_limit=settings.code_pids_limit,
                timeout_ms=timeout_ms,
            )
        return await self._run_python(
            source, input_vars, data_in, session, timeout_ms, memory_mb
        )

    async def _run_python(
        self,
        source: str,
        input_vars: list[str],
        data_in: dict[str, Any],
        session: Session,
        timeout_ms: int,
        memory_mb: int,
    ) -> dict[str, Any]:
        ctx = {**session.variables, **data_in}
        local_vars: dict[str, Any] = {k: ctx.get(k) for k in input_vars}

        if _MP_CTX is not None:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._run_in_subprocess,
                source,
                local_vars,
                timeout_ms,
                memory_mb,
            )
        # Fallback: in-thread exec with wall-clock timeout only (no rlimits).
        return await self._run_in_thread(source, local_vars, timeout_ms)

    def _run_in_subprocess(
        self,
        source: str,
        local_vars: dict[str, Any],
        timeout_ms: int,
        memory_mb: int,
    ) -> dict[str, Any]:
        assert _MP_CTX is not None
        timeout_s = timeout_ms / 1000
        cpu_seconds = max(1, math.ceil(timeout_s) + 1)  # CPU backstop
        mem_bytes = memory_mb * 1024 * 1024 if memory_mb > 0 else 0

        parent_conn, child_conn = _MP_CTX.Pipe(duplex=False)
        proc = _MP_CTX.Process(
            target=_sandbox_worker,
            args=(child_conn, source, local_vars, mem_bytes, cpu_seconds),
        )
        start = time.monotonic()
        proc.start()
        child_conn.close()  # parent only reads

        try:
            if parent_conn.poll(timeout_s):
                try:
                    status, value = parent_conn.recv()
                except EOFError:
                    return self._err(
                        "Sandbox process terminated (resource limit exceeded)", start
                    )
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                if status == "ok":
                    return {"result": value, "error": None, "duration_ms": duration_ms}
                return {"result": None, "error": value, "duration_ms": duration_ms}
            # Wall-clock timeout: kill the process.
            self._kill(proc)
            return {"result": None, "error": "Timeout", "duration_ms": timeout_ms}
        finally:
            self._kill(proc)
            parent_conn.close()

    @staticmethod
    def _kill(proc: Any) -> None:
        if proc.is_alive():
            proc.terminate()
            proc.join(1)
        if proc.is_alive():  # pragma: no cover - stubborn process
            proc.kill()
            proc.join(1)

    @staticmethod
    def _err(msg: str, start: float) -> dict[str, Any]:
        return {
            "result": None,
            "error": msg,
            "duration_ms": round((time.monotonic() - start) * 1000, 2),
        }

    async def _run_in_thread(
        self, source: str, local_vars: dict[str, Any], timeout_ms: int
    ) -> dict[str, Any]:
        local_vars = dict(local_vars)
        local_vars.setdefault("__result__", None)
        globals_copy = dict(_SANDBOX_GLOBALS)
        start = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, exec, source + "\n", globals_copy, local_vars),
                timeout=timeout_ms / 1000,
            )
            return {
                "result": local_vars.get("__result__"),
                "error": None,
                "duration_ms": round((time.monotonic() - start) * 1000, 2),
            }
        except asyncio.TimeoutError:
            return {"result": None, "error": "Timeout", "duration_ms": timeout_ms}
        except Exception as exc:
            return self._err(str(exc), start)


register(NodeType.CODE, CodeHandler())
