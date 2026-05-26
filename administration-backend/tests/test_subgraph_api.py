"""E2E tests for the /api/v1/subgraph CRUD endpoints."""


SAMPLE_SUBGRAPH = {
    "name": "if_part",
    "inputs": ["y"],
    "exits": ["small", "big"],
    "graph": {
        "root": "s1",
        "nodes": {
            "s1": {
                "type": "set_variable",
                "assigned_variable": "y",
                "operation": "=",
                "operand": 20.0,
                "next_node_id": "s2",
            },
            "s2": {"type": "subgraph_exit", "exit_label": "small"},
        },
    },
}


def test_create_and_get_subgraph(client):
    r = client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "if_part"
    assert body["inputs"] == ["y"]
    assert body["exits"] == ["small", "big"]

    r = client.get("/api/v1/subgraph/subgraph/if_part")
    assert r.status_code == 200
    fetched = r.json()
    assert fetched["name"] == "if_part"
    assert fetched["graph"]["root"] == "s1"
    assert fetched["graph"]["nodes"]["s2"]["type"] == "subgraph_exit"


def test_create_conflict(client):
    r = client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    assert r.status_code == 201
    r2 = client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    assert r2.status_code == 409


def test_list_subgraphs(client):
    assert client.get("/api/v1/subgraph/subgraphs").json() == []
    client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    second = {**SAMPLE_SUBGRAPH, "name": "other"}
    client.post("/api/v1/subgraph/subgraphs", json=second)

    listed = client.get("/api/v1/subgraph/subgraphs").json()
    assert sorted(listed) == ["if_part", "other"]


def test_update_subgraph(client):
    client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    updated = {**SAMPLE_SUBGRAPH, "exits": ["small", "big", "extra"]}
    r = client.put("/api/v1/subgraph/subgraph/if_part", json=updated)
    assert r.status_code == 200, r.text
    assert r.json()["exits"] == ["small", "big", "extra"]

    r = client.get("/api/v1/subgraph/subgraph/if_part")
    assert r.json()["exits"] == ["small", "big", "extra"]


def test_update_name_mismatch(client):
    client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    wrong = {**SAMPLE_SUBGRAPH, "name": "other_name"}
    r = client.put("/api/v1/subgraph/subgraph/if_part", json=wrong)
    assert r.status_code == 400


def test_delete_subgraph(client):
    client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)
    r = client.delete("/api/v1/subgraph/subgraph/if_part")
    assert r.status_code == 200

    assert client.get("/api/v1/subgraph/subgraph/if_part").status_code == 404
    assert client.get("/api/v1/subgraph/subgraphs").json() == []


def test_missing_subgraph_returns_404(client):
    assert client.get("/api/v1/subgraph/subgraph/nope").status_code == 404
    assert client.put("/api/v1/subgraph/subgraph/nope", json={**SAMPLE_SUBGRAPH, "name": "nope"}).status_code == 404
    assert client.delete("/api/v1/subgraph/subgraph/nope").status_code == 404


def test_subgraphs_are_isolated_per_user(client, app_and_user, s3):
    """A subgraph owned by user A must not appear for user B."""
    from api.middleware import get_current_active_user
    from entities.User import User

    app, user_a, _ = app_and_user
    client.post("/api/v1/subgraph/subgraphs", json=SAMPLE_SUBGRAPH)

    user_b = User(id=999, name="Other", email="other@example.com", hashed_password="x")
    app.dependency_overrides[get_current_active_user] = lambda: user_b

    # User B sees an empty library and can't fetch user A's subgraph.
    assert client.get("/api/v1/subgraph/subgraphs").json() == []
    assert client.get("/api/v1/subgraph/subgraph/if_part").status_code == 404

    # Switch back: user A still sees their subgraph.
    app.dependency_overrides[get_current_active_user] = lambda: user_a
    assert client.get("/api/v1/subgraph/subgraphs").json() == ["if_part"]


def test_subgraph_with_invalid_node_type_is_rejected(client):
    bad = {**SAMPLE_SUBGRAPH, "graph": {"root": "x", "nodes": {"x": {"type": "nonsense"}}}}
    r = client.post("/api/v1/subgraph/subgraphs", json=bad)
    assert r.status_code == 422
