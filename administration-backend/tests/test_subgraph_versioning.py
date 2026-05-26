"""Версионирование сабграфов: history, diff, force, conflict, automerge."""

import copy


def _sub(name="if_part"):
    """Базовый сабграф с одним set_variable + subgraph_exit."""
    return {
        "name": name,
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


def _create(client, payload):
    r = client.post("/api/v1/subgraph/subgraphs", json=payload)
    assert r.status_code == 201, r.text
    return r


def _put(client, name, payload, **kwargs):
    body = {"subgraph": payload, **kwargs}
    return client.put(f"/api/v1/subgraph/subgraph/{name}", json=body)


def test_history_grows_with_each_save(client):
    _create(client, _sub())

    history = client.get("/api/v1/subgraph/subgraph/if_part/history").json()
    assert len(history) == 1

    v2 = _sub()
    v2["graph"]["nodes"]["s1"]["operand"] = 30.0
    _put(client, "if_part", v2, force=True)

    history = client.get("/api/v1/subgraph/subgraph/if_part/history").json()
    assert len(history) == 2
    # newest first
    assert history[0]["id"] > history[1]["id"]
    # parent chain links them
    assert history[0]["parent_id"] == history[1]["id"]


def test_get_returns_latest_version(client):
    _create(client, _sub())

    v2 = _sub()
    v2["graph"]["nodes"]["s1"]["operand"] = 99.0
    _put(client, "if_part", v2, force=True)

    fetched = client.get("/api/v1/subgraph/subgraph/if_part").json()
    assert fetched["graph"]["nodes"]["s1"]["operand"] == 99.0


def test_diff_between_versions(client):
    _create(client, _sub())
    history = client.get("/api/v1/subgraph/subgraph/if_part/history").json()
    v1_id = history[0]["id"]

    # v2: modify s1, add s3
    v2 = _sub()
    v2["graph"]["nodes"]["s1"]["operand"] = 42.0
    v2["graph"]["nodes"]["s3"] = {"type": "subgraph_exit", "exit_label": "big"}
    _put(client, "if_part", v2, force=True)

    history = client.get("/api/v1/subgraph/subgraph/if_part/history").json()
    v2_id = history[0]["id"]

    diff = client.get(f"/api/v1/subgraph/subgraph/if_part/diff?v1={v1_id}&v2={v2_id}").json()
    assert diff["added"] == ["s3"]
    assert diff["deleted"] == []
    assert diff["modified"] == ["s1"]


def test_save_with_base_version_id_no_conflict(client):
    """Юзер открыл v1, ничего не сохранилось параллельно, отдаёт base_version_id=v1 → ok."""
    _create(client, _sub())
    v1_id = client.get("/api/v1/subgraph/subgraph/if_part/history").json()[0]["id"]

    v2 = _sub()
    v2["graph"]["nodes"]["s1"]["operand"] = 7.0

    r = _put(client, "if_part", v2, base_version_id=v1_id)
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/subgraph/subgraph/if_part").json()["graph"]["nodes"]["s1"]["operand"] == 7.0


def test_save_with_stale_base_and_disjoint_changes_automerges(client):
    """User A и user B оба ушли с v1. A сохраняет (s1 -> 50). B сохраняет (s3 added). Конфликта нет — автомерж."""
    _create(client, _sub())
    v1_id = client.get("/api/v1/subgraph/subgraph/if_part/history").json()[0]["id"]

    # User A saves first.
    va = _sub()
    va["graph"]["nodes"]["s1"]["operand"] = 50.0
    r = _put(client, "if_part", va, base_version_id=v1_id)
    assert r.status_code == 200

    # User B still thinks base is v1, but actually latest is va. B touches a different node — adds s3.
    vb = _sub()
    vb["graph"]["nodes"]["s3"] = {"type": "subgraph_exit", "exit_label": "big"}
    r = _put(client, "if_part", vb, base_version_id=v1_id)
    assert r.status_code == 200, r.text

    merged = client.get("/api/v1/subgraph/subgraph/if_part").json()
    assert merged["graph"]["nodes"]["s1"]["operand"] == 50.0   # из versii A
    assert "s3" in merged["graph"]["nodes"]                     # из versii B


def test_save_with_stale_base_and_overlapping_changes_returns_409(client):
    """Оба юзера правят один и тот же узел s1 → конфликт."""
    _create(client, _sub())
    v1_id = client.get("/api/v1/subgraph/subgraph/if_part/history").json()[0]["id"]

    va = _sub()
    va["graph"]["nodes"]["s1"]["operand"] = 50.0
    _put(client, "if_part", va, base_version_id=v1_id)

    vb = _sub()
    vb["graph"]["nodes"]["s1"]["operand"] = 70.0
    r = _put(client, "if_part", vb, base_version_id=v1_id)

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "merge_conflict"
    assert "s1" in detail["conflicting_nodes"]
    assert detail["your_version"]["graph"]["nodes"]["s1"]["operand"] == 70.0
    assert detail["their_version"]["graph"]["nodes"]["s1"]["operand"] == 50.0


def test_conflict_can_be_forced_through(client):
    """После 409 юзер видит обе версии, выбирает свою → отправляет с force=True."""
    _create(client, _sub())
    v1_id = client.get("/api/v1/subgraph/subgraph/if_part/history").json()[0]["id"]

    va = _sub()
    va["graph"]["nodes"]["s1"]["operand"] = 50.0
    _put(client, "if_part", va, base_version_id=v1_id)

    vb = _sub()
    vb["graph"]["nodes"]["s1"]["operand"] = 70.0
    r = _put(client, "if_part", vb, force=True)
    assert r.status_code == 200
    assert client.get("/api/v1/subgraph/subgraph/if_part").json()["graph"]["nodes"]["s1"]["operand"] == 70.0


def test_inputs_change_is_a_metadata_conflict(client):
    """Если оба пользователя поменяли `inputs` относительно base — конфликт."""
    _create(client, _sub())
    v1_id = client.get("/api/v1/subgraph/subgraph/if_part/history").json()[0]["id"]

    va = _sub()
    va["inputs"] = ["y", "extra_a"]
    _put(client, "if_part", va, base_version_id=v1_id)

    vb = _sub()
    vb["inputs"] = ["y", "extra_b"]
    r = _put(client, "if_part", vb, base_version_id=v1_id)
    assert r.status_code == 409
    assert "inputs" in r.json()["detail"]["conflicting_metadata"]
