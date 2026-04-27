from tests.conftest import auth
from app.models.marketplace import IntegrationConnector


def _authz_status(resp):
    # Some endpoints may return 401 (no auth) or 403 (auth but no scope/role)
    return resp.status_code


def _minimal_valid_graph():
    return {
        'nodes': [
            {'id': 'start_1', 'type': 'start'},
            {'id': 'end_1', 'type': 'end'},
        ],
        'edges': [
            {'source': 'start_1', 'target': 'end_1'},
        ],
    }


def _ensure_test_connector(db):
    existing = db.query(IntegrationConnector).filter(IntegrationConnector.slug == 'jira-test').first()
    if existing:
        return existing

    connector = IntegrationConnector(
        name='Jira Test Connector',
        slug='jira-test',
        category='itsm',
        description='Connector seeded by authz tests',
        docs_url='https://example.test/docs/jira',
        auth_scheme='api_key',
        is_active=True,
        is_certified=True,
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)
    return connector


def test_workflow_designer_blueprints_requires_auth(client):
    r = client.get('/api/v1/sd/workflow-designer/blueprints')
    assert _authz_status(r) in (401, 403)


def test_workflow_designer_create_forbidden_for_employee(client, dev_token):
    payload = {
        'name': 'WF forbidden employee',
        'process_type': 'ticket',
        'graph': _minimal_valid_graph(),
    }
    r = client.post('/api/v1/sd/workflow-designer/blueprints', headers=auth(dev_token), json=payload)
    assert _authz_status(r) == 403


def test_workflow_designer_create_allowed_for_pm(client, pm_token):
    payload = {
        'name': 'WF by pm',
        'process_type': 'ticket',
        'graph': _minimal_valid_graph(),
    }
    r = client.post('/api/v1/sd/workflow-designer/blueprints', headers=auth(pm_token), json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get('name') == payload['name']


def test_governance_metrics_catalog_requires_auth(client):
    r = client.get('/api/v1/sd/governance/metrics/catalog')
    assert _authz_status(r) in (401, 403)


def test_governance_quality_contract_forbidden_for_employee(client, dev_token):
    r = client.get('/api/v1/sd/governance/quality-contract', headers=auth(dev_token))
    assert _authz_status(r) == 403


def test_governance_quality_contract_allowed_for_pm(client, pm_token):
    r = client.get('/api/v1/sd/governance/quality-contract', headers=auth(pm_token))
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_connectors_marketplace_requires_auth(client):
    r = client.get('/api/v1/sd/connectors/marketplace')
    assert _authz_status(r) in (401, 403)


def test_connectors_install_forbidden_for_employee(client, dev_token, db):
    seeded = _ensure_test_connector(db)

    marketplace = client.get('/api/v1/sd/connectors/marketplace', headers=auth(dev_token))
    assert marketplace.status_code == 200
    connectors = marketplace.json()
    assert connectors, 'Expected at least one connector in marketplace'

    payload = {'connector_id': seeded.id, 'name': 'Forbidden install by employee'}
    r = client.post('/api/v1/sd/connectors/install', headers=auth(dev_token), json=payload)
    assert _authz_status(r) == 403


def test_connectors_install_allowed_for_pm(client, pm_token, db):
    seeded = _ensure_test_connector(db)

    marketplace = client.get('/api/v1/sd/connectors/marketplace', headers=auth(pm_token))
    assert marketplace.status_code == 200
    connectors = marketplace.json()
    assert connectors, 'Expected at least one connector in marketplace'

    payload = {'connector_id': seeded.id, 'name': 'PM connector install'}
    r = client.post('/api/v1/sd/connectors/install', headers=auth(pm_token), json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get('ok') is True
    assert data.get('instance_id')
