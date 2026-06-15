from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.registry import register
from integrations.payment import PaymentError, build_provider
from models.node import Node, NodeType
from models.session import Session
from services import connections

logger = logging.getLogger(__name__)


class PaymentHandler:
    """Stripe / YooKassa with stub fallback when no provider creds are set."""

    async def execute(
        self,
        config: dict[str, Any],
        data_in: dict[str, Any],
        session: Session,
        node: Node,
    ) -> dict[str, Any]:
        config = await connections.resolve(config, session)
        ctx = {**session.variables, **data_in}
        provider: str = config.get("provider", "stripe")
        amount: Any = ctx.get(config.get("amount_var", "amount"), config.get("amount", 0))
        currency: str = config.get("currency", "RUB")
        description: str = config.get("description", "")
        redirect_url: str = config.get("return_url") or config.get("success_url") or ""

        # No credentials configured → keep the flow runnable with a stub link.
        if "secret_key" not in config:
            return self._stub(provider)

        client = config.get("__client__")
        try:
            impl = build_provider(provider, config, client=client)
        except PaymentError as exc:
            return {"provider": provider, "ok": False, "error": str(exc)}

        if impl is None:
            return self._stub(provider)

        try:
            result = await impl.create_payment(amount, currency, description, redirect_url)
            result.setdefault("expires_at", _expiry())
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Payment via %s failed: %s", provider, exc)
            return {"provider": provider, "ok": False, "error": str(exc)}

    @staticmethod
    def _stub(provider: str) -> dict[str, Any]:
        return {
            "provider": provider, "ok": True,
            "payment_url": f"https://{provider}.example.com/pay/stub-id",
            "payment_id": "stub-payment-id", "expires_at": _expiry(), "stub": True,
        }


def _expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()


register(NodeType.PAYMENT, PaymentHandler())
