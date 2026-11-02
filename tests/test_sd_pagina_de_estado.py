"""Pagina de estado publica por organizacion.

Auditoria 2026-11: la pagina publica (anonima) mezclaba los componentes de
todas las organizaciones: un cliente veia las caidas de otro.
"""


def test_cada_organizacion_ve_solo_sus_componentes(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.mfa import Organization
    from app.models.service_desk import StatusPageComponent

    db.add(Organization(id="org-b", name="Cliente B", slug="cliente-b"))
    db.add(StatusPageComponent(name="Web A", organization_id="1", is_public=True))
    db.add(StatusPageComponent(name="ERP B", organization_id="org-b", is_public=True, status="major_outage"))
    db.commit()
    with TestClient(app) as anonimo:
        assert anonimo.get("/api/v1/sd/status-page").status_code == 422, "con varias, hay que decir cual"
        assert anonimo.get("/api/v1/sd/status-page?org=no-existe").status_code == 404
        datos = anonimo.get("/api/v1/sd/status-page?org=cliente-b").json()["data"]
    nombres = [c["name"] for g in datos["groups"].values() for c in g]
    assert nombres == ["ERP B"] and datos["overall_status"] == "major_outage"
