"""El usuario del portal y su organizacion (auditoria 2026-11)."""
from __future__ import annotations




def test_la_via_de_la_pantalla_tambien_hereda_la_del_cliente(client, superadmin_token, db):
    """La pantalla da de alta por POST /portal/clients, no por /clients/{id}/portal-users.

    Con un administrador normal el filtro de organizacion ya hace que coincidan
    (solo ve clientes de la suya); difieren con el superadministrador, que da
    de alta usuarios para clientes de cualquier organizacion.
    """
    from app.models.client_portal import ClientUser
    from app.models.clients import Client
    from tests.conftest import auth

    db.add(Client(id="cli-pant", name="Beta", organization_id="org-beta"))
    db.commit()
    r = client.post("/api/v1/portal/clients", headers=auth(superadmin_token), json={
        "full_name": "Ana", "email": "ana@beta-demo.com", "password": "Clave-segura-123", "client_org_id": "cli-pant"})
    assert r.status_code == 200, r.text
    assert db.query(ClientUser).filter_by(email="ana@beta-demo.com").one().organization_id == "org-beta"
