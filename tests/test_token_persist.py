"""AmoCRM refreshed token is persisted back to its secret by the CRM handler."""
from __future__ import annotations

import httpx

from engine.registry import get, load_all_handlers
from models.node import Node, NodeType
from models.session import Session

load_all_handlers()


class TestAmoTokenPersist:
    async def test_refreshed_token_saved_to_secret(self, secret_store):
        await secret_store.put("default", "amo", {
            "base_url": "https://acme.amocrm.ru", "token": "old",
            "refresh": {"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        })

        state = {"calls": 0}

        def handler(req):
            if req.url.path.endswith("/oauth2/access_token"):
                return httpx.Response(200, json={"access_token": "newtok"})
            state["calls"] += 1
            if state["calls"] == 1:
                return httpx.Response(401, json={})
            return httpx.Response(200, json={"_embedded": {"contacts": [{"id": 1}]}})

        crm = get(NodeType.CRM)
        out = await crm.execute(
            config={"provider": "amocrm", "action": "find", "entity": "contact",
                    "secret_ref": "amo", "fields": {"query": "x"},
                    "__client__": httpx.AsyncClient(transport=httpx.MockTransport(handler))},
            data_in={}, session=Session(flow_id="f"),
            node=Node(id="c", type=NodeType.CRM),
        )
        assert out["ok"] is True
        # The refreshed token must be written back, and not leak in the node output.
        assert "refreshed_token" not in out
        bundle = await secret_store.get_value("default", "amo")
        assert bundle["token"] == "newtok"
