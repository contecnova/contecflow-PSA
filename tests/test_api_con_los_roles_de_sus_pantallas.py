"""Lecturas de la API con los roles de sus pantallas, y tokens de uso concreto.

Auditoria 2026-11: un empleado podia leer por API costes (vista previa del
generador de informes), datos personales (RGPD y auditoria de accesos),
actividad de Microsoft 365 y datos crudos de ETL, y forzar la narrativa de IA
(de pago). Y el token de «incrustar un panel BI» era un token de sesion
completo.
"""
import pytest

from app.core.security import create_access_token
from tests.conftest import auth

SOLO_ADMIN_O_PM = [
    ("POST", "/api/v1/reports/preview", {"entity": "users", "fields": ["hourly_rate"]}),
    ("GET", "/api/v1/reports/schema", None),
    ("POST", "/api/v1/bi/query-builder/preview", {}),
    ("GET", "/api/v1/analytics/narrative?force_refresh=true", None),
]
SOLO_ADMIN = [
    ("GET", "/api/v1/bi/gdpr/dsr", None),
    ("GET", "/api/v1/bi/gdpr/consents", None),
    ("GET", "/api/v1/bi/gdpr/field-masks", None),
    ("GET", "/api/v1/bi/governance/audit/access", None),
    ("GET", "/api/v1/bi/o365/adoption", None),
    ("GET", "/api/v1/bi/etl/data/cualquiera", None),
]


@pytest.mark.parametrize("metodo,ruta,cuerpo", SOLO_ADMIN_O_PM + SOLO_ADMIN)
def test_un_empleado_no_las_lee(client, dev_token, metodo, ruta, cuerpo):
    r = client.request(metodo, ruta, headers=auth(dev_token), json=cuerpo)
    assert r.status_code == 403, (ruta, r.status_code, r.text[:200])


@pytest.mark.parametrize("metodo,ruta,cuerpo", SOLO_ADMIN)
def test_un_pm_no_lee_las_de_administracion(client, pm_token, metodo, ruta, cuerpo):
    assert client.request(metodo, ruta, headers=auth(pm_token), json=cuerpo).status_code == 403


def test_el_pm_si_entra_en_las_suyas(client, pm_token):
    assert client.get("/api/v1/reports/schema", headers=auth(pm_token)).status_code == 200


@pytest.mark.parametrize("claim", ["bi_embed", "bi_intelligence_stream", "ws"])
def test_un_token_de_uso_concreto_no_abre_la_api(client, claim):
    token = create_access_token(subject="admin-test-id", extra={claim: True})
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    normal = create_access_token(subject="admin-test-id")
    assert client.get("/api/v1/auth/me", headers=auth(normal)).status_code == 200
