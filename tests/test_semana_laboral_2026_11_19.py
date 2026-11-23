"""Semana laboral sin lunes-a-viernes fijo (19-11-2026).

Medido antes: `weekday() < 5` y capacidad/5 en las métricas de capacidad, los
escenarios, el mapa de reservas, las horas de un externo y el recordatorio de
imputaciones; la pausa del SLA contaba días enteros L-V en UTC sin horario ni
festivos; y alertas (08:00), campaña de presupuestos (08:30) e imputaciones
(18:00 L-V) corrían a una hora fija en la zona global del worker.

Aquí: SLA con festivo y horario SLA_BUSINESS_*, capacidad de una persona con
jornada de martes a sábado, recordatorio de imputaciones con su horario, y los
avisos a la hora local de cada empresa.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.settings import Holiday
from app.models.user import User, UserRole, UserStatus
from app.services.horario import efectivo as hor
from app.services.horario import jornadas
from app.services.settings_service import set_runtime_value
from tests.conftest import HASH_DE_PRUEBA

ORG = "1"
LUNES = date(2026, 12, 7)
MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture
def ctx(db):
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, db.query(User).filter(User.id == "admin-test-id").first())
    return db


def _admin(db):
    return db.query(User).filter(User.id == "admin-test-id").first()


def _persona(db, uid):
    u = User(id=uid, username=uid, email=f"{uid}@t.es", full_name=uid.title(), role=UserRole.employee,
             status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id=ORG,
             weekly_capacity_hours=40.0)
    db.add(u)
    db.commit()
    return u


def _martes_a_sabado(db, u):
    admin = _admin(db)
    j = jornadas.guardar_jornada(db, admin, {"nombre": f"Martes a sábado {u.id}",
                                             "semana": {str(d): [["09:00", "17:00"]] for d in range(2, 7)}})
    jornadas.guardar_asignacion(db, admin, {"jornada_id": j["id"], "ambito": "persona", "valor": u.id})


# ── SLA: festivo de la empresa y horario SLA_BUSINESS_* ──────────────────────

def test_sla_minutos_habiles_saltan_el_festivo_y_respetan_el_horario(ctx):
    from app.models.cmdb import SLACalendar, V21SLAHoliday
    from app.services.billing_reports_service import business_minutes_between
    from app.services.sla_service import calendario_sla

    db = ctx
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "Europe/Madrid", ORG)
    for clave, valor in (("SLA_BUSINESS_HOURS_ONLY", "true"), ("SLA_BUSINESS_START_HOUR", "9"),
                         ("SLA_BUSINESS_END_HOUR", "17"), ("SLA_BUSINESS_DAYS", "1,2,3,4,5")):
        set_runtime_value(db, "sla", clave, valor, ORG)
    cal_festivos = SLACalendar(id=str(uuid.uuid4()), organization_id=ORG, name="Festivos generales",
                               applies_to_all=True, is_active=True)
    db.add(cal_festivos)
    db.flush()
    db.add(V21SLAHoliday(id=str(uuid.uuid4()), organization_id=ORG, calendar_id=cal_festivos.id,
                         holiday_date=str(LUNES + timedelta(days=2)), is_active=True, name="Miércoles festivo"))
    db.commit()

    cal = calendario_sla(db, None, ORG)
    inicio = datetime(2026, 12, 8, 16, 0, tzinfo=MADRID)   # martes 16:00
    fin = datetime(2026, 12, 10, 10, 0, tzinfo=MADRID)     # jueves 10:00 (miércoles festivo)
    # martes 16-17 (60) + miércoles festivo (0) + jueves 9-10 (60)
    assert business_minutes_between(inicio, fin, cal) == 120
    # Sin calendario, lo de antes: días enteros L-V en UTC (15:00 → 09:00 UTC del jueves).
    assert business_minutes_between(inicio, fin) == 9 * 60 + 24 * 60 + 9 * 60
    # Fuera de horario (martes 18:00 → 20:00) no corre.
    assert business_minutes_between(datetime(2026, 12, 8, 18, tzinfo=MADRID),
                                    datetime(2026, 12, 8, 20, tzinfo=MADRID), cal) == 0


# ── Capacidad con jornada de martes a sábado ─────────────────────────────────

def test_capacidad_cuenta_sabados_y_no_lunes_con_su_jornada(ctx):
    from app.services.metrics.capacity import metric_productivity_by_person
    from app.services.metrics.remaining import metric_load_by_person

    db = ctx
    u = _persona(db, "sabadista")
    _martes_a_sabado(db, u)
    domingo = LUNES + timedelta(days=6)
    plan = hor.horario(db, u.id, LUNES, domingo, estados_ausencia=None)
    assert plan[LUNES].horas == 0 and plan[LUNES + timedelta(days=5)].horas == 8

    filas, _ = metric_productivity_by_person(db, LUNES, domingo, 50, user_id=u.id)
    assert [f["capacity"] for f in filas] == [40.0]
    # Solo el lunes: antes 8 h (L-V); con su jornada, 0.
    assert metric_productivity_by_person(db, LUNES, LUNES, 50, user_id=u.id)[0] == []
    # Solo el sábado: antes 0; con su jornada, 8.
    filas, _ = metric_load_by_person(db, LUNES + timedelta(days=5), LUNES + timedelta(days=5), 50, user_id=u.id)
    assert [f["capacity"] for f in filas] == [8.0]

    # Un festivo de la empresa el sábado le quita ese día.
    db.add(Holiday(id=str(uuid.uuid4()), organization_id=ORG, name="Sábado festivo",
                   date=LUNES + timedelta(days=5)))
    db.commit()
    filas, _ = metric_productivity_by_person(db, LUNES, domingo, 50, user_id=u.id)
    assert [f["capacity"] for f in filas] == [32.0]


def test_sin_jornada_especial_la_capacidad_es_la_de_siempre(ctx):
    from app.services.metrics.capacity import metric_productivity_by_person

    db = ctx
    u = _persona(db, "normal")
    filas, _ = metric_productivity_by_person(db, LUNES, LUNES + timedelta(days=13), 50, user_id=u.id)
    assert [f["capacity"] for f in filas] == [80.0]   # 10 días L-V × 40/5


def test_recordatorio_de_imputaciones_sigue_su_horario(ctx, monkeypatch):
    from app.core import timeutil
    from app.services.trabajos_de_fondo import personas_sin_imputar_hoy

    db = ctx
    sab = _persona(db, "sabadista2")
    _martes_a_sabado(db, sab)
    lun = _persona(db, "lunesista")
    sabado = LUNES + timedelta(days=5)

    monkeypatch.setattr(timeutil, "today", lambda: sabado)
    faltan = personas_sin_imputar_hoy(db, ORG)
    assert sab.email in faltan and lun.email not in faltan

    monkeypatch.setattr(timeutil, "today", lambda: LUNES)
    faltan = personas_sin_imputar_hoy(db, ORG)
    assert lun.email in faltan and sab.email not in faltan


# ── Avisos a la hora local de cada empresa ───────────────────────────────────

def _sesion_de_pruebas(monkeypatch, db):
    @contextmanager
    def _s():
        yield db
    monkeypatch.setattr("app.db.session.worker_db_session", _s)


def test_cada_empresa_recibe_el_aviso_a_su_hora_local(db, monkeypatch, seed_multitenant):
    from app.services.trabajos_de_fondo import organizaciones_a_su_hora

    _sesion_de_pruebas(monkeypatch, db)
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "Asia/Tokyo", "org-a-test")
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "America/New_York", "org-b-test")

    def a_las(h, m=0):
        return organizaciones_a_su_hora("NOTIFICATIONS_MISSING_IMPUTATIONS_TIME",
                                        ahora=datetime(2026, 12, 8, h, m, tzinfo=timezone.utc))

    assert a_las(9) == ["org-a-test"]          # Tokio 18:00, Nueva York 04:00
    assert a_las(9, 14) == ["org-a-test"]      # mismo cuarto de hora
    assert a_las(9, 15) == []
    assert a_las(23) == ["org-b-test"]         # Nueva York 18:00, Tokio 08:00
    # La hora es de cada empresa: Nueva York la pone a las 04:20 (tramo de las 04:15).
    set_runtime_value(db, "automations", "NOTIFICATIONS_MISSING_IMPUTATIONS_TIME", "4:20", "org-b-test")
    assert a_las(9, 15) == ["org-b-test"]
    assert a_las(9) == ["org-a-test"]


def test_la_tarea_de_alertas_solo_corre_en_la_empresa_que_toca(db, monkeypatch, seed_multitenant):
    import app.worker as w
    from app.core import timeutil

    _sesion_de_pruebas(monkeypatch, db)
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "Asia/Tokyo", "org-a-test")
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "America/New_York", "org-b-test")
    vistas = []
    monkeypatch.setattr("app.services.alert_service.run_alert_engine",
                        lambda s: vistas.append(s.info.get("organization_id")) or {})
    # 23:00 UTC: Tokio 08:00 del día siguiente (su hora de alertas), Nueva York 18:00.
    monkeypatch.setattr(timeutil, "utcnow", lambda: datetime(2026, 12, 8, 23, 0, tzinfo=timezone.utc))
    r = w.run_alert_engine()
    assert vistas == ["org-a-test"] and r["organizaciones"] == 1
    # 13:00 UTC: Nueva York 08:00.
    vistas.clear()
    monkeypatch.setattr(timeutil, "utcnow", lambda: datetime(2026, 12, 8, 13, 0, tzinfo=timezone.utc))
    w.run_alert_engine()
    assert vistas == ["org-b-test"]


def test_la_hora_se_valida_y_se_normaliza_al_guardar(db):
    from app.models.settings import AppSetting

    set_runtime_value(db, "automations", "NOTIFICATIONS_ALERTS_TIME", "7:05", ORG)
    fila = db.query(AppSetting).filter(AppSetting.key == "NOTIFICATIONS_ALERTS_TIME",
                                       AppSetting.organization_id == ORG).first()
    assert fila.value == "07:05"
    for malo in ("25:00", "08:60", "ocho", "8"):
        with pytest.raises(ValueError):
            set_runtime_value(db, "automations", "NOTIFICATIONS_ALERTS_TIME", malo, ORG)


def test_por_defecto_las_horas_son_las_de_antes():
    from app.core.config import settings
    assert (settings.NOTIFICATIONS_ALERTS_TIME, settings.NOTIFICATIONS_BUDGET_CAMPAIGN_TIME,
            settings.NOTIFICATIONS_MISSING_IMPUTATIONS_TIME,
            settings.NOTIFICATIONS_PERF_REMINDERS_TIME) == ("08:00", "08:30", "18:00", "09:00")


def test_en_festivo_de_la_empresa_no_hay_recordatorio_de_imputaciones(ctx, monkeypatch):
    from app.core import timeutil
    from app.services.trabajos_de_fondo import personas_sin_imputar_hoy

    db = ctx
    u = _persona(db, "festiva")
    monkeypatch.setattr(timeutil, "today", lambda: LUNES)
    assert u.email in personas_sin_imputar_hoy(db, ORG)
    db.add(Holiday(id=str(uuid.uuid4()), organization_id=ORG, name="Lunes festivo", date=LUNES))
    db.commit()
    assert u.email not in personas_sin_imputar_hoy(db, ORG)


def test_los_recordatorios_de_desempeno_van_a_la_hora_local(db, monkeypatch, seed_multitenant):
    import app.worker as w
    from app.core import timeutil

    _sesion_de_pruebas(monkeypatch, db)
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "Asia/Tokyo", "org-a-test")
    set_runtime_value(db, "locale", "DEFAULT_TIMEZONE", "America/New_York", "org-b-test")
    vistas = []
    monkeypatch.setattr("app.services.perf_reminder_service.send_pending_review_reminders",
                        lambda s, **kw: vistas.append(s.info.get("organization_id")) or {})
    # 00:00 UTC: Tokio 09:00 (su hora por defecto), Nueva York 19:00.
    monkeypatch.setattr(timeutil, "utcnow", lambda: datetime(2026, 12, 9, 0, 0, tzinfo=timezone.utc))
    w.run_perf_reminders()
    assert vistas == ["org-a-test"]
    vistas.clear()
    monkeypatch.setattr(timeutil, "utcnow", lambda: datetime(2026, 12, 9, 14, 0, tzinfo=timezone.utc))
    w.run_perf_reminders()   # Nueva York 09:00
    assert vistas == ["org-b-test"]
