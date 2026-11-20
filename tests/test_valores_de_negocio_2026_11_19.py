"""Valores de negocio que eran fijos, ahora ajustes por empresa (19-11-2026).

Medido antes:
- la rampa canaria 1/5/25/50/100 y sus 30/45/60 min estaban escritos en
  `ChangeRolloutPanel.tsx`;
- los 24 meses de retención propuestos del chat, en `ChatAdminPage.tsx` y en
  `RetentionPolicyIn`; una política de 0 meses ponía el corte en «ahora» y el
  barrido borraba todo el chat;
- el máximo de 60 días de vacaciones asignados era sólo el `max="60"` de la
  pantalla: la API aceptaba 500;
- los plazos de recordatorios y de ciclos atascados de evaluaciones eran
  constantes de `perf_reminder_service`.

Aquí: validación al guardar, lectura por empresa, valor por defecto igual al de
antes, `/settings/org-defaults` → `propuestas` y la auditoría de cada cambio.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.codigos_de_error import ErrorConCodigo
from app.models.settings import AppSetting
from app.services import settings_service
from app.services.settings_service import valores_de_negocio as vn
from tests.conftest import auth


@pytest.fixture(autouse=True)
def _cache_limpia():
    settings_service.invalidate_cache()
    yield
    settings_service.invalidate_cache()


# ── Declaración ──────────────────────────────────────────────────────────────

CLAVES = {
    "service_desk": ["CHANGE_CANARY_RAMP_PCT", "CHANGE_CANARY_FIRST_MINUTES", "CHANGE_CANARY_STEP_MINUTES",
                     "CHANGE_CANARY_LAST_MINUTES"],
    "audit": ["CHAT_RETENTION_PROPOSED_MONTHS"],
    "locale": ["VACATION_MAX_DAYS_ENTITLED"],
    "automations": ["PERF_REMINDER_WINDOW_DAYS", "PERF_REMINDER_UNDATED_CYCLE_DAYS", "PERF_STALLED_CYCLE_DAYS",
                    "PERF_STALLED_COMPLETION_PCT"],
}


def test_cada_valor_esta_en_su_grupo_con_el_defecto_de_antes():
    from app.core.config import settings
    for grupo, claves in CLAVES.items():
        del_grupo = {k for k, _, _ in settings_service.RUNTIME_FLAG_GROUPS[grupo]}
        assert set(claves) <= del_grupo, grupo
    assert settings.CHANGE_CANARY_RAMP_PCT == "1,5,25,50,100"
    assert (settings.CHANGE_CANARY_FIRST_MINUTES, settings.CHANGE_CANARY_STEP_MINUTES,
            settings.CHANGE_CANARY_LAST_MINUTES) == (30, 45, 60)
    assert settings.CHAT_RETENTION_PROPOSED_MONTHS == 24
    assert settings.VACATION_MAX_DAYS_ENTITLED == 60
    assert (settings.PERF_REMINDER_WINDOW_DAYS, settings.PERF_REMINDER_UNDATED_CYCLE_DAYS,
            settings.PERF_STALLED_CYCLE_DAYS, settings.PERF_STALLED_COMPLETION_PCT) == (7, 30, 45, 50.0)


def test_ninguno_es_de_plataforma():
    claves = {k for v in CLAVES.values() for k in v}
    assert not claves & settings_service.AJUSTES_DE_PLATAFORMA


# ── Rampa canaria ────────────────────────────────────────────────────────────

def test_rampa_se_normaliza():
    assert vn.parsear_rampa(" 1, 5,25 ,50,100") == [1, 5, 25, 50, 100]
    assert vn.parsear_rampa("10,100") == [10, 100]


@pytest.mark.parametrize("mala", ["", "100", "1,5,25", "5,1,100", "1,1,100", "0,50,100", "1,50,101",
                                  "a,b,100", ",".join(str(i) for i in range(1, 11)) + ",100"])
def test_rampa_no_valida(mala):
    with pytest.raises(ErrorConCodigo) as e:
        vn.parsear_rampa(mala)
    assert e.value.codigo == "ajuste_valor_no_valido"


def test_rampa_se_guarda_normalizada_y_se_lee_por_empresa(db):
    settings_service.set_runtime_value(db, "service_desk", "CHANGE_CANARY_RAMP_PCT", "10, 50,100", "1")
    assert vn.rampa_canaria(db, "1") == [10, 50, 100]
    fila = db.query(AppSetting).filter(AppSetting.key == "CHANGE_CANARY_RAMP_PCT",
                                       AppSetting.organization_id == "1").one()
    assert fila.value == "10,50,100"
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "service_desk", "CHANGE_CANARY_RAMP_PCT", "50,10,100", "1")


def test_rampa_escrita_a_mano_mal_cae_a_la_de_por_defecto(db):
    db.add(AppSetting(key="CHANGE_CANARY_RAMP_PCT", value="basura", organization_id="1"))
    db.commit()
    assert vn.rampa_canaria(db, "1") == [1, 5, 25, 50, 100]


@pytest.mark.parametrize("valor", [4, 0, 1441])
def test_minutos_fuera_de_rango(db, valor):
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "service_desk", "CHANGE_CANARY_FIRST_MINUTES", valor, "1")


def test_minutos_por_empresa(db):
    assert vn.minutos_canarios(db, "1") == {"first": 30, "step": 45, "last": 60}
    settings_service.set_runtime_value(db, "service_desk", "CHANGE_CANARY_STEP_MINUTES", 20, "1")
    assert vn.minutos_canarios(db, "1")["step"] == 20


# ── Retención propuesta del chat ─────────────────────────────────────────────

def test_retencion_propuesta_en_rango_y_dentro_del_tope(db):
    assert vn.retencion_propuesta_del_chat(db, "1") == 24
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "audit", "CHAT_RETENTION_PROPOSED_MONTHS", 0, "1")
    # Tope del chat de la empresa por defecto: 60 meses.
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "audit", "CHAT_RETENTION_PROPOSED_MONTHS", 61, "1")
    settings_service.set_runtime_value(db, "audit", "CHAT_RETENTION_PROPOSED_MONTHS", 36, "1")
    assert vn.retencion_propuesta_del_chat(db, "1") == 36


def test_retencion_propuesta_respeta_el_minimo_de_retencion(db):
    settings_service.set_runtime_value(db, "audit", "RETENTION_MIN_DAYS", 90, "1")
    assert vn.meses_minimos_de_retencion(db, "1") == 3
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "audit", "CHAT_RETENTION_PROPOSED_MONTHS", 2, "1")


def test_retencion_propuesta_no_pasa_del_tope_que_baje_despues(db):
    from app.services.collaboration.compliance import set_retention_settings
    set_retention_settings(db, "1", {"default_months": 6, "max_months": 12})
    assert vn.retencion_propuesta_del_chat(db, "1") == 12


def test_EL_HALLAZGO_politica_del_chat_sin_meses_usa_la_propuesta_y_cero_no_vale(client, admin_token, db):
    settings_service.set_runtime_value(db, "audit", "CHAT_RETENTION_PROPOSED_MONTHS", 18, "1")
    r = client.post("/api/v1/collaboration/retention", headers=auth(admin_token),
                    json={"name": "Sin meses", "scope": "workspace", "apply_to": "all"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["retention_months"] == 18
    r = client.post("/api/v1/collaboration/retention", headers=auth(admin_token),
                    json={"name": "Cero", "scope": "workspace", "apply_to": "all", "retention_months": 0})
    assert r.status_code == 422, r.text
    assert r.json().get("code") == "retencion_minimo_dias"


# ── Máximo de vacaciones ─────────────────────────────────────────────────────

def test_maximo_de_vacaciones_y_dias_por_defecto_quedan_en_orden(db):
    assert vn.maximo_de_dias_de_vacaciones(db, "1") == 60
    settings_service.set_runtime_value(db, "locale", "DEFAULT_VACATION_DAYS_PER_YEAR", 25, "1")
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "locale", "VACATION_MAX_DAYS_ENTITLED", 20, "1")
    settings_service.set_runtime_value(db, "locale", "VACATION_MAX_DAYS_ENTITLED", 30, "1")
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "locale", "DEFAULT_VACATION_DAYS_PER_YEAR", 31, "1")
    with pytest.raises(ErrorConCodigo):
        settings_service.set_runtime_value(db, "locale", "VACATION_MAX_DAYS_ENTITLED", 400, "1")


def test_EL_HALLAZGO_el_servidor_no_asigna_mas_del_maximo(db):
    from app.core.errores import ErrorDeDominio
    from app.models.user import User
    from app.services.advanced_config_service.tarifas_y_vacaciones import update_vacation_balance
    persona = db.query(User).filter(User.organization_id == "1").first()
    with pytest.raises(ErrorDeDominio):
        update_vacation_balance(persona.id, 2031, 61, db)
    assert update_vacation_balance(persona.id, 2031, 60, db) == {"ok": True}
    settings_service.set_runtime_value(db, "locale", "VACATION_MAX_DAYS_ENTITLED", 30, "1")
    with pytest.raises(ErrorDeDominio):
        update_vacation_balance(persona.id, 2031, 31, db)
    with pytest.raises(ErrorDeDominio):
        update_vacation_balance(persona.id, 2031, -1, db)


# ── Evaluaciones de desempeño ────────────────────────────────────────────────

def test_plazos_de_evaluaciones_por_empresa_y_validados(db):
    assert vn.plazos_de_evaluaciones(db, "1") == {"ventana_dias": 7, "sin_cierre_dias": 30,
                                                  "atascado_dias": 45, "atascado_pct": 50.0}
    settings_service.set_runtime_value(db, "automations", "PERF_REMINDER_WINDOW_DAYS", 14, "1")
    settings_service.set_runtime_value(db, "automations", "PERF_STALLED_COMPLETION_PCT", 80, "1")
    plazos = vn.plazos_de_evaluaciones(db, "1")
    assert (plazos["ventana_dias"], plazos["atascado_pct"]) == (14, 80.0)
    for clave, malo in (("PERF_REMINDER_WINDOW_DAYS", 0), ("PERF_REMINDER_UNDATED_CYCLE_DAYS", 366),
                        ("PERF_STALLED_CYCLE_DAYS", 0), ("PERF_STALLED_COMPLETION_PCT", 101)):
        with pytest.raises(ErrorConCodigo):
            settings_service.set_runtime_value(db, "automations", clave, malo, "1")


def test_la_ventana_de_recordatorios_es_la_de_la_empresa_del_ciclo(db):
    from app.models.performance import ReviewCycle, ReviewCycleStatus
    from app.services.perf_reminder_service import send_pending_review_reminders
    hoy = date(2031, 3, 3)
    ciclo = ReviewCycle(name="Ciclo 10 días", status=ReviewCycleStatus.active, organization_id="1",
                        start_date=hoy - timedelta(days=30), end_date=hoy + timedelta(days=10),
                        created_at=datetime.now(timezone.utc))
    db.add(ciclo)
    db.commit()
    antes = send_pending_review_reminders(db, today=hoy)["cycles_processed"]
    settings_service.set_runtime_value(db, "automations", "PERF_REMINDER_WINDOW_DAYS", 14, "1")
    assert send_pending_review_reminders(db, today=hoy)["cycles_processed"] == antes + 1


# ── Lectura en pantalla y auditoría ──────────────────────────────────────────

def test_org_defaults_trae_las_propuestas(client, admin_token):
    r = client.get("/api/v1/settings/org-defaults", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    propuestas = r.json()["data"]["propuestas"]
    assert propuestas == {
        "change_canary_ramp_pct": [1, 5, 25, 50, 100],
        "change_canary_minutes": {"first": 30, "step": 45, "last": 60},
        "chat_retention_proposed_months": 24,
        "vacation_max_days_entitled": 60,
    }


def test_cada_cambio_queda_auditado(db, monkeypatch):
    vistos = []
    import app.services.settings_audit_service as auditoria
    monkeypatch.setattr(auditoria, "record_change", lambda db, **kw: vistos.append(kw))
    settings_service.set_runtime_value(db, "service_desk", "CHANGE_CANARY_RAMP_PCT", "5,100", "1", actor_id="u1")
    assert vistos and vistos[-1]["key"] == "CHANGE_CANARY_RAMP_PCT"
    assert vistos[-1]["new_value"] == "5,100" and vistos[-1]["scope"] == "runtime"
