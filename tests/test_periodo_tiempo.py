"""Periodo libre en informes de tiempo y recursos (16-11-2026).

- ``/alm/integracion/proyectos/{id}/recursos``: coste del periodo por día de
  calendario (``SIN_HORA``, sin serie). ``hasta`` es exclusivo como en el resto
  de informes; el último día que se calcula es ``p.fecha_hasta``.
- ``/resource-forecast/utilization-trend``: serie semanal (solo ``week``);
  ``weeks_past``/``weeks_future`` siguen valiendo sin ``desde``.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core import timeutil
from tests.conftest import auth

ORG = "1"


def _proyecto(db):
    from app.models.project import Project, ProjectType
    p = Project(id=str(uuid.uuid4()), organization_id=ORG, name="Proyecto periodo", code=f"P{uuid.uuid4().hex[:5]}",
                project_type=list(ProjectType)[0], pm_id="pm-test-id")
    db.add(p)
    db.flush()
    return p


# ── Recursos técnicos del proyecto ────────────────────────────────────────────

def test_recursos_del_proyecto_sin_periodo_usa_30_dias(client, pm_token, db):
    p = _proyecto(db)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["periodo"]["origen"] == "defecto"
    assert date.fromisoformat(d["hasta"]) - date.fromisoformat(d["desde"]) >= timedelta(days=29)


def test_recursos_del_proyecto_desde_hasta_con_hasta_exclusivo(client, pm_token, db):
    p = _proyecto(db)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token),
                   params={"desde": "2026-10-01", "hasta": "2026-11-01", "tz": "Europe/Madrid"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["desde"] == "2026-10-01" and d["hasta"] == "2026-10-31"
    assert d["periodo"]["origen"] == "rango" and d["periodo"]["zona"] == "Europe/Madrid"


def test_recursos_del_proyecto_days_sigue_valiendo(client, pm_token, db):
    p = _proyecto(db)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token), params={"days": 7})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["periodo"]["origen"] == "days"


def test_recursos_del_proyecto_rechaza_hora(client, pm_token, db):
    p = _proyecto(db)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token),
                   params={"days": 7, "granularidad": "hour"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.hora_no_admitida"


def test_recursos_del_proyecto_desde_mayor_que_hasta(client, pm_token, db):
    p = _proyecto(db)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token),
                   params={"desde": "2026-11-10", "hasta": "2026-11-01"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.desde_mayor_que_hasta"


# ── Tendencia de utilización ──────────────────────────────────────────────────

URL_TENDENCIA = "/api/v1/resource-forecast/utilization-trend"


def test_tendencia_alias_viejos_sin_periodo(client, admin_token):
    r = client.get(URL_TENDENCIA, headers=auth(admin_token), params={"weeks_past": 4, "weeks_future": 2})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert len(d["weeks"]) == 4 + 2 + 1 and d["periodo"] is None


def test_tendencia_desde_hasta_filtra_semanas_e_imputaciones(client, admin_token, db):
    from app.models.imputation import Imputation
    p = _proyecto(db)
    hoy = timeutil.today()
    lunes = hoy - timedelta(days=hoy.weekday()) - timedelta(weeks=4)
    # Una imputación dentro (primera semana) y otra fuera del periodo (semana siguiente al fin).
    db.add(Imputation(id=str(uuid.uuid4()), organization_id=ORG, user_id="dev-test-id", project_id=p.id,
                      date=lunes + timedelta(days=2), hours=8))
    db.add(Imputation(id=str(uuid.uuid4()), organization_id=ORG, user_id="dev-test-id", project_id=p.id,
                      date=lunes + timedelta(days=15), hours=8))
    db.commit()
    r = client.get(URL_TENDENCIA, headers=auth(admin_token),
                   params={"user_id": "dev-test-id", "desde": lunes.isoformat(),
                           "hasta": (lunes + timedelta(days=14)).isoformat(), "granularidad": "week"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert len(d["weeks"]) == 2 and d["periodo"]["origen"] == "rango"
    serie = d["users"][0]["series"]
    assert serie[0]["hours"] == 8 and serie[1]["hours"] == 0
    assert all(not s["is_future"] for s in serie)
    assert d["team"][0]["t"].startswith(lunes.isoformat())


def test_tendencia_solo_admite_semanas(client, admin_token):
    r = client.get(URL_TENDENCIA, headers=auth(admin_token), params={"granularidad": "day"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.granularidad_no_admitida"
    r = client.get(URL_TENDENCIA, headers=auth(admin_token), params={"granularidad": "hour"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.hora_no_admitida"
