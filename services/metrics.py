"""
Prometheus metrics. Degrades to no-ops if prometheus_client is unavailable, so
importing this never breaks the engine/tests.
"""
from __future__ import annotations

from typing import Any

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
    _ENABLED = True
except ImportError:  # pragma: no cover
    _ENABLED = False
    CONTENT_TYPE_LATEST = "text/plain"

if _ENABLED:
    _flow_runs = Counter("flow_runs_total", "Flow runs by final state", ["state"])
    _node_execs = Counter("node_executions_total", "Node executions by type", ["type"])
    _node_seconds = Histogram("node_execution_seconds", "Node execution duration", ["type"])
    _webhooks = Counter("webhook_requests_total", "Inbound webhook requests", ["channel"])


def record_node(node_type: str, seconds: float) -> None:
    if _ENABLED:
        _node_execs.labels(node_type).inc()
        _node_seconds.labels(node_type).observe(seconds)


def record_flow(state: str) -> None:
    if _ENABLED:
        _flow_runs.labels(state).inc()


def record_webhook(channel: str) -> None:
    if _ENABLED:
        _webhooks.labels(channel).inc()


def render() -> tuple[bytes, str]:
    if not _ENABLED:
        return b"", CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


def enabled() -> bool:
    return _ENABLED
