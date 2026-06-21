"""Tests for metrics endpoint, request-id middleware, and JSON logging."""
from __future__ import annotations

import logging

import pytest

from services import metrics
from services.logging_config import JsonFormatter, request_id_var
from models.flow import Flow
from models.node import Node, NodeType, ExecOut
from stores.bot_store import BotConfig

_FLOW = Flow(id="obs-flow", start_node="n1", nodes={
    "n1": Node(id="n1", type=NodeType.SEND_MESSAGE, config={"text": "hi"}, exec_out=ExecOut(fallback="n2")),
    "n2": Node(id="n2", type=NodeType.END),
})


class TestMetricsEndpoint:
    def test_metrics_exposed(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    async def test_flow_run_increments_metrics(self, client, flow_store, bot_store):
        await flow_store.save(_FLOW)
        await bot_store.save(BotConfig(id="obs-bot", name="b", flow_id="obs-flow", channel="generic"))
        client.post("/webhook/generic/obs-bot", json={"user_id": "u", "text": "hi"})

        body = client.get("/metrics").text
        if metrics.enabled():
            assert "node_executions_total" in body
            assert "webhook_requests_total" in body


class TestRequestId:
    def test_generated_header(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Request-ID")

    def test_echoes_provided_id(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "abc123"})
        assert resp.headers["X-Request-ID"] == "abc123"


class TestJsonFormatter:
    def test_emits_json_with_request_id(self):
        token = request_id_var.set("rid-9")
        try:
            rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
            rec.request_id = request_id_var.get("")
            line = JsonFormatter().format(rec)
        finally:
            request_id_var.reset(token)
        import json
        parsed = json.loads(line)
        assert parsed["message"] == "hello"
        assert parsed["request_id"] == "rid-9"
        assert parsed["level"] == "INFO"


class TestRecorders:
    def test_record_helpers_no_crash(self):
        metrics.record_node("send_message", 0.01)
        metrics.record_flow("done")
        metrics.record_webhook("telegram")
        body, ct = metrics.render()
        assert isinstance(body, bytes)
