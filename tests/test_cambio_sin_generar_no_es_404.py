"""Planes de un cambio aún no generados: 200 con data=null, no 404 (19-11-2026).

La ficha del cambio consulta siempre el análisis de impacto, los planes de vuelta
atrás, pruebas y comunicaciones y el workflow del CAB; «todavía no existe» no es
un error y antes el navegador anotaba un 404 por cada uno. El 404 queda para un
cambio que no existe.
"""
import pytest

from app.models.service_desk import ITSMChangeRequest
from tests.conftest import auth


@pytest.fixture
def cambio(db):
    c = ITSMChangeRequest(id="chg-sin-planes", number="CHG-SP1", title="Sin planes", description="x",
                          status="submitted", organization_id="1")
    db.add(c)
    db.commit()
    return c


@pytest.mark.parametrize("ruta", ["impact-analysis", "rollback-plan", "testing-plan", "comms-plan", "cab/workflow"])
def test_sin_generar_es_200_con_null(client, admin_token, cambio, ruta):
    r = client.get(f"/api/v1/sd/changes/{cambio.id}/{ruta}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"] is None


def test_cambio_inexistente_sigue_siendo_404(client, admin_token):
    r = client.get("/api/v1/sd/changes/no-existe/impact-analysis", headers=auth(admin_token))
    assert r.status_code == 404
