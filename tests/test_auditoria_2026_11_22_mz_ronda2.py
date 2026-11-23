"""Auditoria 2026-11-22, informe 03 (servicios m-z), segunda ronda: medios y
bajos de r-z, modelos y esquemas (los de m-p estan en
`test_auditoria_2026_11_22_mz_ronda2_mp.py`).

Un test por arreglo, lo minimo para que no vuelva.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.core.errores import ErrorDeDominio

ORG = "1"
RAIZ = Path(__file__).resolve().parent.parent


def _admin(db):
    from app.models.user import User
    return db.query(User).filter(User.id == "admin-test-id").first()


def _usuario(db, uid):
    from app.models.user import User
    return db.query(User).filter(User.id == uid).first()


# ── SCIM: token por empresa, busqueda por hash y bulk con savepoint ─────────

def test_scim_token_por_empresa_se_genera_audita_y_solo_vale_para_su_empresa(db):
    from app.models.enterprise import AuditLog
    from app.services import scim_service as scim
    token = scim.rotar_token_scim(db, ORG, "admin-test-id")
    assert scim.require_scim_token(db, f"Bearer {token}", ORG).id == ORG
    with pytest.raises(ErrorDeDominio) as e:
        scim.require_scim_token(db, f"Bearer {token}", "otra-empresa")
    assert e.value.status_code == 403
    assert db.query(AuditLog).filter(AuditLog.action == "SCIM_TOKEN_ROTATE").count() == 1


def test_scim_bulk_una_operacion_fallida_no_deja_cambios_a_medias(db):
    from app.models.user import User
    from app.services import scim_service as scim
    ops = [
        {"method": "POST", "path": "/Users", "bulkId": "a",
         "data": {"userName": "bulk1", "emails": [{"value": "bulk1@ejemplo.com"}]}},
        {"method": "PATCH", "path": "/Users/no-existe", "bulkId": "b", "data": {}},
    ]
    respuestas = scim.process_bulk_operations(ORG, ops, None, db)
    assert [r["status"] for r in respuestas] == ["201", "400"]
    assert db.query(User).filter(User.username == "bulk1").count() == 1


# ── STT: la voz ya no cuesta 0 ──────────────────────────────────────────────

def test_stt_coste_estimado_por_duracion_o_por_tamano():
    from app.services.stt import coste_estimado_usd, BYTES_POR_SEGUNDO_ESTIMADOS
    un_minuto = b"x" * (BYTES_POR_SEGUNDO_ESTIMADOS * 60)
    assert coste_estimado_usd(un_minuto) == pytest.approx(0.006)
    assert coste_estimado_usd(b"", SimpleNamespace(duration_ms=120_000)) == pytest.approx(0.012)


# ── Tarifas: excepciones de tablas inactivas y tarifa 0 ─────────────────────

def test_tarifas_las_excepciones_de_una_tabla_inactiva_no_cuentan(db):
    from app.models.advanced_config import RateOverride, RateTable
    from app.models.project import Project
    from app.services.rate_card_service import _tarifa_por_excepcion
    db.add(Project(id="p-rate", organization_id=ORG, code="PRJ-RT", name="P", project_type="consulting"))
    tabla = RateTable(id="t-rate", organization_id=ORG, name="T", is_active=False)
    db.add(tabla)
    db.flush()
    db.add(RateOverride(organization_id=ORG, table_id=tabla.id, project_id="p-rate", role_label="Dev", billing_rate=99))
    db.commit()
    assert _tarifa_por_excepcion(db, "Dev", None, "p-rate", "2026-11-23") is None
    tabla.is_active = True
    db.commit()
    assert _tarifa_por_excepcion(db, "Dev", None, "p-rate", "2026-11-23")["billing_rate"] == 99


def test_tarifas_una_tarifa_cero_pactada_no_cae_a_la_de_respaldo(db, monkeypatch):
    from app.services import rate_card_service as rc
    monkeypatch.setattr(rc, "get_effective_rate", lambda *a, **k: {"billing_rate": 0, "source": "override_project_id"})
    usuario = SimpleNamespace(job_title="Dev", hourly_rate=50)
    proyecto = SimpleNamespace(id="p", client_id=None, organization_id=ORG, billing_rate=80)
    assert rc.tarifa_de_facturacion(db, usuario, proyecto, date(2026, 11, 23)) == 0.0


# ── traffic_control: no confirma la sesion del llamante ─────────────────────

def test_cuota_no_confirma_el_trabajo_pendiente_del_llamante(db):
    from app.models.settings import AppSetting
    from app.services.traffic_control_service import consume_quota
    db.add(AppSetting(key="pendiente.del.llamante", value="x", organization_id=ORG))
    r = consume_quota(db, scope="t", tenant_id=ORG, subject="s", limit=5)
    assert r["allowed"] and r["count"] == 1
    db.rollback()
    assert db.query(AppSetting).filter(AppSetting.key == "pendiente.del.llamante").count() == 0
    assert db.query(AppSetting).filter(AppSetting.key.like("traffic.ctrl.t.%")).count() == 1


# ── user_service: responsable, auditoria, correo, roles ─────────────────────

def test_usuarios_manager_id_por_patch_se_valida(db):
    from app.schemas.users import UserUpdate
    from app.services.user_service import update_user_record
    with pytest.raises(ErrorDeDominio) as e:
        update_user_record("pm-test-id", UserUpdate(manager_id="no-existe"), _admin(db), db)
    assert e.value.status_code == 404
    with pytest.raises(ErrorDeDominio) as e:
        update_user_record("pm-test-id", UserUpdate(manager_id="pm-test-id"), _admin(db), db)
    assert e.value.code == "jerarquia_ciclica"


def test_usuarios_cambiar_rol_o_tarifa_deja_audit_log(db):
    import json
    from app.models.enterprise import AuditLog
    from app.schemas.users import UserUpdate
    from app.services.user_service import update_user_record
    update_user_record("pm-test-id", UserUpdate(role="team_lead", hourly_rate=55), _admin(db), db)
    filas = db.query(AuditLog).filter(AuditLog.resource_id == "pm-test-id").all()
    assert any("campos_sensibles" in (f.metadata_ or "") for f in filas)
    nuevos = json.loads([f for f in filas if "campos_sensibles" in (f.metadata_ or "")][0].new_values)
    assert nuevos["role"] == "team_lead"


def test_usuarios_el_propio_correo_solo_lo_cambia_un_administrador(db):
    from app.services.user_service import update_self_profile
    pm = _usuario(db, "pm-test-id")
    with pytest.raises(ErrorDeDominio) as e:
        update_self_profile(pm, {"email": "otro@ejemplo.com"}, db)
    assert e.value.code == "correo_solo_admin"
    update_self_profile(pm, {"email": pm.email.upper(), "first_name": "P"}, db)  # mismo correo: vale


def test_usuarios_roles_que_ven_tarifas_es_una_constante():
    from app.services.user_service import ROLES_QUE_VEN_TARIFAS
    assert ROLES_QUE_VEN_TARIFAS == ("admin", "hr")


# ── session_security: cabeceras de geo solo de un proxy de confianza ────────

def test_geo_las_cabeceras_del_cliente_no_cuentan():
    from app.services.session_security import _lookup_ip_intel
    req = SimpleNamespace(headers={"cf-ipcountry": "KP", "x-asn": "AS1"}, client=SimpleNamespace(host="8.8.8.8"))
    out = _lookup_ip_intel(None, req)
    assert out["country_code"] is None and out["ip_asn"] is None


# ── Informes programados: hora local, reenvio y HTML ────────────────────────

def test_informes_programados_la_hora_es_la_local_de_la_empresa():
    from app.services.scheduled_reports import _get_next_run
    madrid = ZoneInfo("Europe/Madrid")
    desde = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)      # 07:00 en Madrid
    sig = _get_next_run("daily", desde, send_hour=8, zona=madrid)
    assert sig == datetime(2026, 11, 23, 7, 0, tzinfo=timezone.utc)  # 08:00 en Madrid


def test_informes_programados_el_nombre_va_escapado():
    from app.services.scheduled_reports import _build_html_body
    html = _build_html_body("<script>x</script>", "custom", "daily", datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_informes_programados_un_envio_parcial_no_se_reintenta_entero(db, monkeypatch):
    from app.services import scheduled_reports as sr
    informe = SimpleNamespace(name="R", frequency="daily", send_hour=8, day_of_week=None, day_of_month=None,
                              next_run_at=None, last_run_at=None, last_status=None, last_error=None)

    class _Q:
        def filter(self, *a, **k):
            return self

        def all(self):
            return [informe]

    monkeypatch.setattr(db, "query", lambda *a, **k: _Q())
    monkeypatch.setattr(sr, "_execute_report", lambda r, d: (_ for _ in ()).throw(sr.EnvioParcial("1 de 2")))
    monkeypatch.setattr(sr, "_zona_del_informe", lambda r, d: None)
    monkeypatch.setattr(db, "commit", lambda: None)
    ahora = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
    assert sr.ejecutar_informes_vencidos(db, ahora) == {"enviados": 0, "fallidos": 1}
    assert informe.next_run_at > ahora and informe.last_status == "error"


def test_resumen_de_informes_sin_contexto_no_cuenta_otras_empresas():
    from app.services.scheduled_reports_compat import _RESUMEN_VACIO
    fuente = (RAIZ / "app/services/scheduled_reports_compat.py").read_text(encoding="utf-8")
    assert 'db.info.get("is_superadmin", True)' not in fuente
    assert isinstance(_RESUMEN_VACIO, dict)


# ── PDF BI: si OLAP falla, error y no PDF vacio ─────────────────────────────

def test_pdf_bi_falla_con_codigo_si_olap_no_responde(monkeypatch):
    from app.services import report_pdf_service as rps
    from app.services.olap import query_engine
    monkeypatch.setattr(query_engine, "get_kpi_summary", lambda org: (_ for _ in ()).throw(RuntimeError("duckdb")))
    with pytest.raises(ErrorDeDominio) as e:
        rps._fetch_executive_data(ORG)
    assert (e.value.status_code, e.value.code) == (503, "informe_bi_sin_datos")


# ── Slack: sin token ni webhook no es un exito ──────────────────────────────

def test_slack_sin_configurar_no_simula_exito():
    from app.services.slack_service import send_slack_message
    cfg = SimpleNamespace(platform="slack", bot_token=None, webhook_url=None, default_channel=None, organization_id=None)
    assert send_slack_message(cfg, "hola") == (False, "slack_sin_configurar")


# ── S3: sin recarga sobre el objeto global ──────────────────────────────────

def test_s3_no_hay_recarga_que_mute_el_almacen_global():
    from app.services.s3_service import S3Service
    assert not hasattr(S3Service, "reload_from_db")


# ── next_ci_number por empresa ──────────────────────────────────────────────

def test_ci_la_numeracion_es_por_empresa(db):
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.models.service_desk._enums import CIType
    from app.services.sla_service import next_ci_number
    db.add(ConfigurationItem(organization_id=ORG, code="CI-0005", name="srv", ci_type=CIType.server))
    db.commit()
    assert next_ci_number(db, ORG) == "CI-0006"
    assert next_ci_number(db, "otra-empresa") == "CI-0001"


# ── raci: capacidad 0 ───────────────────────────────────────────────────────

def test_agotamiento_con_capacidad_cero_no_divide_por_cero(db, monkeypatch):
    from app.services import raci_service
    monkeypatch.setattr(raci_service, "capacidad_semanal", lambda db, u: 0)
    semanas = raci_service._semanas_de_carga(_usuario(db, "dev-test-id"), db, date(2026, 11, 23))
    assert all(s["load_pct"] == 0.0 for s in semanas)


# ── Tareas: asignacion masiva validada ──────────────────────────────────────

def test_tareas_masiva_rechaza_prioridad_y_asignado_invalidos(db):
    from app.services.tasks.bulk import bulk_update_tasks
    with pytest.raises(ErrorDeDominio) as e:
        bulk_update_tasks([], {"priority": "urgentisima"}, _admin(db), db)
    assert e.value.code == "valor_no_valido"
    with pytest.raises(ErrorDeDominio) as e:
        bulk_update_tasks([], {"assignee_id": "no-existe"}, _admin(db), db)
    assert e.value.status_code == 422


# ── SOC: umbrales y sesion propia ───────────────────────────────────────────

def test_soc_umbrales_configurables_y_sin_constantes_muertas(db):
    import app.services.security_observability as so
    assert so.umbral_soc(db, ORG, "SOC_CRED_STUFFING_USUARIOS") == 3
    assert not hasattr(so, "MASS_EXPORT_THRESHOLD") and not hasattr(so, "SESSION_CONCURRENT_LIMIT")


def test_soc_el_evento_no_confirma_la_sesion_del_llamante_y_sobrevive_al_rollback(db):
    from app.models.security_observability import SecurityEvent
    from app.models.settings import AppSetting
    from app.services.security_observability import SecurityEventService
    db.add(AppSetting(key="pendiente.soc", value="x", organization_id=ORG))
    SecurityEventService(db, ORG).login_failed(None, "203.0.113.9", "ua")
    db.rollback()
    assert db.query(AppSetting).filter(AppSetting.key == "pendiente.soc").count() == 0
    assert db.query(SecurityEvent).filter(SecurityEvent.ip_address == "203.0.113.9").count() == 1


# ── Bajos ───────────────────────────────────────────────────────────────────

def test_auditoria_de_ajustes_no_guarda_sha256_sin_sal():
    from app.services.settings_audit_service import _hash
    assert _hash("secreto") != hashlib.sha256(b"secreto").hexdigest()
    assert _hash("secreto") == _hash("secreto") and len(_hash("secreto")) == 64


def test_tarea_de_imputaciones_no_devuelve_correos(db):
    from app.services.trabajos_de_fondo import imputaciones_pendientes_de_hoy
    assert set(imputaciones_pendientes_de_hoy(db, ORG)) == {"missing_today"}


def test_bajos_sin_cadenas_fijas_ni_nombre_de_tercero():
    from app.models.project import FACTURACION_RETAINER
    assert FACTURACION_RETAINER == "recurring_retainer"
    fondo = (RAIZ / "app/services/trabajos_de_fondo.py").read_text(encoding="utf-8")
    assert "%B" not in fondo and '"recurring_retainer"' not in fondo
    assert "Ficosa" not in (RAIZ / "app/services/semantic_classifier.py").read_text(encoding="utf-8")


def test_token_del_bot_de_teams_bajo_cerrojo():
    from app.services import teams_bot
    assert teams_bot._TOKEN_LOCK is not None


# ── Esquemas: avatar_url ────────────────────────────────────────────────────

def test_esquema_avatar_url_solo_http_o_ruta_propia():
    from pydantic import ValidationError
    from app.schemas.users import UserSelfUpdate, UserUpdate
    assert UserUpdate(avatar_url="https://cdn.ejemplo.com/a.png").avatar_url
    assert UserSelfUpdate(avatar_url="/uploads/a.png").avatar_url == "/uploads/a.png"
    for malo in ("javascript:alert(1)", "data:image/png;base64,AA", "//otro.host/a.png"):
        with pytest.raises(ValidationError):
            UserSelfUpdate(avatar_url=malo)


# ── A-MOD1 / A-MOD2: deteccion sin migracion (lista medida que solo encoge) ──

_DINERO = r"(amount|price|cost|total|budget|revenue|margin|fee|salary|_rate$|^rate$|subtotal|tax_amount|balance|paid|invoiced)"
_NO_DINERO = r"(_pct$|percent|ratio|score|hours|probability|confidence|weight|factor|escalation)"


def _medir_modelos():
    import re
    from sqlalchemy import Float
    from app.db.base import Base
    import app.models  # noqa: F401  (registra todas las tablas)
    fk, flt = set(), set()
    for nombre, tabla in Base.metadata.tables.items():
        for col in tabla.columns:
            if any(not f.ondelete for f in col.foreign_keys):
                fk.add(f"{nombre}.{col.name}")
            if isinstance(col.type, Float) and re.search(_DINERO, col.name) and not re.search(_NO_DINERO, col.name):
                flt.add(f"{nombre}.{col.name}")
    return fk, flt


def test_a_mod1_y_a_mod2_ninguna_fk_sin_ondelete_ni_dinero_float_nuevos():
    """Una FK nueva sin `ondelete` o una columna de dinero nueva en `Float` falla.
    Las existentes (medidas el 23-11-2026) estan en `tests/datos_auditoria_mz_modelos.json`
    y se van quitando segun las migra la migracion de A-MOD1/A-MOD2."""
    import json
    permitidas = json.loads((RAIZ / "tests/datos_auditoria_mz_modelos.json").read_text(encoding="utf-8"))
    fk, flt = _medir_modelos()
    assert not (fk - set(permitidas["fk_sin_ondelete"])), "FK nuevas sin ondelete"
    assert not (flt - set(permitidas["dinero_en_float"])), "dinero nuevo en Float: usar Money/Rate"
