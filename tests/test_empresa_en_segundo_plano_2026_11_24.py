"""Caminos sin empresa en la sesión tras la migración 208 (`organization_id` obligatorio).

24-11-2026. Docs: docs/seguridad/empresa_obligatoria.md §6. Vigila los caminos
de fondo y anónimos que creaban filas sin empresa deducible:

- superadmin sin empresa elegida → 409 `empresa_requerida` (no un 500);
- trabajo sin empresa → sigue cortando con `fila_sin_empresa`;
- correo y SMS entrantes sin empresa destinataria → se ignoran, sin ticket;
- registros accesorios (uso de IA, acciones de IA, caché de traducción,
  configuración semántica) sin empresa → no se guardan ni rompen a quien llama;
- reglas SoD y huecos de cupo (inserts que se saltan el sellado) sin empresa;
- el planificador de mensajes de colaboración y el agente de la CMDB trabajan
  en la empresa de cada fila.
"""
import inspect
from contextlib import contextmanager

import pytest


_CLAVES = ("organization_id", "is_superadmin", "current_user", "contexto_de_sistema")


@contextmanager
def _sin_empresa(db, **extra):
    """La sesión sin empresa, como un trabajo de fondo (contexto de sistema declarado,
    igual que `TareaDeSistema`); el sellado intenta deducir la empresa del padre."""
    previo = {k: db.info.pop(k, None) for k in _CLAVES}
    db.info["contexto_de_sistema"] = "prueba: trabajo sin empresa"
    db.info.update(extra)
    try:
        yield db
    finally:
        for k in _CLAVES:
            db.info.pop(k, None)
        db.info.update({k: v for k, v in previo.items() if v is not None})


def _segunda_empresa(db):
    from app.models.mfa import Organization
    db.add(Organization(id="org-b-208", name="B", slug="org-b-208", is_active=True))
    db.commit()


# ── Superadmin sin empresa ────────────────────────────────────────────────────

def test_superadmin_sin_empresa_elegida_recibe_409_empresa_requerida(db):
    from app.core.errores import ErrorDeDominio
    from app.models.settings import Department
    from app.models.user import User
    superadmin = User(id="sa-sin-empresa", is_superadmin=True, organization_id=None)
    with _sin_empresa(db, current_user=superadmin, is_superadmin=True):
        db.add(Department(name="Sin empresa elegida"))
        with pytest.raises(ErrorDeDominio) as exc:
            db.flush()
        db.rollback()
    assert exc.value.status_code == 409
    assert exc.value.code == "empresa_requerida"
    assert exc.value.params["tabla"] == "departments"


def test_un_trabajo_sin_empresa_sigue_cortando_con_fila_sin_empresa(db):
    from app.core.errores import ErrorDeDominio
    from app.models.settings import Department
    with _sin_empresa(db):
        db.add(Department(name="Trabajo sin empresa"))
        with pytest.raises(ErrorDeDominio) as exc:
            db.flush()
        db.rollback()
    assert exc.value.status_code == 500
    assert exc.value.code == "fila_sin_empresa"


def test_superadmin_con_empresa_no_cambia(db):
    from app.db.empresa_obligatoria import superadmin_sin_empresa
    from app.models.user import User
    con = User(id="sa-con", is_superadmin=True, organization_id="1")
    with _sin_empresa(db, current_user=con, is_superadmin=True):
        assert superadmin_sin_empresa(db) is False
    with _sin_empresa(db, current_user=con, is_superadmin=True, organization_id="1"):
        assert superadmin_sin_empresa(db) is False


# ── Correo y SMS entrantes ────────────────────────────────────────────────────

def test_correo_entrante_sin_empresa_destinataria_se_ignora_sin_ticket(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk import inbound_mail
    _segunda_empresa(db)
    antes = db.query(Ticket).count()
    correo = inbound_mail.CorreoEntrante(remitente="ana@ejemplo.com", nombre="Ana", asunto="Ayuda",
                                         texto="No funciona", message_id="<m-208@x>",
                                         para=["nadie@ejemplo.com"])
    with _sin_empresa(db):
        r = inbound_mail.procesar(db, None, correo)
    assert r.accion == "ignored"
    assert r.motivo == "sin empresa destinataria"
    assert db.query(Ticket).count() == antes


def test_sms_entrante_sin_empresa_del_numero_se_ignora_sin_ticket(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.multichannel_service import process_inbound_sms
    _segunda_empresa(db)
    antes = db.query(Ticket).count()
    with _sin_empresa(db):
        r = process_inbound_sms(db, from_phone="+34600000000", body="hola", to_phone="+34911111111")
    assert r["ignored"] is True and r["ticket_id"] is None
    assert db.query(Ticket).count() == antes


# ── Registros accesorios ─────────────────────────────────────────────────────

def test_empresa_para_registro_prefiere_la_candidata_y_luego_la_sesion(db):
    from app.db.empresa_obligatoria import empresa_para_registro
    assert empresa_para_registro(db, None, "org-x") == "org-x"
    assert empresa_para_registro(db) == str(db.info["organization_id"])
    with _sin_empresa(db):
        assert empresa_para_registro(db) is None


def test_uso_de_ia_sin_empresa_no_se_registra_ni_rompe(db):
    from app.models.ai_providers import AIUsageLog
    from app.services.ai_provider_service.gasto import _registrar_uso
    antes = db.query(AIUsageLog).count()
    with _sin_empresa(db):
        _registrar_uso(db, None, {"model": "m"}, user_id=None, module="prueba", latency=1,
                       error_msg=None, organization_id=None)
        assert not [o for o in db.new if isinstance(o, AIUsageLog)]
    assert db.query(AIUsageLog).count() == antes


def test_accion_de_ia_sin_empresa_toma_la_del_usuario(db):
    from app.models.ai_chat import AIActionLog
    from app.services.ai_chat.core_service import log_action
    with _sin_empresa(db):
        log_action(db, "admin-test-id", "prueba", "consulta")
        nuevas = [o for o in db.new if isinstance(o, AIActionLog)]
    assert nuevas and str(nuevas[0].organization_id) == "1"
    db.rollback()


def test_cache_de_traduccion_sin_empresa_no_guarda(db):
    from app.models.traduccion import TranslationCacheEntry
    from app.services.traduccion import cache
    with _sin_empresa(db):
        cache.guardar(db, None, "k-208", "es", "en", "hola", "prueba", 4)
        assert not [o for o in db.new if isinstance(o, TranslationCacheEntry)]


def test_configuracion_semantica_sin_empresa_queda_en_memoria(db):
    from app.models.semantic_engine import SemConfig
    from app.services.semantic_engine_service import get_or_create_config
    antes = db.query(SemConfig).count()
    with _sin_empresa(db):
        cfg = get_or_create_config(db)
    assert cfg is not None
    assert db.query(SemConfig).count() == antes


# ── Inserts que se saltan el sellado ─────────────────────────────────────────

def test_reglas_sod_sin_empresa_no_se_siembran(db):
    from app.models.billing_reports import SodRule
    from app.services.grc_service import ensure_sod_seeded
    regla = {"module_a": "a", "action_a": "x", "module_b": "b", "action_b": "y", "risk": "high",
             "description": "Regla de prueba 208", "roles_conflict": []}
    ensure_sod_seeded(db, [regla], None)
    assert db.query(SodRule).filter(SodRule.organization_id.is_(None)).count() == 0


def test_huecos_de_cupo_sin_empresa_cortan_con_codigo(db):
    from datetime import date
    from app.core.errores import ErrorDeDominio
    from app.services.ausencias.cupos import _asegurar
    with _sin_empresa(db):
        with pytest.raises(ErrorDeDominio) as exc:
            _asegurar(db, None, "cupo-208", [(date(2026, 12, 1), None, "")], 2)
    assert exc.value.code == "fila_sin_empresa"
    assert exc.value.params["tabla"] == "huecos_de_cupo"


# ── Caminos de fondo y anónimos que publican la empresa (estáticos) ──────────

def test_el_planificador_de_mensajes_trabaja_en_la_empresa_de_cada_mensaje():
    from app.services.collaboration import _scheduler
    fuente = inspect.getsource(_scheduler._tick)
    assert "con_empresa(db, msg.organization_id)" in fuente


def test_el_agente_de_la_cmdb_publica_la_empresa_de_su_registro():
    from app.services.cmdb import models as cmdb_models
    fuente = inspect.getsource(cmdb_models.process_agent_checkin)
    assert "publicar_empresa(db, reg.organization_id)" in fuente


def test_el_webhook_entrante_de_colaboracion_publica_su_empresa():
    from app.services.collaboration import webhooks
    assert "publicar_empresa(db, fila.organization_id)" in inspect.getsource(webhooks.deliver_incoming)


def test_la_instantanea_colaborativa_lleva_la_empresa_del_documento():
    from app.services import documents_collab_service
    fuente = inspect.getsource(documents_collab_service.save_collab_snapshot)
    assert "organization_id=empresa_del_documento" in fuente


def test_la_aprobacion_por_correo_de_un_superadmin_va_a_la_empresa_de_la_solicitud():
    from app.services.approval_engine import por_correo
    fuente = inspect.getsource(por_correo._leer)
    assert 'db.info["organization_id"] = req.organization_id' in fuente
