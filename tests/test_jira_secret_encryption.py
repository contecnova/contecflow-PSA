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

    from app.models.settings import AppSetting

    row = db.query(AppSetting).filter(
        AppSetting.key == "jira_api_token",
        AppSetting.organization_id == "1",
    ).first()
    # In some test paths org_id may persist as int/string depending on SQLite coercion.
    if row is None:
        row = db.query(AppSetting).filter(AppSetting.key == "jira_api_token").first()

    assert row is not None
    assert row.value is not None
    assert row.value.startswith("v2:") or row.value.startswith("kmsv1:")
