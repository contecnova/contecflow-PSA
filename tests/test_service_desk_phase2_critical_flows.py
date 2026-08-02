from tests.conftest import auth


def test_workflow_designer_create_and_publish(client, admin_token, db):
    graph = {
        "nodes": [
            {"id": "start-1", "type": "start", "config": {"trigger": "ticket_created"}},
            {"id": "act-1", "type": "action", "config": {"action": "set_priority"}},
            {"id": "end-1", "type": "end", "config": {"final_status": "approved"}},
        ],
        "edges": [
            {"source": "start-1", "target": "act-1", "type": "default"},
            {"source": "act-1", "target": "end-1", "type": "default"},
        ],
    }

    create = client.post(
        "/api/v1/sd/workflow-designer/blueprints",
        headers=auth(admin_token),
        json={
            "name": "Ticket triage v1",
            "process_type": "ticket",
            "graph": graph,
        },
    )
    assert create.status_code in (200, 201), create.text
    bp = create.json()["data"]

    publish = client.post(
        f"/api/v1/sd/workflow-designer/blueprints/{bp['id']}/publish/1",
        headers=auth(admin_token),
    )
    assert publish.status_code == 200
    assert publish.json()["data"]["published_version"] == 1


def test_kb_versioning_and_rollback(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/kb",
        headers=auth(admin_token),
        json={
            "title": "Reset VPN",
            "body": "Paso 1",
            "summary": "VPN reset",
            "status": "draft",
        },
    )
    assert created.status_code in (200, 201), created.text
    article_id = created.json()["data"]["id"]

    patch = client.patch(
        f"/api/v1/sd/kb/{article_id}",
        headers=auth(admin_token),
        json={"body": "Paso 1\nPaso 2", "status": "published"},
    )
    assert patch.status_code == 200

    versions = client.get(f"/api/v1/sd/kb/{article_id}/versions", headers=auth(admin_token))
    assert versions.status_code == 200
    assert len(versions.json()["items"]) >= 2

    rollback = client.post(f"/api/v1/sd/kb/{article_id}/rollback/1", headers=auth(admin_token))
    assert rollback.status_code == 200
    assert rollback.json()["data"]["rolled_back_to"] == 1


def test_queue_prioritized_endpoint(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "SLA urgent",
            "description": "Need quick response",
            "priority": "p1_critical",
            "ticket_type": "incident",
            "assigned_to_user_id": "admin-test-id",
        },
    )
    assert created.status_code in (200, 201)

    res = client.get("/api/v1/sd/tickets/my-queue/prioritized", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)


def test_connectors_marketplace_and_governance_ops(client, admin_token, db):
    market = client.get("/api/v1/sd/connectors/marketplace", headers=auth(admin_token))
    assert market.status_code == 200

    eval_run = client.post(
        "/api/v1/sd/governance/ai/evaluations",
        headers=auth(admin_token),
        json={
            "model_name": "triage-model-v2",
            "task_type": "triage",
            "dataset_name": "offline_eval_2026w17",
            "score": "0.88",
            "metrics": {"precision": 0.89, "recall": 0.86},
        },
    )
    assert eval_run.status_code in (200, 201), eval_run.text

    drift = client.post(
        "/api/v1/sd/governance/ai/drift",
        headers=auth(admin_token),
        json={
            "model_name": "triage-model-v2",
            "feature_set": "ticket_embeddings",
            "drift_score": 45,
            "details": {"psi": 0.31},
        },
    )
    assert drift.status_code in (200, 201), drift.text

    quality = client.get("/api/v1/sd/governance/quality-contract", headers=auth(admin_token))
    assert quality.status_code == 200
