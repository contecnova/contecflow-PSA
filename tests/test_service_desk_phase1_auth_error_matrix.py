from tests.conftest import auth


def _valid_graph():
    return {
        "nodes": [
            {"id": "start_1", "type": "start"},
            {"id": "end_1", "type": "end"},
        ],
        "edges": [
            {"source": "start_1", "target": "end_1"},
        ],
    }


def test_workflow_validate_requires_manager_role(client, dev_token):
    r = client.post("/api/v1/sd/workflow-designer/validate", headers=auth(dev_token), json=_valid_graph())
    assert r.status_code == 403


def test_workflow_blueprint_create_invalid_process_type_returns_422(client, admin_token):
    r = client.post(
        "/api/v1/sd/workflow-designer/blueprints",
        headers=auth(admin_token),
        json={
            "name": "WF invalid type",
            "process_type": "incident",
            "graph": _valid_graph(),
        },
    )
    assert r.status_code == 422


def test_workflow_blueprint_create_invalid_graph_returns_400(client, admin_token):
    r = client.post(
        "/api/v1/sd/workflow-designer/blueprints",
        headers=auth(admin_token),
        json={
            "name": "WF invalid graph",
            "process_type": "ticket",
            "graph": {"nodes": [{"id": "start_1", "type": "start"}], "edges": []},
        },
    )
    assert r.status_code == 400


def test_workflow_blueprint_detail_nonexistent_returns_404(client, admin_token):
    r = client.get("/api/v1/sd/workflow-designer/blueprints/not-found-id", headers=auth(admin_token))
    assert r.status_code == 404


def test_workflow_publish_nonexistent_version_returns_404(client, admin_token):
    created = client.post(
        "/api/v1/sd/workflow-designer/blueprints",
        headers=auth(admin_token),
        json={"name": "WF publish missing", "process_type": "ticket", "graph": _valid_graph()},
    )
    assert created.status_code == 200
    bp_id = created.json()["id"]

    r = client.post(f"/api/v1/sd/workflow-designer/blueprints/{bp_id}/publish/999", headers=auth(admin_token))
    assert r.status_code == 404


def test_cmdb_topology_invalid_radius_returns_422(client, admin_token):
    r = client.get("/api/v1/sd/cmdb/some-ci/topology?radius=0", headers=auth(admin_token))
    assert r.status_code == 422


def test_cmdb_topology_nonexistent_ci_returns_404(client, admin_token):
    r = client.get("/api/v1/sd/cmdb/non-existent-ci/topology?radius=2", headers=auth(admin_token))
    assert r.status_code == 404


def test_cmdb_discovery_list_forbidden_for_employee(client, dev_token):
    r = client.get("/api/v1/sd/cmdb/discovery/providers", headers=auth(dev_token))
    assert r.status_code == 403


def test_cmdb_discovery_create_invalid_payload_returns_422(client, admin_token):
    r = client.post(
        "/api/v1/sd/cmdb/discovery/providers",
        headers=auth(admin_token),
        json={"name": "AWS discovery"},
    )
    assert r.status_code == 422


def test_cmdb_discovery_patch_nonexistent_provider_returns_ok_false(client, admin_token):
    r = client.patch(
        "/api/v1/sd/cmdb/discovery/providers/not-found-provider",
        headers=auth(admin_token),
        json={"name": "x"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is False
    assert data.get("error") == "Provider not found"


def test_governance_drift_invalid_type_returns_422(client, admin_token):
    r = client.post(
        "/api/v1/sd/governance/ai/drift",
        headers=auth(admin_token),
        json={"model_name": "m1", "feature_set": "f1", "drift_score": "high"},
    )
    assert r.status_code == 422


def test_governance_quality_contract_forbidden_for_employee(client, dev_token):
    r = client.put(
        "/api/v1/sd/governance/quality-contract",
        headers=auth(dev_token),
        json={"minimum_tests_pass_rate": 0.99},
    )
    assert r.status_code == 403


def test_governance_evaluations_limit_invalid_returns_422(client, admin_token):
    r = client.get("/api/v1/sd/governance/ai/evaluations?limit=0", headers=auth(admin_token))
    assert r.status_code == 422


def test_marketplace_installed_forbidden_for_employee(client, dev_token):
    r = client.get("/api/v1/sd/connectors/installed", headers=auth(dev_token))
    assert r.status_code == 403


def test_marketplace_install_nonexistent_connector_returns_404(client, admin_token):
    r = client.post(
        "/api/v1/sd/connectors/install",
        headers=auth(admin_token),
        json={"connector_id": "does-not-exist", "name": "Missing connector"},
    )
    assert r.status_code == 404


def test_marketplace_install_missing_name_returns_422(client, admin_token):
    r = client.post(
        "/api/v1/sd/connectors/install",
        headers=auth(admin_token),
        json={"connector_id": "any-id"},
    )
    assert r.status_code == 422


def test_kb_create_requires_auth(client):
    r = client.post("/api/v1/sd/kb", json={"title": "t", "body": "b"})
    assert r.status_code in (401, 403)


def test_kb_versions_nonexistent_article_returns_404(client, admin_token):
    r = client.get("/api/v1/sd/kb/not-found-article/versions", headers=auth(admin_token))
    assert r.status_code == 404


def test_kb_rollback_nonexistent_version_returns_404(client, admin_token):
    created = client.post(
        "/api/v1/sd/kb",
        headers=auth(admin_token),
        json={"title": "KB rollback test", "body": "v1", "status": "draft"},
    )
    assert created.status_code == 200
    article_id = created.json()["id"]

    r = client.post(f"/api/v1/sd/kb/{article_id}/rollback/999", headers=auth(admin_token))
    assert r.status_code == 404
