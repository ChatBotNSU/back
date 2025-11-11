from __future__ import annotations
import io, json, os, sys, time, traceback, multiprocessing, resource, builtins, types, ast, socket, ipaddress
from typing import Dict, List, Literal, Optional
from fastapi import FastAPI, Response
from pydantic import BaseModel, Field
import uvicorn

# ==== SCHEMAS ====
Status = Literal["OK","TIMEOUT","OOM","RUNTIME_ERROR","POLICY_VIOLATION","TYPE_ERROR"]

class NetPolicy(BaseModel):
    egress: List[Literal["http","https"]] = ["https"]
    deny_private_ips: bool = True
    allow_ports: List[int] = [80, 443]

class PackagePolicy(BaseModel):
    allow_imports: List[str] = ["requests","httpx","json","re","datetime","math","statistics","itertools","functools"]

class RunRequest(BaseModel):
    job_id: str
    code: str
    variables: Dict[str, str | int]
    schema: Dict[str, Literal["str","int"]]
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
    variables: Optional[Dict[str, str | int]] = None
    added_variables: Dict[str, str | int] = {}
    removed_variables: List[str] = []
    error: Optional[ErrorInfo] = None
    logs: Logs = Field(default_factory=Logs)
    metrics: Metrics

# ==== SANDBOX POLICY ====
import builtins as _py_builtins

SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "len": len, "range": range,
    "enumerate": enumerate, "sum": sum, "print": print, "str": str, "int": int, "float": float,
    "bool": bool, "sorted": sorted, "__import__": _py_builtins.__import__
}

DENY_IMPORTS = {
    "os","sys","subprocess","shlex","socket","pty","selectors","asyncio",
    "multiprocessing","threading","ctypes","ssl","importlib","builtins",
    "pathlib","fcntl","resource","signal","pickle","marshal","tempfile"
}

def ast_policy_check(code: str, allow_imports: List[str]):
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name.split(".")[0] for n in (node.names)]
            bad = [n for n in names if n not in allow_imports]
            if bad:
                raise PermissionError(f"Forbidden import: {', '.join(bad)}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"eval","exec","open","compile","__import__"}:
                raise PermissionError(f"Forbidden call: {node.func.id}")
    return True

# network guard: deny private IPs, ports not allowed
def patch_network(net: NetPolicy):
    orig_create = socket.create_connection

    private_networks = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("169.254.169.254/32"),  # metadata
    ]

    def is_private_ip(ip: str) -> bool:
        try:
            ipaddr = ipaddress.ip_address(ip)
            return any(ipaddr in netw for netw in private_networks)
        except ValueError:
            return True

    def guarded_create_connection(address, timeout=None, source_address=None):
        host, port = address
        if port not in net.allow_ports:
            raise PermissionError(f"Port {port} not allowed")
        # resolve and check all A/AAAA
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        for family, socktype, proto, canonname, sockaddr in infos:
            ip = sockaddr[0]
            if net.deny_private_ips and is_private_ip(ip):
                raise PermissionError(f"Connection to private IP {ip} is blocked")
        return orig_create(address, timeout=timeout, source_address=source_address)

    socket.create_connection = guarded_create_connection  # type: ignore

def enforce_limits(memory_mb: int, cpu_seconds: int):
    bytes_limit = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
    resource.setrlimit(resource.RLIMIT_DATA, (bytes_limit, bytes_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))  # forbid new processes

def worker(payload: dict, conn):
    # apply resource limits
    try:
        enforce_limits(payload.get("memory_mb", 256), payload.get("timeout_seconds", 8))
    except Exception:
        pass

    code: str = payload["code"]
    variables: Dict[str, str | int] = payload["variables"]
    schema: Dict[str, str] = payload["schema"]
    net_policy = NetPolicy(**payload.get("net_policy", {}))
    pkg_policy = PackagePolicy(**payload.get("package_policy", {}))

    # static policy
    try:
        ast_policy_check(code, allow_imports=pkg_policy.allow_imports)
    except Exception as e:
        conn.send(("POLICY_VIOLATION", {"type": type(e).__name__, "message": str(e), "traceback": ""}, "", ""))
        return

    # network guard
    try:
        patch_network(net_policy)
    except Exception as e:
        conn.send(("POLICY_VIOLATION", {"type": type(e).__name__, "message": f"Net guard failed: {e}", "traceback": ""}, "", ""))
        return

    # exec env
    g = {"__builtins__": SAFE_BUILTINS}
    l: dict = {}

    # preload variables (type placeholders)
    for name, t in schema.items():
        if t not in ("int", "str"):
            conn.send(("TYPE_ERROR", {"type": "TypeError", "message": f"Unsupported type {t}", "traceback": ""}, "", ""))
            return
        l[name] = variables.get(name)

    stdout, stderr = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr

    status, err = "OK", None
    try:
        exec(compile(code, "<user_code>", "exec"), g, l)
    except MemoryError as e:
        status = "OOM"; err = {"type": "MemoryError", "message": str(e), "traceback": traceback.format_exc()}
    except Exception as e:
        status = "RUNTIME_ERROR"; err = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    if status == "OK":
        out_vars: Dict[str, str | int] = {}
        added: Dict[str, str | int] = {}
        removed = [k for k in schema.keys() if k not in l]
        try:
            for name, t in schema.items():
                val = l.get(name)
                if t == "int" and not isinstance(val, int): raise TypeError(f"{name} expected int, got {type(val).__name__}")
                if t == "str" and not isinstance(val, str): raise TypeError(f"{name} expected str, got {type(val).__name__}")
                out_vars[name] = val
            # persist new str|int variables if user created them
            for name, val in l.items():
                if name not in schema and isinstance(val, (int, str)):
                    added[name] = val
            conn.send((status, err, stdout.getvalue(), stderr.getvalue(), out_vars, added, removed))
        except Exception as e:
            conn.send(("TYPE_ERROR", {"type": "TypeError", "message": str(e), "traceback": traceback.format_exc()}, stdout.getvalue(), stderr.getvalue()))
    else:
        conn.send((status, err, stdout.getvalue(), stderr.getvalue()))

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/run")
def run(req: RunRequest, resp: Response) -> dict:
    parent, child = multiprocessing.Pipe(False)
    p = multiprocessing.Process(target=worker, args=(req.model_dump(), child))
    start = time.time()
    p.start()
    p.join(req.timeout_seconds)
    wall_ms = int((time.time() - start) * 1000)

    body = {
        "job_id": req.job_id,
        "metrics": {"wall_ms": wall_ms}
    }

    if p.is_alive():
        p.terminate(); p.join()
        body.update({
            "status": "TIMEOUT",
            "error": {"type": "TimeoutError", "message": "Execution exceeded timeout", "traceback": ""},
            "logs": {"stdout": "", "stderr": ""}
        })
    else:
        msg = parent.recv()
        if len(msg) == 7:
            status, err, out, errout, out_vars, added, removed = msg
            body.update({
                "status": status,
                "variables": out_vars if status=="OK" else req.variables,
                "added_variables": added if status=="OK" else {},
                "removed_variables": removed if status=="OK" else [],
                "error": err,
                "logs": {"stdout": out, "stderr": errout}
            })
        else:
            status, err, out, errout = msg
            body.update({
                "status": status,
                "error": err,
                "logs": {"stdout": out, "stderr": errout}
            })
    return body

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
