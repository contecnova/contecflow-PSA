"""Revisión multitenant 2026-11b: lo que seguía cruzando empresas tras las dos auditorías.

Cada prueba fija un hallazgo medido (ver DOCS.md, «Aislamiento entre tenants»):

- un evento emitido por un superadmin disparaba los webhooks de SU empresa de
  ficha con los datos de otra;
- informes programados, OLAP, predictivo y ajustes generales enseñaban datos
  o totales de todas las empresas al administrador de una;
- el webhook CAB, el SMS sin empresa, Adobe Sign y la monitorización con token
  global trabajaban sin empresa (filas NULL, búsquedas entre empresas);
- claves de API y agente en segundo plano corrían en la empresa de ficha del
  dueño, no en la suya;
- `in:` en la búsqueda de colaboración saltaba las conversaciones visibles;
- cachés (analítica, token de conector) sin el ámbito correcto;
- trabajos de fondo sobre empresas desactivadas; purga que fallaba en silencio;
- la tercera capa del filtro y el export RGPD olvidaban los modelos `org_id`;
- «entrar como» no dejaba al suplantador en la auditoría.
"""
from __future__ import annotations

import io
import json
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.mfa import Organization
from app.models.user import User, UserOrganizationMembership
from tests.conftest import HASH_DE_PRUEBA


def _empresa_b(db, activa=True):
    db.add(Organization(id="org-b", name="Empresa B", slug="empresa-b", is_active=activa))
    db.flush()


def _sesion_de(db, org):
    """El mismo db del fixture, como si fuera una peticion de `org` (no superadmin)."""
    db.info["organization_id"], db.info["is_superadmin"] = org, False
    return db


# ── Eventos salientes ─────────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_evento_de_un_superadmin_va_a_la_empresa_del_proyecto(db):
    from app.core.events import _organizacion_del_evento
    from app.models.project import Project, ProjectStatus, ProjectType
    _empresa_b(db)
    db.add(Project(id="p-b", code="PB-1", name="De B", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id="org-b"))
    db.commit()
    superadmin = SimpleNamespace(id="s", is_superadmin=True, organization_id="1")
    db.info["organization_id"], db.info["is_superadmin"] = None, True
    assert _organizacion_del_evento(db, superadmin, None, "p-b") == "org-b"
    # Sin proyecto ni sesion: ninguna (fire_webhook no entrega), nunca la de ficha.
    assert _organizacion_del_evento(db, superadmin, None, None) is None


def test_el_evento_de_un_usuario_normal_sigue_en_su_empresa(db):
    from app.core.events import _organizacion_del_evento
    usuario = SimpleNamespace(id="u", is_superadmin=False, organization_id="1")
    db.info.pop("organization_id", None)
    assert _organizacion_del_evento(db, usuario, None, None) == "1"
    assert _organizacion_del_evento(db, usuario, "org-x", None) == "org-x"


# ── Informes, OLAP, predictivo, ajustes ──────────────────────────────────────

def test_EL_HALLAZGO_el_informe_programado_usa_su_empresa_y_sin_ella_no_se_envia(db):
    from app.services import scheduled_reports as sr
    db.info["organization_id"] = None
    informe = SimpleNamespace(organization_id="org-b", created_by="no-existe", name="R")
    assert sr._organizacion_del_informe(informe, db) == "org-b"
    huerfano = SimpleNamespace(organization_id=None, created_by="no-existe", name="R",
                               recipients="[]", recipients_extra=None)
    with pytest.raises(RuntimeError, match="no tiene organización"):
        sr._execute_report(huerfano, db)


def test_EL_HALLAZGO_la_carga_olap_no_ensena_totales_de_plataforma():
    from app.services.olap.etl import resumen_de_carga
    detalle = {"status": "ok", "since": "full", "seconds": 1.2, "organizations": 7, "users": 900, "tickets": 5}
    assert resumen_de_carga(detalle, plataforma=False) == {"status": "ok", "since": "full", "seconds": 1.2}
    assert resumen_de_carga(detalle, plataforma=True) == detalle
    assert resumen_de_carga({"error": "x"}, plataforma=False) == {"error": "x"}


def test_EL_HALLAZGO_el_resumen_predictivo_solo_ensena_la_empresa_propia():
    from app.api.v1.endpoints.predictive_observability import _ultima_evaluacion_para
    resumen = {"evaluated_at": "t", "organizations": 3, "itsm_retrained": 2, "bi_retrained": 1, "results": [
        {"organization_id": "1", "itsm": {"triggered": True}, "bi": {"triggered": False}},
        {"organization_id": "org-b", "itsm": {"triggered": True}, "bi": {"triggered": True}},
    ]}
    admin = SimpleNamespace(is_superadmin=False)
    visto = _ultima_evaluacion_para(resumen, admin, "1")
    assert [r["organization_id"] for r in visto["results"]] == ["1"]
    assert "organizations" not in visto and visto["itsm_retrained"] == 1 and visto["bi_retrained"] == 0
    assert _ultima_evaluacion_para(resumen, SimpleNamespace(is_superadmin=True), "1") == resumen


def test_EL_HALLAZGO_el_estado_interno_global_no_lo_ve_el_admin_de_una_empresa(db):
    from app.models.settings import AppSetting
    from app.services.settings_service import ajustes_generales_para
    db.add(AppSetting(key="predictive.retraining.last_eval", value='{"results": ["org-b"]}', organization_id=None))
    db.add(AppSetting(key="itsm.estado_propio", value="mio", organization_id="1"))
    db.commit()
    claves = {f["key"] for f in ajustes_generales_para(db, True, False)}
    assert "predictive.retraining.last_eval" not in claves
    assert "itsm.estado_propio" in claves  # lo de su empresa, si
    assert "predictive.retraining.last_eval" in {f["key"] for f in ajustes_generales_para(db, True, True)}


# ── Entradas sin usuario ─────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_webhook_cab_registra_en_la_empresa_del_disparador(db):
    from app.models.cab import WebhookTrigger, WebhookTriggerLog
    from app.services.cab_service.webhooks_entrantes import log_webhook_fire
    _empresa_b(db)
    db.add(WebhookTrigger(id="wt-b", name="B", slug="slug-b", secret="s", organization_id="org-b"))
    db.commit()
    trigger = db.get(WebhookTrigger, "wt-b")
    db.info["organization_id"], db.info["is_superadmin"] = None, None  # peticion sin usuario
    log_webhook_fire(trigger, "{}", "{}", db)
    assert db.query(WebhookTriggerLog).filter_by(trigger_id="wt-b").one().organization_id == "org-b"


def test_el_webhook_cab_de_una_empresa_desactivada_no_entra(db):
    from app.core.errores import ErrorDeDominio
    from app.models.cab import WebhookTrigger
    from app.services.cab_service.webhooks_entrantes import get_active_webhook_trigger_by_slug
    _empresa_b(db, activa=False)
    db.add(WebhookTrigger(id="wt-off", name="B", slug="slug-off", secret="s", organization_id="org-b"))
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        get_active_webhook_trigger_by_slug(db, "slug-off")
    assert e.value.status_code == 403


def test_EL_HALLAZGO_un_sms_sin_empresa_no_busca_el_telefono_en_todas(db, monkeypatch):
    from app.models.client_portal import ClientUser
    from app.services.service_desk import multichannel_service as ms
    from app.services.service_desk import ticket_creation_service as tcs
    _empresa_b(db)
    db.add(ClientUser(id="cu-b", full_name="Cliente B", email="cb@b.com", phone="+34600000000",
                      organization_id="org-b", is_active=True, hashed_password=HASH_DE_PRUEBA))
    db.commit()
    visto = {}

    def _falso(db_, **kw):
        visto.update(kw)
        return SimpleNamespace(id="t", number="T-1")

    monkeypatch.setattr(tcs, "build_channel_ticket", _falso)
    monkeypatch.setattr(ms, "send_sms", lambda *a, **k: None)
    db.info["organization_id"], db.info["is_superadmin"] = None, None
    ms.process_inbound_sms(db, from_phone="+34600000000", body="hola", to_phone="+000")
    assert visto["org_id"] is None and visto["requester_client"] is None


def test_EL_HALLAZGO_la_efirma_lee_las_credenciales_de_la_empresa_de_la_sesion(db):
    from app.models.settings import AppSetting
    from app.services.esign_service import _get_db_setting
    _empresa_b(db)
    clave = "esign.adobe_sign_base_url"  # no secreta: se compara en claro
    db.add(AppSetting(key=clave, value="https://de-la-1", organization_id="1"))
    db.add(AppSetting(key=clave, value="https://de-la-b", organization_id="org-b"))
    db.commit()
    db.info["organization_id"] = "org-b"
    assert _get_db_setting(db, clave) == "https://de-la-b"
    db.info["organization_id"] = None  # sin empresa: solo el global (no hay), nunca el de otra
    assert _get_db_setting(db, clave) is None


def test_EL_HALLAZGO_un_token_de_monitorizacion_global_con_varias_empresas_no_vale(db):
    from app.core.errores import ErrorDeDominio
    from app.services.service_desk.monitoring_ingest import _empresa_de_la_alerta
    assert _empresa_de_la_alerta(db, None) == "1"  # una sola empresa activa: esa
    _empresa_b(db)
    db.commit()
    with pytest.raises(ErrorDeDominio):
        _empresa_de_la_alerta(db, None)
    db.query(Organization).filter_by(id="org-b").update({"is_active": False})
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        _empresa_de_la_alerta(db, "org-b")
    assert e.value.status_code == 403


def test_los_proveedores_sso_de_una_empresa_desactivada_no_se_ofrecen(db):
    from app.models.enterprise import SSOConfig
    from app.services.auth_service.sso import get_active_sso_providers
    _empresa_b(db, activa=False)
    db.add(SSOConfig(provider="oidc", name="IdP de B", organization_id="org-b", is_active=True, is_deleted=False))
    db.add(SSOConfig(provider="oidc", name="IdP de 1", organization_id="1", is_active=True, is_deleted=False))
    db.commit()
    nombres = {p["name"] for p in get_active_sso_providers(db)}
    assert "IdP de 1" in nombres and "IdP de B" not in nombres


# ── Empresa activa fuera de la cookie ────────────────────────────────────────

def _miembro_de_b(db):
    _empresa_b(db)
    db.add(UserOrganizationMembership(user_id="pm-test-id", organization_id="org-b"))
    db.commit()


def _peticion(ruta="/api/v1/projects"):
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": ruta, "headers": [], "query_string": b"",
                    "scheme": "http", "server": ("test", 80)})


def test_EL_HALLAZGO_la_clave_de_api_trabaja_en_la_empresa_en_la_que_se_creo(db):
    from app.core.deps import _usuario_de_credencial_delegada
    _miembro_de_b(db)
    db.info.clear()
    usuario = _usuario_de_credencial_delegada(db, _peticion(), "pm-test-id", ["read"], "api_key", "org-b")
    assert db.info["organization_id"] == "org-b" and usuario.organization_id == "org-b"


def test_la_clave_de_api_de_una_empresa_que_ya_no_es_suya_no_vale(db):
    from fastapi import HTTPException
    from app.core.deps import _usuario_de_credencial_delegada
    _empresa_b(db)
    db.commit()
    db.info.clear()
    with pytest.raises(HTTPException) as e:
        _usuario_de_credencial_delegada(db, _peticion(), "pm-test-id", ["read"], "api_key", "org-b")
    assert e.value.status_code == 401


def test_el_formulario_publico_de_una_empresa_desactivada_no_se_sirve(db):
    from app.models.public_forms import PublicForm
    from app.services.public_forms_service import get_active_form_by_token
    _empresa_b(db, activa=False)
    db.add(PublicForm(name="F", token="tok-b", form_type="ticket", is_active=True, organization_id="org-b"))
    db.add(PublicForm(name="F", token="tok-1", form_type="ticket", is_active=True, organization_id="1"))
    db.commit()
    assert get_active_form_by_token(db, "tok-b") is None
    assert get_active_form_by_token(db, "tok-1") is not None


def test_el_login_del_portal_de_una_empresa_desactivada_no_emite_token(db):
    from app.core.errores import ErrorDeDominio
    from app.core.security import get_password_hash
    from app.models.client_portal import ClientUser
    from app.services.client_portal_service.clientes import client_login
    _empresa_b(db, activa=False)
    db.add(ClientUser(id="cu-off", full_name="C", email="c@off.com", is_active=True,
                      organization_id="org-b", hashed_password=get_password_hash("Clave-123!")))
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        client_login("c@off.com", "Clave-123!", db)
    assert e.value.status_code == 403


def test_EL_HALLAZGO_fijar_la_empresa_activa_fuera_de_http(db):
    from app.services.entrada_service import fijar_organizacion_activa
    _miembro_de_b(db)
    pm = db.get(User, "pm-test-id")
    assert fijar_organizacion_activa(db, pm, "org-b") == "org-b" and pm.organization_id == "org-b"
    dev = db.get(User, "dev-test-id")  # no es miembro de B: se queda en la suya
    assert fijar_organizacion_activa(db, dev, "org-b") == "1" and dev.organization_id == "1"


# ── Búsqueda de colaboración ─────────────────────────────────────────────────

def test_EL_HALLAZGO_in_no_salta_las_conversaciones_visibles(db, monkeypatch):
    from app.services.collaboration import _search as s
    resueltas = {"general": "c-ajena", "mia": "c1"}
    monkeypatch.setattr(s, "_resolve_in_target", lambda db_, v, org: resueltas.get(v))
    p = s.parse_query
    assert s.conversaciones_a_buscar(db, p("hola in:no-existe"), "1", ["c1"]) == ["c1"]
    assert s.conversaciones_a_buscar(db, p("hola in:general"), "1", ["c1"]) == []
    assert s.conversaciones_a_buscar(db, p("hola in:mia"), "1", ["c1", "c2"]) == ["c1"]
    assert s.conversaciones_a_buscar(db, p("hola"), "1", []) == []  # vacia = ninguna
    assert s.conversaciones_a_buscar(db, p("hola"), "1", None) is None  # uso interno: sin acotar


# ── Cachés ───────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_la_cache_de_analitica_separa_superadmin_y_empresa():
    from app.services.analytics_service import build_cache_key
    sa = SimpleNamespace(id="s", is_superadmin=True, organization_id="1")
    admin = SimpleNamespace(id="a", is_superadmin=False, organization_id="1")
    assert build_cache_key("m", sa, {}) != build_cache_key("m", admin, {})


def test_EL_HALLAZGO_el_token_de_conector_depende_del_secreto():
    from app.services.conectores.anfitrion import _clave_de_aplicacion
    producto = SimpleNamespace(clave="contecmind")
    a = {"base_url": "https://x", "client_id": "id", "client_secret": "bueno"}
    assert _clave_de_aplicacion(producto, a) != _clave_de_aplicacion(producto, {**a, "client_secret": "otro"})


# ── Trabajos de fondo ────────────────────────────────────────────────────────

def test_EL_HALLAZGO_una_lista_explicita_no_salta_las_empresas_desactivadas(monkeypatch):
    from app.db import session as _sesion
    from app.services import trabajos_de_fondo as tf

    class _Falsa:
        info: dict = {}

        def commit(self):
            pass

        def rollback(self):
            pass

    @contextmanager
    def _ws():
        yield _Falsa()

    monkeypatch.setattr(_sesion, "worker_db_session", _ws)
    monkeypatch.setattr(tf, "organizaciones_activas", lambda db: ["1"])
    vistas = []
    r = tf.en_cada_organizacion("t", lambda db, org: vistas.append(org), organizaciones=["1", "org-off"])
    assert vistas == ["1"] and r["organizaciones"] == 1


def test_EL_HALLAZGO_la_traza_de_timeout_va_en_la_empresa_de_la_solicitud():
    from app.services.approval_engine.timeouts import _log_timeout_audit_event
    filas = []
    req = SimpleNamespace(id="r", entity_type="expense", entity_id="e", organization_id="org-b")
    _log_timeout_audit_event(req, SimpleNamespace(step_order=1), "escalate", datetime.now(timezone.utc),
                             SimpleNamespace(add=filas.append))
    assert filas and filas[0].organization_id == "org-b"


def test_EL_HALLAZGO_la_purga_que_falla_no_queda_en_success(db, monkeypatch):
    from app.services import baja_de_empresa_service as baja
    from app.services.trabajos_de_fondo import FalloEnOrganizaciones
    _empresa_b(db)
    db.query(Organization).filter_by(id="org-b").update(
        {"deletion_purge_after": datetime.now(timezone.utc) - timedelta(days=1)})
    db.commit()

    def _revienta(db_, org):
        raise RuntimeError("fk")

    monkeypatch.setattr(baja, "purgar", _revienta)
    with pytest.raises(FalloEnOrganizaciones):
        baja.purgar_caducadas(db)


# ── Modelos `org_id`: tercera capa, export y únicos ──────────────────────────

def test_EL_HALLAZGO_la_tercera_capa_filtra_tambien_los_modelos_org_id():
    from app.db.session import _iter_org_id_models
    nombres = {m.__name__ for m in _iter_org_id_models()}
    assert {"ABACPolicy", "SecurityEvent", "AIGuardrailPolicyModel"} <= nombres and len(nombres) >= 11


def test_la_tercera_capa_esconde_las_filas_org_id_de_otra_empresa(db):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models.abac import ABACPolicy
    _empresa_b(db)
    db.add(ABACPolicy(id="ap-b", org_id="org-b", policy_name="de B", rules="{}"))
    db.add(ABACPolicy(id="ap-1", org_id="1", policy_name="de 1", rules="{}"))
    db.commit()
    _sesion_de(db, "1")
    # `Session.execute` sin el override de TenantSession: solo actua el escuchador.
    nombres = {p.policy_name for p in Session.execute(db, select(ABACPolicy)).scalars()}
    assert nombres == {"de 1"}


def test_EL_HALLAZGO_el_export_rgpd_lleva_las_tablas_org_id(db):
    from app.models.abac import ABACPolicy
    from app.services.baja_de_empresa_service import exportar
    db.add(ABACPolicy(id="ap-mia", org_id="1", policy_name="mia", rules="{}"))
    db.commit()
    with zipfile.ZipFile(io.BytesIO(exportar(db, "1"))) as zf:
        filas = json.loads(zf.read("abac_policies.json"))
    assert [f["policy_name"] for f in filas] == ["mia"]


def test_los_unicos_de_las_tablas_org_id_incluyen_la_empresa():
    import app.models  # noqa: F401
    from app.db.base import Base
    for tabla in Base.metadata.sorted_tables:
        if "organization_id" in tabla.c or "org_id" not in tabla.c:
            continue
        grupos = [(c.name,) for c in tabla.c if c.unique and not c.primary_key]
        grupos += [tuple(c.name for c in i.columns) for i in tabla.indexes if i.unique]
        grupos += [tuple(c.name for c in k.columns) for k in tabla.constraints
                   if k.__class__.__name__ == "UniqueConstraint"]
        assert all("org_id" in g for g in grupos), (tabla.name, grupos)


# ── «Entrar como» ────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_lo_hecho_entrando_como_lleva_al_suplantador(db):
    from app.services.audit import audit_log
    usuario = db.get(User, "pm-test-id")
    db.info["suplantado_por"] = "superadmin-real"
    entrada = audit_log(db, usuario, "UPDATE", "projects", "p1", metadata={"campo": "x"})
    assert json.loads(entrada.metadata_) == {"campo": "x", "impersonated_by": "superadmin-real"}
    db.info.pop("suplantado_por")
    assert audit_log(db, usuario, "UPDATE", "projects", "p1").metadata_ is None

