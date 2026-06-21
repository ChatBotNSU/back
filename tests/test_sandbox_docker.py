"""Tests for Docker-isolated sandbox command building + handler mode selection."""
from __future__ import annotations

import pytest

import engine.sandbox as sandbox
from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


async def _run(config):
    h = get(NodeType.CODE)
    return await h.execute(
        config=config, data_in={},
        session=Session(flow_id="t"), node=Node(id="c", type=NodeType.CODE),
    )


class TestBuildDockerCommand:
    def test_lockdown_flags_present(self):
        cmd = sandbox.build_docker_command(image="python:3.12-slim", memory_mb=128, cpus=0.5, pids_limit=32)
        joined = " ".join(cmd)
        assert "--network none" in joined
        assert "--read-only" in joined
        assert "--cap-drop ALL" in joined
        assert "--security-opt no-new-privileges" in joined
        assert "--memory 128m" in joined
        assert "--pids-limit 32" in joined
        assert "--user 65534:65534" in joined
        assert cmd[0] == "docker" and "python:3.12-slim" in cmd

    def test_no_docker(self, monkeypatch):
        monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
        assert sandbox.docker_available() is False


class TestHandlerModeSelection:
    async def test_docker_mode_calls_docker(self, monkeypatch):
        called = {}

        async def fake_docker(source, local_vars, **kw):
            called["yes"] = True
            return {"result": "from-docker", "error": None, "duration_ms": 1}

        monkeypatch.setattr(sandbox, "run_python_docker", fake_docker)
        out = await _run({"language": "python", "source": "__result__ = 1", "sandbox": "docker"})
        assert called.get("yes") is True
        assert out["result"] == "from-docker"

    async def test_process_mode_does_not_call_docker(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("docker must not be used in process mode")

        monkeypatch.setattr(sandbox, "run_python_docker", boom)
        monkeypatch.setattr(sandbox, "docker_available", lambda: True)
        out = await _run({
            "language": "python", "source": "__result__ = 2 + 2",
            "input_vars": [], "sandbox": "process",
        })
        assert out["result"] == 4

    async def test_auto_falls_back_to_process_without_docker(self, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_available", lambda: False)
        out = await _run({"language": "python", "source": "__result__ = 7", "sandbox": "auto"})
        assert out["result"] == 7


@pytest.mark.skipif(not sandbox.docker_available(), reason="docker not installed")
class TestDockerIntegration:
    """Real container runs — only on hosts with Docker."""

    async def test_runs_code(self):
        out = await sandbox.run_python_docker(
            "import math\n__result__ = math.factorial(5)", {}, timeout_ms=60000
        )
        assert out["error"] is None
        assert out["result"] == 120

    async def test_network_is_blocked(self):
        out = await sandbox.run_python_docker(
            "import urllib.request\n"
            "__result__ = urllib.request.urlopen('http://example.com', timeout=3).status",
            {}, timeout_ms=60000,
        )
        assert out["result"] is None
        assert out["error"] is not None  # name resolution / network unreachable

    async def test_exception_captured(self):
        out = await sandbox.run_python_docker("__result__ = 1/0", {}, timeout_ms=60000)
        assert out["result"] is None
        assert "division by zero" in out["error"]


class TestReadyProbe:
    def test_ready_reports_checks(self, client):
        # In tests there's no real Postgres/Redis backing app.state → not ready.
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "checks" in body
        assert set(body["checks"]) == {"postgres", "redis"}
