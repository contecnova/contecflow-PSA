"""Informes: guardados en el servidor, métricas que fallan lo dicen (revisión 2026-11).

Medido antes:
- los informes guardados vivían en una variable de la página y se perdían al recargar;
- `projects_by_client` estaba en el catálogo sin cálculo y salía vacío;
- un cálculo que fallaba devolvía filas vacías, como si no hubiera datos, y se cacheaba.
"""
from __future__ import annotations

from app.api.v1.endpoints import analytics
from tests.conftest import auth


def test_EL_HALLAZGO_los_guardados_se_quedan_y_extra_no_pisa_otras_claves(client, dev_token):
    h = auth(dev_token)
    assert client.patch("/api/v1/users/me/preferences", headers=h, json={"extra": {"otra_pantalla": 1}}).status_code == 200
    guardado = [{"id": "1", "name": "Horas", "metric": "hours_by_week"}]
    assert client.patch("/api/v1/users/me/preferences", headers=h,
                        json={"extra": {"informes_guardados": guardado}}).status_code == 200
    extra = client.get("/api/v1/users/me/preferences", headers=h).json()["data"]["extra"]
    assert extra == {"otra_pantalla": 1, "informes_guardados": guardado}
    client.patch("/api/v1/users/me/preferences", headers=h, json={"extra": {"otra_pantalla": None}})
    assert client.get("/api/v1/users/me/preferences", headers=h).json()["data"]["extra"] == {"informes_guardados": guardado}


def test_EL_HALLAZGO_proyectos_por_cliente_tiene_calculo(client, admin_token):
    r = client.post("/api/v1/projects", headers=auth(admin_token), json={
        "name": "P Cliente", "code": "PBC1", "status": "active", "billing_type": "time_material", "client_name": "Acme"})
    assert r.status_code in (200, 201), r.text
    datos = client.get("/api/v1/analytics/query/projects_by_client", headers=auth(admin_token),
                       params={"no_cache": True}).json()["data"]
    assert "error" not in datos["meta"]
    assert any(f["label"] == "Acme" and f["value"] >= 1 for f in datos["rows"])


def test_EL_HALLAZGO_una_metrica_que_falla_lo_dice(client, admin_token, monkeypatch):
    def revienta(**k):
        raise RuntimeError("boom")
    monkeypatch.setitem(analytics.METRIC_REGISTRY, "projects_by_status", revienta)
    client.post("/api/v1/projects", headers=auth(admin_token), json={
        "name": "P Falla", "code": "PBC2", "status": "active", "billing_type": "time_material"})
    datos = client.get("/api/v1/analytics/query/projects_by_status", headers=auth(admin_token),
                       params={"no_cache": True}).json()["data"]
    assert datos["rows"] == [] and datos["meta"]["error"]
