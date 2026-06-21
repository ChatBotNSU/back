"""Tests for the sliding-window rate limiter + webhook 429 behaviour."""
from __future__ import annotations

import api.webhooks as wh
from api.ratelimit import SlidingWindowRateLimiter


class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


class TestSlidingWindow:
    def test_allows_up_to_limit(self):
        clock = _Clock()
        rl = SlidingWindowRateLimiter(3, 60, clock=clock)
        assert [rl.allow("k") for _ in range(4)] == [True, True, True, False]

    def test_window_slides(self):
        clock = _Clock()
        rl = SlidingWindowRateLimiter(2, 10, clock=clock)
        assert rl.allow("k") and rl.allow("k")
        assert rl.allow("k") is False
        clock.t = 11  # window passed
        assert rl.allow("k") is True

    def test_keys_independent(self):
        rl = SlidingWindowRateLimiter(1, 60, clock=_Clock())
        assert rl.allow("a") is True
        assert rl.allow("b") is True
        assert rl.allow("a") is False

    def test_zero_disables(self):
        rl = SlidingWindowRateLimiter(0, 60, clock=_Clock())
        assert all(rl.allow("k") for _ in range(100))


class TestWebhookRateLimit:
    def test_generic_webhook_429(self, client, monkeypatch):
        # Install a deterministic in-memory limiter (env may have Redis up).
        limiter = SlidingWindowRateLimiter(2, 60)
        monkeypatch.setattr(wh, "_rate_limiter", limiter)
        codes = [
            client.post("/webhook/generic/some-bot", json={"text": "hi"}).status_code
            for _ in range(3)
        ]
        # First two pass rate limit (404 — bot missing), third is limited.
        assert codes[2] == 429
        assert 429 not in codes[:2]
