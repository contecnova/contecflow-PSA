import pytest

from tests.conftest import auth

from app.services.service_desk.cmdb_discovery_service import discover_gcp


def test_discover_gcp_requires_project_id():
    with pytest.raises(ValueError, match="project_id"):
        discover_gcp({})


def test_cmdb_reconciliation_candidates_requires_admin(client, dev_token):
    res = client.get(
        "/api/v1/sd/cmdb/discovery/reconciliation-candidates",
        headers=auth(dev_token),
    )
    assert res.status_code == 403


def test_cmdb_reconciliation_merge_requires_admin(client, dev_token):
    res = client.post(
        "/api/v1/sd/cmdb/discovery/reconciliation-merge",
        headers=auth(dev_token),
    )
    assert res.status_code == 403
