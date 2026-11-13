from tests.conftest import auth


def test_jira_api_token_is_encrypted_at_rest(client, admin_token, db):
    payload = {
        "jira_url": "https://test.atlassian.net",
        "jira_email": "admin@test.com",
        "jira_api_token": "ATATT3xFfGF0TestToken123",
        "jira_project_key": "TST",
    }

    res = client.post("/api/v1/jira/config", json=payload, headers=auth(admin_token))
    assert res.status_code == 200, res.text

    # Auditoria 2026-11 (#34): la conexion de las tareas vive en `sd_jira_configs`.
    from app.models.jira_integration import JiraConfig

    row = db.query(JiraConfig).filter(
        JiraConfig.organization_id == "1", JiraConfig.usar_para_tareas.is_(True),
    ).first()

    assert row is not None
    assert row.jira_api_token_enc is not None
    assert row.jira_api_token_enc.startswith("v2:") or row.jira_api_token_enc.startswith("kmsv1:")
