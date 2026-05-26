"""E2E tests for the /api/v1/chatbot endpoints, including embedding subgraphs."""


def _make_chatbot_payload(*, with_subgraph: bool = False):
    if with_subgraph:
        return {
            "bot_name": "demo",
            "graph": {
                "root": "n_seed",
                "nodes": {
                    "n_seed": {
                        "type": "set_variable",
                        "assigned_variable": "y",
                        "operation": "=",
                        "operand": 3.0,
                        "next_node_id": "n_call",
                    },
                    "n_call": {
                        "type": "subgraph_call",
                        "subgraph_name": "if_part",
                        "input_bindings": {"y": "y"},
                        "exit_next_nodes": {"small": "n_msg", "big": "n_msg"},
                    },
                    "n_msg": {
                        "type": "set_message",
                        "text": "y={y}",
                        "audios": [],
                        "images": [],
                        "files": [],
                        "choise_options": [],
                        "next_node_id": "n_send",
                    },
                    "n_send": {"type": "send_message", "next_node_id": "n_call"},
                },
            },
            "subgraphs": {
                "if_part": {
                    "name": "if_part",
                    "inputs": ["y"],
                    "exits": ["small", "big"],
                    "graph": {
                        "root": "s_set",
                        "nodes": {
                            "s_set": {
                                "type": "set_variable",
                                "assigned_variable": "y",
                                "operation": "=",
                                "operand": 20.0,
                                "next_node_id": "s_exit",
                            },
                            "s_exit": {"type": "subgraph_exit", "exit_label": "small"},
                        },
                    },
                }
            },
        }
    return {
        "bot_name": "simple",
        "graph": {
            "root": "n_send",
            "nodes": {"n_send": {"type": "send_message", "next_node_id": "n_send"}},
        },
    }


def test_create_chatbot_and_fetch(client, s3):
    payload = _make_chatbot_payload(with_subgraph=False)
    r = client.post("/api/v1/chatbot/chatbots", json=payload)
    assert r.status_code == 200, r.text
    created = r.json()
    bot_id = created["bot_id"]
    assert bot_id >= 100  # from the fake db service

    r = client.get(f"/api/v1/chatbot/chatbot/{bot_id}")
    assert r.status_code == 200, r.text
    assert r.json()["bot_id"] == bot_id
    assert r.json()["bot_name"] == "simple"


def test_create_chatbot_with_embedded_subgraph(client):
    payload = _make_chatbot_payload(with_subgraph=True)
    r = client.post("/api/v1/chatbot/chatbots", json=payload)
    assert r.status_code == 200, r.text
    bot_id = r.json()["bot_id"]

    fetched = client.get(f"/api/v1/chatbot/chatbot/{bot_id}").json()
    assert "if_part" in fetched["subgraphs"]
    assert fetched["subgraphs"]["if_part"]["inputs"] == ["y"]
    assert fetched["graph"]["nodes"]["n_call"]["type"] == "subgraph_call"
    assert fetched["graph"]["nodes"]["n_call"]["input_bindings"] == {"y": "y"}


def test_chatbot_round_trip_after_update(client):
    initial = _make_chatbot_payload(with_subgraph=False)
    bot_id = client.post("/api/v1/chatbot/chatbots", json=initial).json()["bot_id"]

    # Update now wraps the chatbot in a SaveChatbotRequest envelope (versioning).
    # `force=True` skips conflict detection — fine here, we're not testing merges.
    updated = _make_chatbot_payload(with_subgraph=True)
    r = client.post(
        f"/api/v1/chatbot/chatbot/{bot_id}",
        json={"chatbot": updated, "force": True},
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/api/v1/chatbot/chatbot/{bot_id}").json()
    assert "if_part" in fetched["subgraphs"]


def test_chatbot_with_invalid_subgraph_call_node_rejected(client):
    payload = _make_chatbot_payload(with_subgraph=True)
    # Strip required field input_bindings to ensure validation catches the malformed node.
    del payload["graph"]["nodes"]["n_call"]["input_bindings"]
    r = client.post("/api/v1/chatbot/chatbots", json=payload)
    assert r.status_code == 422


def test_compose_chatbot_from_subgraph_library(client):
    """Realistic flow: user creates a subgraph in their library, then composes a chatbot
    that references it inline (the editor would copy the subgraph JSON into the bot)."""
    sub_payload = {
        "name": "if_part",
        "inputs": ["y"],
        "exits": ["small", "big"],
        "graph": {
            "root": "s_set",
            "nodes": {
                "s_set": {
                    "type": "set_variable",
                    "assigned_variable": "y",
                    "operation": "=",
                    "operand": 99.0,
                    "next_node_id": "s_exit",
                },
                "s_exit": {"type": "subgraph_exit", "exit_label": "small"},
            },
        },
    }
    assert client.post("/api/v1/subgraph/subgraphs", json=sub_payload).status_code == 201
    sub = client.get("/api/v1/subgraph/subgraph/if_part").json()

    bot_payload = _make_chatbot_payload(with_subgraph=True)
    bot_payload["subgraphs"]["if_part"] = sub  # caller embeds the library copy as-is
    r = client.post("/api/v1/chatbot/chatbots", json=bot_payload)
    assert r.status_code == 200, r.text
    bot_id = r.json()["bot_id"]

    fetched = client.get(f"/api/v1/chatbot/chatbot/{bot_id}").json()
    # The version that the engine will execute uses the snapshot from the chatbot,
    # so the operand should be 99.0 (from the library) — even if the user later
    # edits the library, this chatbot keeps its snapshot.
    assert fetched["subgraphs"]["if_part"]["graph"]["nodes"]["s_set"]["operand"] == 99.0
