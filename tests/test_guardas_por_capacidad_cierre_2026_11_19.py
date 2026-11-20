"""Cierre de las guardas que faltaban por migrar a `requiere_capacidad` (19-11-2026).

Costes (`/user-costs`), tarifas (`/rate-cards`), formularios públicos
(`/forms`), portal de desarrolladores (`/developer`), importación masiva
(`/billing-reports/import/*`), licencias y activos (`/alm`, `/alm/uso`) y
calendarios SLA (`/cmdb/sla-calendars`) pasan de `require_*` a la capacidad
con EXACTAMENTE los mismos roles. Donde la pantalla y la API tenían roles
distintos se desdobla la capacidad (la de la pantalla no cambia):

- `tarifas.config` (pantalla, admin/PM) + `tarifas.gestionar` (API, gestores);
- `integraciones.desarrollo` (pantalla y /developer, admin/PM) +
  `integraciones.importar` (API de importación, gestores);
- `alm.ver` (pantalla, admin/PM) + `alm.gestionar` (gestores),
  `alm.consultar` (internos) y `alm.conexiones` (admin).

`costes.config`, `integraciones.desarrollo` y `portal.formularios` pierden el
módulo `settings`: sus rutas no están bajo /settings, así que con módulo un rol
personalizado que cierra Ajustes perdería rutas que hoy tiene.
"""
from __future__ import annotations

import pytest

from app.core.capacidades import ADMIN, ADMIN_PM, ADMIN_RRHH, CAPACIDADES, GESTORES, INTERNOS
from tests.conftest import auth

#: capacidad → roles que tenía la guarda `require_*` que sustituye.
ROLES_DE_ANTES = {
    "costes.config": ADMIN_RRHH,             # require_admin_or_hr
    "tarifas.gestionar": GESTORES,           # require_any_manager
    "portal.formularios": ADMIN_PM,          # require_admin_or_pm
    "integraciones.desarrollo": ADMIN_PM,    # require_admin_or_pm
    "integraciones.importar": GESTORES,      # require_any_manager
    "alm.gestionar": GESTORES,               # require_any_manager
    "alm.consultar": INTERNOS,               # require_internal_user
    "alm.conexiones": ADMIN,                 # require_admin
    "sd.disenar_flujos": ADMIN_PM,           # require_admin_or_pm
}

#: (método, prefijo de ruta) → capacidad que la guarda ahora.
RUTAS_MIGRADAS = {
    ("POST", "/api/v1/user-costs/countries"): "costes.config",
    ("GET", "/api/v1/user-costs/summary"): "costes.config",
    ("POST", "/api/v1/rate-cards"): "tarifas.gestionar",
    ("POST", "/api/v1/forms"): "portal.formularios",
    ("POST", "/api/v1/developer/apps"): "integraciones.desarrollo",
    ("POST", "/api/v1/billing-reports/import/execute"): "integraciones.importar",
    ("GET", "/api/v1/billing-reports/import/jobs"): "integraciones.importar",
    ("GET", "/api/v1/alm/dashboard"): "alm.gestionar",
    ("GET", "/api/v1/alm/config"): "alm.consultar",
    ("GET", "/api/v1/alm/uso/panel"): "alm.gestionar",
    ("GET", "/api/v1/alm/uso/conexiones"): "alm.conexiones",
    ("POST", "/api/v1/cmdb/sla-calendars"): "sd.disenar_flujos",
}


def _capacidades_de_la_ruta(metodo: str, ruta: str) -> set[str]:
    from app.core.deps import RequiereCapacidad
    from app.main import app

    def _recorrer(dep):
        for d in dep.dependencies:
            if isinstance(d.call, RequiereCapacidad):
                yield d.call.capacidad
            yield from _recorrer(d)

    for route in app.routes:
        if getattr(route, "path", None) == ruta and metodo in (getattr(route, "methods", None) or set()):
            return set(_recorrer(route.dependant))
    raise AssertionError(f"no existe {metodo} {ruta}")


@pytest.mark.parametrize("capacidad,roles", sorted(ROLES_DE_ANTES.items()))
def test_mismos_roles_que_la_guarda_de_antes(capacidad, roles):
    assert set(CAPACIDADES[capacidad].roles) == set(roles)


@pytest.mark.parametrize("capacidad", ["costes.config", "integraciones.desarrollo", "portal.formularios",
                                       "tarifas.gestionar", "integraciones.importar", "alm.gestionar",
                                       "alm.consultar", "alm.conexiones", "sd.disenar_flujos"])
def test_sin_modulo_porque_sus_rutas_no_estan_bajo_settings(capacidad):
    assert CAPACIDADES[capacidad].modulo is None


def test_la_pantalla_sigue_igual():
    """Las capacidades de pantalla conservan sus roles (admin/PM)."""
    assert set(CAPACIDADES["tarifas.config"].roles) == set(ADMIN_PM)
    assert set(CAPACIDADES["alm.ver"].roles) == set(ADMIN_PM)
    assert set(CAPACIDADES["integraciones.desarrollo"].roles) == set(ADMIN_PM)
    assert set(CAPACIDADES["costes.config"].roles) == set(ADMIN_RRHH)


@pytest.mark.parametrize("clave,capacidad", sorted(RUTAS_MIGRADAS.items()))
def test_la_ruta_lleva_la_capacidad(clave, capacidad):
    metodo, ruta = clave
    assert capacidad in _capacidades_de_la_ruta(metodo, ruta)


def test_no_quedan_require_en_los_ficheros_migrados():
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints"
    guarda = re.compile(r"Depends\(require_(admin_or_pm|admin_or_hr|any_manager|internal_user|admin)\)")
    for nombre in ("user_costs.py", "rate_cards.py", "public_forms.py", "developer_portal.py",
                   "alm.py", "alm_uso.py"):
        assert not guarda.search((raiz / nombre).read_text(encoding="utf-8")), nombre


def test_por_http_deniega_con_capacidad_requerida(client, dev_token, sub_token, pm_token):
    r = client.get("/api/v1/user-costs/summary", headers=auth(pm_token))
    assert r.status_code == 403 and r.json().get("code") == "capacidad_requerida"
    assert r.json().get("params") == {"capacidad": "costes.config"}
    r = client.get("/api/v1/alm/dashboard", headers=auth(dev_token))
    assert r.status_code == 403 and r.json()["params"] == {"capacidad": "alm.gestionar"}
    r = client.get("/api/v1/alm/config", headers=auth(sub_token))
    assert r.status_code == 403 and r.json()["params"] == {"capacidad": "alm.consultar"}
    r = client.get("/api/v1/alm/uso/conexiones", headers=auth(pm_token))
    assert r.status_code == 403 and r.json()["params"] == {"capacidad": "alm.conexiones"}
    r = client.get("/api/v1/billing-reports/import/jobs", headers=auth(dev_token))
    assert r.status_code == 403 and r.json()["params"] == {"capacidad": "integraciones.importar"}


def test_por_http_dejan_pasar_a_los_mismos(client, admin_token, pm_token, dev_token):
    assert client.get("/api/v1/alm/dashboard", headers=auth(pm_token)).status_code != 403
    assert client.get("/api/v1/alm/config", headers=auth(dev_token)).status_code != 403
    assert client.get("/api/v1/alm/uso/conexiones", headers=auth(admin_token)).status_code != 403
    assert client.get("/api/v1/billing-reports/import/jobs", headers=auth(pm_token)).status_code != 403
    assert client.get("/api/v1/user-costs/summary", headers=auth(admin_token)).status_code != 403
