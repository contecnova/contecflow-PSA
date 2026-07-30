from tests.conftest import auth


def test_bi_shared_views_crud_flow(client, admin_token):
    listed = client.get('/api/v1/bi/collaboration/shared-views', headers=auth(admin_token))
    assert listed.status_code == 200
    assert 'items' in listed.json()

    created = client.post(
        '/api/v1/bi/collaboration/shared-views',
        headers=auth(admin_token),
        json={
            'name': 'Executive weekly review',
            'dashboard_key': 'executive',
            'filters': {'period_days': 30, 'department': 'support'},
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()['data']['view']
    view_id = payload['id']
    assert payload['name'] == 'Executive weekly review'

    patched = client.patch(
        f'/api/v1/bi/collaboration/shared-views/{view_id}',
        headers=auth(admin_token),
        json={'name': 'Executive monthly review', 'filters': {'period_days': 90}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()['data']['view']['name'] == 'Executive monthly review'

    listed_after = client.get('/api/v1/bi/collaboration/shared-views', headers=auth(admin_token))
    assert listed_after.status_code == 200
    items = listed_after.json().get('items', [])
    assert any(v.get('id') == view_id for v in items)


def test_bi_shared_views_not_found_returns_404(client, admin_token):
    res = client.patch(
        '/api/v1/bi/collaboration/shared-views/not-found-id',
        headers=auth(admin_token),
        json={'name': 'missing view'},
    )
    assert res.status_code == 404
