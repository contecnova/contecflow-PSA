from app.services.service_desk.workflow_designer_service import validate_graph


def test_validate_graph_accepts_minimal_valid_graph():
    graph = {
        "nodes": [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "end"},
        ],
        "edges": [{"source": "n1", "target": "n2", "type": "default"}],
    }
    out = validate_graph(graph)
    assert out["valid"] is True
    assert out["errors"] == []


def test_validate_graph_rejects_without_start():
    graph = {
        "nodes": [{"id": "n2", "type": "end"}],
        "edges": [],
    }
    out = validate_graph(graph)
    assert out["valid"] is False
    assert any("start" in err for err in out["errors"])


def test_validate_graph_detects_unreachable_nodes():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "a", "type": "state"},
            {"id": "b", "type": "state"},  # No alcanzable
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "a"},
            {"source": "a", "target": "e"},
        ],
    }
    out = validate_graph(graph)
    assert out["valid"] is True  # ok estructura, warning de alcanzabilidad
    assert any("inalcanzables" in w for w in out["warnings"])


def test_validate_graph_detects_unknown_node_types():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "x", "type": "unknown_type_xyz"},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "x"},
            {"source": "x", "target": "e"},
        ],
    }
    out = validate_graph(graph)
    assert out["valid"] is False
    assert any("desconocido" in err for err in out["errors"])


def test_validate_graph_detects_duplicate_ids():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "x", "type": "state"},
            {"id": "x", "type": "state"},  # duplicado
            {"id": "e", "type": "end"},
        ],
        "edges": [{"source": "s", "target": "e"}],
    }
    out = validate_graph(graph)
    assert out["valid"] is False
    assert any("duplicado" in err for err in out["errors"])


def test_validate_graph_warns_on_missing_decision_branch():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "d", "type": "decision"},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "d"},
            {"source": "d", "target": "e", "branch": "true"},
            # falta branch 'false'
        ],
    }
    out = validate_graph(graph)
    assert out["valid"] is True
    assert any("'false'" in w for w in out["warnings"])


def test_builtin_templates_are_all_valid():
    from app.services.service_desk.workflow_designer_service import builtin_templates
    for tpl in builtin_templates():
        out = validate_graph(tpl["graph"])
        assert out["valid"], f"Template {tpl['id']} no válido: {out['errors']}"


def test_workflow_designer_endpoints_smoke(client, admin_token):
    """Smoke test HTTP de los endpoints principales."""
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/sd/workflow-designer/schema", headers=h)
    assert r.status_code == 200
    assert "node_types" in r.json()["data"] and len(r.json()["data"]["node_types"]) > 0

    r = client.get("/api/v1/sd/workflow-designer/templates", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list) and len(r.json()["items"]) >= 1

    r = client.post(
        "/api/v1/sd/workflow-designer/validate",
        headers=h,
        json={
            "nodes": [{"id": "s", "type": "start"}, {"id": "e", "type": "end"}],
            "edges": [{"source": "s", "target": "e"}],
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["valid"] is True


# ── Engine ────────────────────────────────────────────────────────────────────
def _publish_blueprint(client, headers, name, graph, process_type="ticket"):
    r = client.post("/api/v1/sd/workflow-designer/blueprints", headers=headers,
                    json={"name": name, "process_type": process_type, "graph": graph})
    assert r.status_code == 200, r.text
    bp = r.json()["data"]
    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/publish/1", headers=headers)
    assert r.status_code == 200, r.text
    return bp


def test_engine_runs_simple_blueprint_to_end(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "e", "type": "end"},
        ],
        "edges": [{"source": "s", "target": "e"}],
    }
    bp = _publish_blueprint(client, h, "simple", graph)

    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h, json={"context": {}})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["run"]["status"] == "completed"
    assert body["run"]["current_node_id"] is None
    # debe haber al menos 2 steps (start, end)
    types = [s["node_type"] for s in body["steps"]]
    assert "start" in types and "end" in types


def test_engine_decision_branches_by_context(client, admin_token):
    """La decisión bifurca según `priority` en el contexto."""
    h = {"Authorization": f"Bearer {admin_token}"}
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "d", "type": "decision", "data": {"config": {"expression": "priority == 'P1'"}}},
            {"id": "fast", "type": "state", "data": {"config": {"status": "fast"}}},
            {"id": "slow", "type": "state", "data": {"config": {"status": "slow"}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "d", "branch": "next"},
            {"source": "d", "target": "fast", "branch": "true"},
            {"source": "d", "target": "slow", "branch": "false"},
            {"source": "fast", "target": "e", "branch": "next"},
            {"source": "slow", "target": "e", "branch": "next"},
        ],
    }
    bp = _publish_blueprint(client, h, "decision", graph)

    # Con P1 → ruta fast
    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h,
                    json={"context": {"priority": "P1"}})
    assert r.status_code == 200
    types = [s["node_id"] for s in r.json()["data"]["steps"]]
    assert "fast" in types and "slow" not in types

    # Sin P1 → ruta slow
    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h,
                    json={"context": {"priority": "P3"}})
    types = [s["node_id"] for s in r.json()["data"]["steps"]]
    assert "slow" in types and "fast" not in types


def test_engine_approval_pauses_and_resumes(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "ap", "type": "approval", "data": {"config": {"approver_role": "manager"}}},
            {"id": "ok", "type": "state", "data": {"config": {"status": "approved"}}},
            {"id": "ko", "type": "state", "data": {"config": {"status": "rejected"}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "ap", "branch": "next"},
            {"source": "ap", "target": "ok", "branch": "approved"},
            {"source": "ap", "target": "ko", "branch": "rejected"},
            {"source": "ok", "target": "e", "branch": "next"},
            {"source": "ko", "target": "e", "branch": "next"},
        ],
    }
    bp = _publish_blueprint(client, h, "approval", graph)

    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h, json={"context": {}})
    body = r.json()["data"]
    assert body["run"]["status"] == "waiting"
    assert body["run"]["current_node_id"] == "ap"

    # Aprobar
    run_id = body["run"]["id"]
    r = client.post(f"/api/v1/sd/workflow-designer/runs/{run_id}/resume", headers=h,
                    json={"branch": "approved"})
    assert r.status_code == 200
    body2 = r.json()["data"]
    assert body2["run"]["status"] == "completed"
    assert any(s["node_id"] == "ok" for s in body2["steps"])
    assert not any(s["node_id"] == "ko" for s in body2["steps"])


def test_engine_run_listing_and_cancel(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "ap", "type": "approval"},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"source": "s", "target": "ap", "branch": "next"},
            {"source": "ap", "target": "e", "branch": "approved"},
        ],
    }
    bp = _publish_blueprint(client, h, "list-cancel", graph)
    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h, json={})
    run_id = r.json()["data"]["run"]["id"]

    r = client.get("/api/v1/sd/workflow-designer/runs", headers=h)
    assert r.status_code == 200
    assert any(x["id"] == run_id for x in r.json()["items"])

    r = client.post(f"/api/v1/sd/workflow-designer/runs/{run_id}/cancel", headers=h, json={"reason": "test"})
    assert r.status_code == 200
    assert r.json()["data"]["run"]["status"] == "cancelled"


def test_engine_rejects_unpublished_blueprint(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    graph = {
        "nodes": [{"id": "s", "type": "start"}, {"id": "e", "type": "end"}],
        "edges": [{"source": "s", "target": "e"}],
    }
    r = client.post("/api/v1/sd/workflow-designer/blueprints", headers=h,
                    json={"name": "draft-only", "process_type": "ticket", "graph": graph})
    bp = r.json()["data"]
    # NO lo publicamos
    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/runs", headers=h, json={})
    assert r.status_code == 400
    assert "publicada" in r.json()["detail"]


def test_engine_expression_evaluator_unit():
    from app.services.service_desk.workflow_engine import evaluate_expression
    assert evaluate_expression("priority == 'P1'", {"priority": "P1"}) is True
    assert evaluate_expression("priority == 'P1'", {"priority": "P3"}) is False
    assert evaluate_expression("amount > 1000", {"amount": 5000}) is True
    assert evaluate_expression("amount > 1000", {"amount": 100}) is False
    assert evaluate_expression("risk in ('high','critical')", {"risk": "high"}) is True
    assert evaluate_expression("risk in ('high','critical')", {"risk": "low"}) is False
    assert evaluate_expression("title startswith 'urgent'", {"title": "urgent: server down"}) is True
