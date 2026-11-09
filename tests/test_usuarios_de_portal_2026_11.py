"""Usuarios del portal: un solo camino de alta, con su tope (revisión 2026-11).

Medido antes: había dos caminos. El de la pantalla (/portal/clients) tenía
guarda de responsable y campos cerrados; el otro (/clients/{id}/portal-users),
sin pantalla, sólo exigía estar dentro —cualquier empleado daba acceso de
fuera— y su edición escribía cualquier atributo. Era el único que aplicaba
max_portal_users. Se retira el duplicado y el tope pasa al de la pantalla.
"""
from __future__ import annotations

from app.models.clients import Client, ClientPortalConfig
from tests.conftest import auth


def test_EL_HALLAZGO_el_camino_duplicado_ya_no_existe(client, admin_token):
    for metodo, ruta in (("get", "/api/v1/clients/x/portal-users"), ("post", "/api/v1/clients/x/portal-users"),
                         ("patch", "/api/v1/clients/x/portal-users/y")):
        r = client.request(metodo.upper(), ruta, headers=auth(admin_token), json={})
        assert r.status_code in (404, 405), (metodo, ruta, r.status_code)


def test_el_tope_se_aplica_en_el_alta_de_la_pantalla(client, db, admin_token):
    db.add(Client(id="cli-tope", name="Acme", organization_id="1", created_by="admin-test-id"))
    db.add(ClientPortalConfig(client_id="cli-tope", max_portal_users=1, organization_id="1"))
    db.commit()
    alta = lambda email: client.post("/api/v1/portal/clients", headers=auth(admin_token), json={
        "full_name": "Ana", "email": email, "password": "Clave-segura-123", "client_org_id": "cli-tope"})
    assert alta("ana@acme.example").status_code == 200
    r = alta("otra@acme.example")
    assert r.status_code == 400 and "Límite" in r.json()["detail"]


def test_un_empleado_no_da_acceso_de_fuera(client, dev_token):
    r = client.post("/api/v1/portal/clients", headers=auth(dev_token), json={
        "full_name": "X", "email": "x@x.example", "password": "Clave-segura-123", "client_org_id": "cli-tope"})
    assert r.status_code == 403
