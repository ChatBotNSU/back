"""
Payment integrations: Stripe (Checkout) and YooKassa.

Returns a normalized dict with a ``payment_url`` the bot can send to the user.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

import httpx

_STRIPE = "https://api.stripe.com/v1"
_YOOKASSA = "https://api.yookassa.ru/v3"
_TINKOFF = "https://securepay.tinkoff.ru/v2"


class PaymentError(RuntimeError):
    pass


def _client(client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    if client is not None:
        return client, False
    return httpx.AsyncClient(timeout=20), True


class StripeProvider:
    name = "stripe"

    def __init__(self, secret_key: str, client: httpx.AsyncClient | None = None) -> None:
        if not secret_key:
            raise PaymentError("stripe: secret_key is required")
        self.secret_key = secret_key
        self._client = client

    async def create_payment(
        self, amount: float, currency: str, description: str, success_url: str
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        # Stripe wants amount in the minor unit (cents/kopecks) + form encoding.
        form = {
            "mode": "payment",
            "success_url": success_url or "https://example.com/success",
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(int(float(amount) * 100)),
            "line_items[0][price_data][product_data][name]": description or "Payment",
        }
        try:
            resp = await client.post(
                f"{_STRIPE}/checkout/sessions", data=form,
                headers={"Authorization": f"Bearer {self.secret_key}"},
            )
            data = resp.json()
            return {
                "provider": self.name, "ok": resp.status_code < 400,
                "payment_id": data.get("id", ""), "payment_url": data.get("url", ""),
                "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


class YooKassaProvider:
    name = "yookassa"

    def __init__(self, shop_id: str, secret_key: str, client: httpx.AsyncClient | None = None) -> None:
        if not shop_id or not secret_key:
            raise PaymentError("yookassa: shop_id and secret_key are required")
        self.shop_id = shop_id
        self.secret_key = secret_key
        self._client = client

    async def create_payment(
        self, amount: float, currency: str, description: str, return_url: str
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        body = {
            "amount": {"value": f"{float(amount):.2f}", "currency": currency},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or "https://example.com/return",
            },
            "description": description,
        }
        try:
            resp = await client.post(
                f"{_YOOKASSA}/payments", json=body,
                auth=(self.shop_id, self.secret_key),
                headers={"Idempotence-Key": str(uuid.uuid4())},
            )
            data = resp.json()
            return {
                "provider": self.name, "ok": resp.status_code < 400,
                "payment_id": data.get("id", ""),
                "payment_url": (data.get("confirmation") or {}).get("confirmation_url", ""),
                "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


class TinkoffProvider:
    name = "tinkoff"

    def __init__(self, terminal_key: str, password: str, client: httpx.AsyncClient | None = None) -> None:
        if not terminal_key or not password:
            raise PaymentError("tinkoff: terminal_key and password are required")
        self.terminal_key = terminal_key
        self.password = password
        self._client = client

    def _token(self, params: dict[str, Any]) -> str:
        # Tinkoff signature: root scalar params + Password, sorted by key, values concatenated, sha256.
        signed = {k: v for k, v in params.items() if not isinstance(v, (dict, list))}
        signed["Password"] = self.password
        concat = "".join(str(signed[k]) for k in sorted(signed))
        return hashlib.sha256(concat.encode()).hexdigest()

    async def create_payment(
        self, amount: float, currency: str, description: str, return_url: str
    ) -> dict[str, Any]:
        client, owned = _client(self._client)
        body: dict[str, Any] = {
            "TerminalKey": self.terminal_key,
            "Amount": int(float(amount) * 100),  # kopecks
            "OrderId": str(uuid.uuid4()),
            "Description": description or "Payment",
        }
        body["Token"] = self._token(body)
        try:
            resp = await client.post(f"{_TINKOFF}/Init", json=body)
            data = resp.json()
            return {
                "provider": self.name,
                "ok": bool(data.get("Success")),
                "payment_id": str(data.get("PaymentId", "")),
                "payment_url": data.get("PaymentURL", ""),
                "raw": data,
            }
        finally:
            if owned:
                await client.aclose()


def build_provider(
    name: str, config: dict[str, Any], client: httpx.AsyncClient | None = None
):
    name = (name or "stripe").lower()
    if name == "stripe":
        return StripeProvider(config.get("secret_key", ""), client=client)
    if name == "yookassa":
        return YooKassaProvider(
            config.get("shop_id", ""), config.get("secret_key", ""), client=client
        )
    if name == "tinkoff":
        return TinkoffProvider(
            config.get("terminal_key", ""), config.get("secret_key", ""), client=client
        )
    return None
