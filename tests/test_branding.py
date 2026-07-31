def test_update_branding_all_fields(client, admin_token, db):
    payload = {
        "app_name": "MiEmpresa",
        "logo_url": "https://cdn.miempresa.com/logo.png",
        "primary_color": "#123456",
        "custom_domain": "miempresa.com",
        "hide_powered_by": True,
        "custom_css_vars": {"--main-bg": "#fff"}
    }
    res = client.put("/api/v1/orgs/1/branding", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()["data"]
    for k, v in payload.items():
        assert data[k] == v
