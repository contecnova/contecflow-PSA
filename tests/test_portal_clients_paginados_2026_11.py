"""GET /portal/clients pagina con el mecanismo comun (fase 2, #22).

Antes devolvia siempre la lista entera, sin `page`/`page_size` ni total. Ahora
usa `app.core.paginacion`: total en `X-Total-Count` y `meta.total`; sin
parametros, la misma lista de antes (compatible con quien ya la consume).
"""
from __future__ import annotations

from tests.conftest import auth

CLAVE = "Clave-de-prueba-123!"


def _proyecto_con_clientes(client, pm_token, codigo: str, n: int) -> str:
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Portal", "code": codigo, "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    for i in range(n):
        r = client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
            "project_ids": [pid], "full_name": f"Cliente {i:02d}",
            "email": f"pag{codigo.lower()}{i}@cli.example", "password": CLAVE})
        assert r.status_code == 200, r.text
    return pid


def test_pagina_con_total_y_sin_solapes(client, pm_token):
    pid = _proyecto_con_clientes(client, pm_token, "PGC1", 5)

    r1 = client.get("/api/v1/portal/clients", headers=auth(pm_token),
                    params={"project_id": pid, "page": 1, "page_size": 2})
    assert r1.status_code == 200, r1.text
    assert r1.headers["X-Total-Count"] == "5"
    cuerpo = r1.json()
    assert cuerpo["meta"]["total"] == 5 and cuerpo["meta"]["has_more"] is True
    assert [c["full_name"] for c in cuerpo["items"]] == ["Cliente 00", "Cliente 01"]

    r3 = client.get("/api/v1/portal/clients", headers=auth(pm_token),
                    params={"project_id": pid, "page": 3, "page_size": 2}).json()
    assert [c["full_name"] for c in r3["items"]] == ["Cliente 04"]
    assert r3["meta"]["has_more"] is False


def test_sin_parametros_devuelve_la_lista_entera_como_antes(client, pm_token):
    pid = _proyecto_con_clientes(client, pm_token, "PGC2", 3)

    r = client.get("/api/v1/portal/clients", headers=auth(pm_token), params={"project_id": pid})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 3
    # Misma forma que antes: los campos que lee el frontend siguen ahi.
    assert {"id", "full_name", "email", "project_ids", "is_active"} <= set(items[0])
    assert r.headers["X-Total-Count"] == "3"
