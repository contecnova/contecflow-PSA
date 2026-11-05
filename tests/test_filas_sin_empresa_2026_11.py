"""Filas sin empresa que la empresa no veía (revisión 2026-11).

Medido en la base de un despliegue (379 tablas): tipos de cambio, instantáneas
de métricas ITSM, predicciones del oráculo, mensajes del asistente y SSO sin
empresa. Los tipos de cambio son globales a propósito pero el filtro los
escondía (y rentabilidad convertía 1 a 1); lo demás se creaba en trabajos de
fondo o como superadmin sin empresa.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.session import sin_filtro_de_tenant
from app.models.bookings import ExchangeRate
from app.core import timeutil
from tests.conftest import auth


def _convertir(client, token):
    r = client.get("/api/v1/currency/convert", headers=auth(token),
                   params={"amount": 100, "from_currency": "EUR", "to_currency": "USD"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _global(db, tasa=1.10):
    """Un tipo SIN empresa de verdad (el sellado no debe poder ponérsela)."""
    from sqlalchemy import insert
    db.execute(insert(ExchangeRate.__table__).values(
        id="tipo-global", organization_id=None, from_currency="EUR", to_currency="USD", rate=tasa,
        effective_date=timeutil.today(), source="ecb"))
    db.commit()
    with sin_filtro_de_tenant(db):
        assert db.get(ExchangeRate, "tipo-global").organization_id is None


def test_EL_HALLAZGO_el_usuario_de_empresa_ve_el_tipo_global(client, pm_token, db):
    _global(db)
    datos = _convertir(client, pm_token)
    assert abs(float(datos.get("rate") or datos.get("exchange_rate") or 0) - 1.10) < 1e-6, datos


def test_el_tipo_manual_es_de_la_empresa_y_gana_sin_tocar_el_global(client, admin_token, pm_token, db):
    _global(db)
    r = client.post("/api/v1/currency/rates", headers=auth(admin_token),
                    json={"from_currency": "EUR", "to_currency": "USD", "rate": 1.25})
    assert r.status_code == 201, r.text
    datos = _convertir(client, pm_token)
    assert abs(float(datos.get("rate") or datos.get("exchange_rate") or 0) - 1.25) < 1e-6, datos
    with sin_filtro_de_tenant(db):
        filas = {(f.organization_id, f.rate) for f in db.query(ExchangeRate).filter(ExchangeRate.to_currency == "USD")}
    assert filas == {(None, 1.10), ("1", 1.25)}, "el global sigue igual; el manual es de la empresa"


def test_EL_HALLAZGO_la_instantanea_de_metricas_es_por_empresa(db):
    from app.models.mfa import Organization
    from app.models.service_desk import ITSMMetricSnapshot, Ticket
    from app.services.service_desk.analytics_service import persist_metric_snapshot
    db.add(Organization(id="org-snap", name="Otra", slug="org-snap"))
    db.flush()
    ahora = datetime.now(timezone.utc)
    for org, n in (("1", "TK-S1"), ("org-snap", "TK-S2")):
        db.add(Ticket(number=n, title="t", description="d", ticket_type="incident", organization_id=org, created_at=ahora))
    db.commit()
    resumen = persist_metric_snapshot(db)
    assert resumen["snapshots"] == 2
    with sin_filtro_de_tenant(db):
        orgs = sorted(o for (o,) in db.query(ITSMMetricSnapshot.organization_id))
    assert orgs == ["1", "org-snap"], "una por empresa y ninguna sin empresa"


def test_EL_HALLAZGO_las_predicciones_del_job_llevan_empresa(db):
    from app.models.ai_chat import AIPrediction
    from app.models.service_desk import Ticket
    from app.services.ai_modules.oracle import _oracle_sla_breach
    from datetime import timedelta
    t = Ticket(number="TK-O1", title="viejo", description="d", ticket_type="incident", organization_id="1", priority="p1_critical",
               created_at=datetime.now(timezone.utc) - timedelta(days=10))
    db.add(t)
    db.commit()
    db.info.clear()   # como el job: sesión sin contexto de empresa
    _oracle_sla_breach(db, [t], datetime.now(timezone.utc))
    db.commit()
    with sin_filtro_de_tenant(db):
        preds = db.query(AIPrediction).filter(AIPrediction.entity_id == t.id).all()
    assert preds and all(p.organization_id == "1" for p in preds)
