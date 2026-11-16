"""Periodo libre en informes de seguridad, gobierno y observabilidad (16-11-2026).

Todos los datos de este grupo son instantes (eventos, decisiones ABAC,
evaluaciones de IA, accesos, derivas): admiten granularidad por hora
(``CON_HORA``). Se comprueba en cada endpoint migrado que:

- el alias histórico (``days``, ``hours``, ``lookback_days``) sigue valiendo;
- ``desde``/``hasta`` filtran ``[desde, hasta)`` (también hacia el pasado);
- los errores de periodo salen como 422 con ``detail.code = periodo.<motivo>``;
- las series (``abac/admin/access-patterns``, ``soc/metrics/timeline``,
  ``soc/metrics/mttd-mttr``) devuelven todos los tramos con ``t`` y respetan
  ``granularidad``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth

ORG = "1"
UTC = timezone.utc


def _ahora() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).isoformat()


@pytest.fixture()
def admin_org(admin_token, db):
    """El admin de prueba en la empresa ``1`` (informes acotados por empresa)."""
    from app.models.user import User
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    admin.organization_id = ORG
    db.commit()
    return admin_token


def _codigo(r) -> str:
    detalle = r.json().get("detail")
    return detalle.get("code") if isinstance(detalle, dict) else ""


# ── ABAC admin ────────────────────────────────────────────────────────────────

def _decisiones_abac(db, ahora):
    from app.models.abac import PolicyAudit
    for dias, resultado in ((0.1, "deny"), (0.2, "allow"), (3, "deny"), (20, "deny")):
        db.add(PolicyAudit(id=str(uuid.uuid4()), org_id=ORG, action="access_denied" if resultado == "deny" else "access_allowed",
                           resource_type="timesheet", result=resultado,
                           created_at=(ahora - timedelta(days=dias)).replace(tzinfo=None)))
    db.commit()


def test_abac_stats_days_sigue_valiendo(client, admin_org, db):
    ahora = _ahora()
    _decisiones_abac(db, ahora)
    r = client.get("/api/v1/abac/admin/audit-log/stats", headers=auth(admin_org), params={"days": 7})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 3 and d["denials"] == 2
    assert d["periodo"]["origen"] == "days"


def test_abac_stats_desde_hasta_filtra_un_tramo_pasado(client, admin_org, db):
    ahora = _ahora()
    _decisiones_abac(db, ahora)
    r = client.get("/api/v1/abac/admin/audit-log/stats", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=4)), "hasta": _iso(ahora - timedelta(days=1))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 1 and d["denials"] == 1
    assert d["periodo"]["origen"] == "rango"


def test_abac_access_patterns_serie_por_hora(client, admin_org, db):
    ahora = _ahora()
    _decisiones_abac(db, ahora)
    r = client.get("/api/v1/abac/admin/access-patterns", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(hours=12)), "hasta": _iso(ahora), "granularidad": "hour", "tz": "UTC"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    serie = d["daily_trend"]
    assert d["periodo"]["granularidad"] == "hour"
    assert len(serie) in (12, 13)  # 12 h que pueden empezar a mitad de hora
    assert all("t" in p and "date" in p for p in serie)
    assert sum(p["deny"] for p in serie) == 1 and sum(p["allow"] for p in serie) == 1


def test_abac_overview_rechaza_desde_mayor_que_hasta(client, admin_org):
    r = client.get("/api/v1/abac/admin/overview", headers=auth(admin_org),
                   params={"desde": "2026-11-10", "hasta": "2026-11-01"})
    assert r.status_code == 422 and _codigo(r) == "periodo.desde_mayor_que_hasta"


def test_abac_days_fuera_del_limite_historico(client, admin_org):
    r = client.get("/api/v1/abac/admin/access-patterns", headers=auth(admin_org), params={"days": 91})
    assert r.status_code == 422


# ── Gobierno de IA ────────────────────────────────────────────────────────────

def _evaluaciones_ia(db, ahora):
    from app.models.ai_governance import AIGuardrailAuditLog
    for horas, bloqueada in ((0.5, True), (5, False), (48, True)):
        db.add(AIGuardrailAuditLog(org_id=ORG, module="chat", scope="prompt",
                                   action_taken="blocked" if bloqueada else "none", was_blocked=bloqueada,
                                   evaluated_at=(ahora - timedelta(hours=horas)).replace(tzinfo=None)))
    db.commit()


def test_ia_audit_log_hours_sigue_valiendo(client, admin_org, db):
    _evaluaciones_ia(db, _ahora())
    r = client.get("/api/v1/ai-governance/audit-log", headers=auth(admin_org), params={"hours": 1})
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["total"] == 1


def test_ia_audit_log_acepta_days_del_selector(client, admin_org, db):
    _evaluaciones_ia(db, _ahora())
    r = client.get("/api/v1/ai-governance/audit-log", headers=auth(admin_org), params={"days": 1})
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["total"] == 2


def test_ia_stats_desde_hasta(client, admin_org, db):
    ahora = _ahora()
    _evaluaciones_ia(db, ahora)
    r = client.get("/api/v1/ai-governance/audit-log/stats", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=3)), "hasta": _iso(ahora - timedelta(hours=1))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total_evaluations"] == 2 and d["total_blocked"] == 1
    assert d["periodo"]["origen"] == "rango"


# ── SOC ───────────────────────────────────────────────────────────────────────

def _eventos_soc(db, ahora):
    from app.models.security_observability import SecurityEvent
    for horas, sev, tipo in ((0.5, "high", "login_failed"), (2.5, "low", "login_success"), (30, "medium", "login_failed")):
        db.add(SecurityEvent(id=str(uuid.uuid4()), org_id=ORG, category="auth", severity=sev, event_type=tipo,
                             ip_address="10.0.0.1", occurred_at=(ahora - timedelta(hours=horas)).replace(tzinfo=None)))
    db.commit()


def test_soc_overview_hours_y_desde_hasta(client, admin_org, db):
    ahora = _ahora()
    _eventos_soc(db, ahora)
    r = client.get("/api/v1/security-observability/soc/overview", headers=auth(admin_org), params={"hours": 1})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["total_events"] == 1
    r = client.get("/api/v1/security-observability/soc/overview", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(hours=40)), "hasta": _iso(ahora - timedelta(hours=1))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total_events"] == 2 and d["periodo"]["origen"] == "rango"


def test_soc_events_lista_del_periodo(client, admin_org, db):
    ahora = _ahora()
    _eventos_soc(db, ahora)
    r = client.get("/api/v1/security-observability/soc/events", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(hours=3)), "hasta": _iso(ahora - timedelta(hours=1))})
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["total"] == 1


def test_soc_timeline_serie_completa_por_hora(client, admin_org, db):
    ahora = _ahora()
    _eventos_soc(db, ahora)
    r = client.get("/api/v1/security-observability/soc/metrics/timeline", headers=auth(admin_org),
                   params={"hours": 24, "tz": "UTC"})
    assert r.status_code == 200, r.text
    serie = r.json()["items"]
    assert len(serie) in (24, 25)
    assert all("t" in p and p["ts"] == p["t"] for p in serie)
    assert sum(p["high"] for p in serie) == 1 and sum(p["low"] for p in serie) == 1


def test_soc_timeline_por_dia(client, admin_org, db):
    ahora = _ahora()
    _eventos_soc(db, ahora)
    r = client.get("/api/v1/security-observability/soc/metrics/timeline", headers=auth(admin_org),
                   params={"days": 3, "granularidad": "day", "tz": "UTC"})
    assert r.status_code == 200, r.text
    serie = r.json()["items"]
    assert len(serie) in (3, 4)
    assert sum(p["high"] + p["low"] + p["medium"] for p in serie) == 3


def test_soc_mttd_mttr_rellena_tramos(client, admin_org):
    r = client.get("/api/v1/security-observability/soc/metrics/mttd-mttr", headers=auth(admin_org),
                   params={"days": 7, "granularidad": "day", "tz": "UTC"})
    assert r.status_code == 200, r.text
    serie = r.json()["items"]
    assert len(serie) in (7, 8)
    assert all(p["detections"] == 0 and "date" in p and "t" in p for p in serie)


def test_soc_granularidad_desconocida(client, admin_org):
    r = client.get("/api/v1/security-observability/soc/metrics/timeline", headers=auth(admin_org),
                   params={"granularidad": "year"})
    assert r.status_code == 422 and _codigo(r) == "periodo.granularidad_invalida"


def test_soc_demasiados_puntos_por_hora(client, admin_org):
    r = client.get("/api/v1/security-observability/soc/metrics/timeline", headers=auth(admin_org),
                   params={"days": 90, "granularidad": "hour"})
    assert r.status_code == 422 and _codigo(r) == "periodo.demasiados_puntos"


def test_soc_heatmap_auto_sigue_siendo_horario(client, admin_org, db):
    ahora = _ahora()
    _eventos_soc(db, ahora)
    r = client.get("/api/v1/security-observability/soc/metrics/auth-heatmap", headers=auth(admin_org),
                   params={"days": 7, "tz": "UTC"})
    assert r.status_code == 200, r.text
    filas = r.json()["items"]
    assert sum(f["count"] for f in filas) == 2  # solo login_failed
    assert len({f["ts"] for f in filas}) == 2  # dos horas distintas


# ── BI governance ─────────────────────────────────────────────────────────────

def _accesos_bi(db, ahora):
    from app.models.enterprise import AuditLog
    for dias in (0.5, 10, 40):
        db.add(AuditLog(action="VIEW", resource="bi:report", resource_id=str(uuid.uuid4()), organization_id=ORG,
                        user_id="admin-test-id", created_at=ahora - timedelta(days=dias)))
    db.commit()


def test_bi_auditoria_days_y_rango(client, admin_org, db):
    ahora = _ahora()
    _accesos_bi(db, ahora)
    r = client.get("/api/v1/bi/governance/audit/access", headers=auth(admin_org), params={"days": 30})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["count"] == 2
    r = client.get("/api/v1/bi/governance/audit/access", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=60)), "hasta": _iso(ahora - timedelta(days=5))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["count"] == 2 and d["periodo"]["origen"] == "rango"


def test_bi_auditoria_days_mantiene_su_tope(client, admin_org):
    r = client.get("/api/v1/bi/governance/audit/access", headers=auth(admin_org), params={"days": 91})
    assert r.status_code == 422


# ── Enterprise: estadísticas del registro ─────────────────────────────────────

def test_enterprise_audit_stats_periodo(client, admin_org, db):
    ahora = _ahora()
    _accesos_bi(db, ahora)
    r = client.get("/api/v1/enterprise/audit-log/stats", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=15)), "hasta": _iso(ahora - timedelta(days=5))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["by_resource"].get("bi:report") == 1
    assert d["periodo"]["origen"] == "rango" and round(d["period_days"]) == 10


# ── Observabilidad predictiva ─────────────────────────────────────────────────

def test_salud_predictiva_lookback_days_y_days(client, admin_org):
    for params in ({"lookback_days": 7}, {"days": 7}):
        r = client.get("/api/v1/bi/predictive/observability/health", headers=auth(admin_org), params=params)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["itsm"]["lookback_days"] == 7 and d["periodo"]["origen"] == "days"


def test_salud_predictiva_desde_hasta(client, admin_org):
    ahora = _ahora()
    r = client.get("/api/v1/bi/predictive/observability/health", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=60)), "hasta": _iso(ahora - timedelta(days=30))})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["periodo"]["origen"] == "rango"


# ── CMDB: deriva ──────────────────────────────────────────────────────────────

def test_deriva_cmdb_hours_y_rango(client, admin_org):
    r = client.get("/api/v1/sd/cmdb/discovery/drift-report", headers=auth(admin_org), params={"hours": 48})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["hours"] == 48 and d["periodo"]["origen"] == "days"
    ahora = _ahora()
    r = client.get("/api/v1/sd/cmdb/discovery/drift-report", headers=auth(admin_org),
                   params={"desde": _iso(ahora - timedelta(days=10)), "hasta": _iso(ahora - timedelta(days=9))})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total_drifted"] == 0 and d["periodo"]["origen"] == "rango"
