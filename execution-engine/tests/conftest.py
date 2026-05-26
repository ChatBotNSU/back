"""Minimal pytest setup for execution-engine: make backend modules importable.

We deliberately do NOT spin up Redis or MinIO for these tests. Each test drives
`Engine.execute` directly against an in-memory Chatbot.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# Insert src/ on sys.path so bare imports ('from models...', 'from engine...') work.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# Stub out sandbox_runner so ScriptNodeExecutor can be imported without the
# real py-runner service. ScriptExecution nodes aren't exercised by these tests.
if "sandbox_runner" not in sys.modules:
    pkg = types.ModuleType("sandbox_runner")
    client_mod = types.ModuleType("sandbox_runner.client")

    class _PyRunnerClientStub:  # pragma: no cover - never invoked
        def run(self, *args, **kwargs):  # noqa: D401
            raise RuntimeError("sandbox_runner is stubbed in tests")

    client_mod.PyRunnerClient = _PyRunnerClientStub
    sys.modules["sandbox_runner"] = pkg
    sys.modules["sandbox_runner.client"] = client_mod
