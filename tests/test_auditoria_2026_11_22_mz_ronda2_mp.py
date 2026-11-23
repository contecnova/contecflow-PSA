"""Auditoria 2026-11-22, informe 03 (servicios m-z), segunda ronda: bloque m-p.

Medios y bajos de m-p: formularios publicos, SMTP, auditoria de empresas,
proveedores, pipeline, presupuestos, avisos, politicas, numeracion, PDF,
redaccion del portal y entrenamiento ML.
"""
from __future__ import annotations

import ssl
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errores import ErrorDeDominio
from app.models.user import User

RAIZ = Path(__file__).resolve().parents[1]


# ── Formularios publicos: el destino es de la empresa del formulario ─────────

def _formulario(db, org, proyecto=None, tipo="ticket"):
    from app.models.public_forms import PublicForm
    f = PublicForm(id=str(uuid.uuid4()), name="F", form_type=tipo, token=uuid.uuid4().hex, is_active=True,
                   target_project_id=proyecto, default_priority="medium", notify_emails="[]",
                   created_by="admin-test-id", organization_id=org)
    db.add(f)
    db.commit()
    return f


def test_formulario_con_proyecto_de_otra_empresa_se_rechaza(db, seed_multitenant):
    from app.core.codigos_de_error import ErrorConCodigo
    from app.services import public_forms_service as pf
    assert pf.destino_de_la_empresa(db, "org-a-test", "project-a-test", None)
    assert not pf.destino_de_la_empresa(db, "org-a-test", "project-b-test", None)
    assert not pf.destino_de_la_empresa(db, "org-a-test", "no-existe", None)
    with pytest.raises(ErrorConCodigo) as e:
        pf.validar_destino("task", "project-b-test", db=db, org_id="org-a-test")
    assert e.value.codigo == "formulario_destino_ajeno"


def test_un_formulario_antiguo_con_destino_ajeno_no_crea_nada_alli(db, seed_multitenant):
    from app.models.task import Task
    from app.services import public_forms_service as pf
    f = _formulario(db, "org-a-test", "project-b-test", tipo="task")
    sub, creado = pf.submit_form(db, form=f, submitter_name="x", submitter_email="x@x.com", subject="s",
                                 description="d", priority="medium", category=None, extra_fields={},
                                 ip_address=None)
    assert creado is None and sub.created_entity_id is None
    assert db.query(Task).filter(Task.project_id == "project-b-test", Task.title == "s").count() == 0


# ── SMTP: certificado verificado ─────────────────────────────────────────────

def test_smtp_verifica_el_certificado_salvo_relay_autofirmado(monkeypatch):
    from app.services import notification_service as ns
    ctx = ns.contexto_tls()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    monkeypatch.setattr(ns.settings, "SMTP_TLS_VERIFY", False, raising=False)
    ctx = ns.contexto_tls()
    assert ctx.verify_mode == ssl.CERT_NONE and ctx.check_hostname is False


# ── organizations_service: el actor de la auditoria es quien asigna ──────────

def test_la_auditoria_de_asignar_y_quitar_lleva_al_actor(db):
    from app.models.enterprise import AuditLog
    from app.models.mfa import Organization
    from app.models.user import UserOrganizationMembership
    from app.services.organizations_service import assign_user_to_org, remove_user_from_org
    db.add(Organization(id="org-act", name="Act", slug="org-act", max_users=10))
    db.commit()
    admin = db.get(User, "admin-test-id")
    dev = db.query(User).filter(User.username == "dev_test").one()
    pm = db.get(User, "pm-test-id")
    db.add(UserOrganizationMembership(user_id=pm.id, organization_id="org-act"))
    db.add(UserOrganizationMembership(user_id=dev.id, organization_id="1"))
    db.commit()
    assign_user_to_org("org-act", dev.id, db, actor=admin)
    remove_user_from_org("org-act", dev.id, db, actor=admin)
    filas = db.query(AuditLog).filter(AuditLog.resource_id == "org-act",
                                      AuditLog.action.in_(["ORG_ASSIGN", "ORG_REMOVE"])).all()
    assert len(filas) == 2 and {f.user_id for f in filas} == {admin.id}


# ── Proveedores: tope sin disputados y factura conciliada una vez ────────────

def _proveedor(db):
    from app.models.enterprise import Subcontractor, SubcontractorInvoice
    from app.models.proveedores import SupplierContract, SupplierStatement
    db.add(Subcontractor(id="sub-r2", code="SUB-9201", name="R2 SA", organization_id="1"))
    db.flush()
    c = SupplierContract(id="c-r2", subcontractor_id="sub-r2", title="c", organization_id="1", total_cap=1000)
    db.add(c)
    db.flush()
    estados = []
    for i, estado in enumerate(("disputed", "closed", "closed")):
        st = SupplierStatement(subcontractor_id="sub-r2", contract_id="c-r2", period_start=date(2026, i + 1, 1),
                               period_end=date(2026, i + 1, 28), currency="EUR", status=estado,
                               expected_amount=400, organization_id="1", lines=[])
        db.add(st)
        estados.append(st)
    db.add(SubcontractorInvoice(id="inv-r2", subcontractor_id="sub-r2", invoice_number="F-R2",
                                issue_date=date(2026, 3, 1), amount=400, total=484, currency="EUR"))
    db.commit()
    return c, estados


def test_el_tope_no_cuenta_estados_disputados(db):
    from app.services.proveedores.facturacion import _gastado_antes
    c, _ = _proveedor(db)
    assert _gastado_antes(db, c) == 800.0


def test_una_factura_no_se_concilia_dos_veces(db):
    from app.services.proveedores.facturacion import conciliar
    _, (_, uno, dos) = _proveedor(db)
    admin = db.get(User, "admin-test-id")
    assert conciliar(db, uno, "inv-r2", admin)["status"] == "reconciled"
    with pytest.raises(ErrorDeDominio) as e:
        conciliar(db, dos, "inv-r2", admin)
    assert (e.value.status_code, e.value.code) == (409, "proveedor_factura_ya_conciliada")
    # Volver a conciliar el mismo estado con su factura sigue valiendo.
    assert conciliar(db, uno, "inv-r2", admin)["status"] == "reconciled"


# ── Pipeline: actividades solo de oportunidades que se ven ───────────────────

def test_actividades_de_una_oportunidad_ajena_dan_404(db, seed_multitenant):
    from app.models.pipeline import Opportunity
    from app.services import pipeline_service as ps
    ajena = Opportunity(id="opp-ajena", code="OPP-9", name="Ajena", client_name="Cliente B",
                        owner_id="outsider-test-id", organization_id="org-b-test")
    db.add(ajena)
    db.commit()
    pm = db.get(User, "pm-test-id")
    for llamada in (lambda: ps.add_activity(db, pm, "opp-ajena", "note", "hola"),
                    lambda: ps.list_activities(db, "opp-ajena", pm)):
        with pytest.raises(ErrorDeDominio) as e:
            llamada()
        assert e.value.status_code == 404


# ── Presupuestos: mes validado y maquina de estados del pedido ───────────────

@pytest.mark.parametrize("mes", ["2026-13", "abc", "2026/01", "", "2026-1"])
def test_mes_mal_escrito_da_400_y_no_500(mes):
    from app.services.presupuestos_seguir import _anio_mes
    with pytest.raises(ErrorDeDominio) as e:
        _anio_mes(mes)
    assert (e.value.status_code, e.value.code) == (400, "mes_formato_no_valido")


def test_un_pedido_anulado_no_se_factura_ni_uno_facturado_se_anula(db):
    from app.models.mfa import BudgetCommitment
    from app.services import presupuestos_seguir as ps
    admin = db.get(User, "admin-test-id")
    c = BudgetCommitment(organization_id="1", origen_id="o1", tipo="otros", descripcion="p", importe=10, mes="2026-01",
                         estado="anulado", created_by=admin.id)
    db.add(c)
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        ps.actualizar_pedido(db, admin, c.id, {"estado": "facturado"})
    assert (e.value.status_code, e.value.code) == (409, "transicion_no_permitida")
    c.estado = "comprometido"
    db.commit()
    assert ps.actualizar_pedido(db, admin, c.id, {"estado": "facturado"})["estado"] == "facturado"
    with pytest.raises(ErrorDeDominio):
        ps.actualizar_pedido(db, admin, c.id, {"estado": "anulado"})


def test_el_traspaso_no_confirma_antes_de_abrir_el_flujo():
    fuente = (RAIZ / "app/services/presupuestos_seguir.py").read_text(encoding="utf-8")
    cuerpo = fuente.split("def solicitar_traspaso", 1)[1].split("\ndef ", 1)[0]
    assert cuerpo.index("db.flush()") < cuerpo.index("fuentes.abrir") < cuerpo.index("db.commit()")


# ── Avisos: Redis compartido y empujon tras el commit ────────────────────────

def test_el_empujon_por_websocket_sale_al_confirmar_y_no_si_se_deshace(db, monkeypatch):
    from app.services import notifications as n
    enviados = []
    monkeypatch.setattr(n, "_push_ws_notification", lambda uid, p: enviados.append(uid))
    n.notify_user(db, "pm-test-id", "system", "Hola")
    assert enviados == []
    db.commit()
    assert enviados == ["pm-test-id"]
    n.notify_user(db, "pm-test-id", "system", "Adios")
    db.rollback()
    db.commit()
    assert enviados == ["pm-test-id"]


def test_el_cliente_redis_se_reutiliza(monkeypatch):
    import sys
    import types
    from app.services import notifications as n
    creados = []
    falso = types.SimpleNamespace(from_url=lambda url, **kw: creados.append(url) or types.SimpleNamespace(
        publish=lambda canal, msg: None))
    monkeypatch.setitem(sys.modules, "redis", falso)
    monkeypatch.setattr(n, "_REDIS_URL", "redis://x")
    monkeypatch.setattr(n, "_redis_cliente", None)
    n._push_ws_notification("u1", {})
    n._push_ws_notification("u2", {})
    assert creados == ["redis://x"]


# ── perf_reminder: por notify_user (preferencias) ────────────────────────────

def test_el_recordatorio_respeta_las_preferencias_de_aviso(db, monkeypatch):
    from app.models.enterprise import Notification
    from app.models.performance import PerformanceReview, ReviewCycle, ReviewCycleStatus, ReviewStatus
    from app.services import perf_reminder_service as pr
    from app.services import preferencias_de_aviso
    hoy = date(2026, 11, 23)
    ciclo = ReviewCycle(name="C", status=ReviewCycleStatus.active, end_date=hoy + timedelta(days=1),
                        organization_id="1")
    db.add(ciclo)
    db.flush()
    dev = db.query(User).filter(User.username == "dev_test").one()
    db.add(PerformanceReview(cycle_id=ciclo.id, reviewee_id=dev.id, reviewer_id="pm-test-id",
                             status=ReviewStatus.pending, organization_id="1"))
    db.commit()
    monkeypatch.setattr(preferencias_de_aviso, "quiere", lambda *a, **k: False)
    assert pr.send_pending_review_reminders(db, today=hoy)["reminders_sent"] == 0
    assert db.query(Notification).filter(Notification.resource == "performance_reminder").count() == 0
    monkeypatch.setattr(preferencias_de_aviso, "quiere", lambda *a, **k: True)
    assert pr.send_pending_review_reminders(db, today=hoy)["reminders_sent"] == 1


# ── Politicas: importacion con tope ──────────────────────────────────────────

def test_la_importacion_de_tablas_tiene_tope_de_filas_y_bytes(db, monkeypatch):
    from app.services.politicas import servicio
    monkeypatch.setattr(servicio, "_tabla", lambda db, tid: object())
    csv = "pais;valor\n" + "ES;1\n" * (servicio.MAX_FILAS + 5)
    with pytest.raises(ErrorDeDominio) as e:
        servicio.importar(db, None, "t", csv.encode(), "t.csv")
    assert e.value.code == "importacion_demasiadas_filas"
    with pytest.raises(ErrorDeDominio) as e:
        servicio.importar(db, None, "t", b"x" * (servicio.MAX_BYTES_IMPORTACION + 1), "t.csv")
    assert (e.value.status_code, e.value.code) == (413, "fichero_supera_mb")


# ── Numeracion: año en la zona de la empresa ─────────────────────────────────

def test_el_anio_de_la_numeracion_es_el_de_la_empresa(db, monkeypatch):
    from app.services import numbering
    from app.services.settings_service import por_empresa

    class _Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(numbering, "datetime", _Reloj)
    monkeypatch.setattr(por_empresa, "zona_de_empresa", lambda db, org=None, **k: "Europe/Madrid")
    assert numbering._current_year(db, "1") == 2027
    assert numbering._current_year() == 2026


# ── PDF: sin fechas naive ────────────────────────────────────────────────────

def test_el_pdf_no_usa_la_hora_del_servidor():
    fuente = (RAIZ / "app/services/pdf_export_service.py").read_text(encoding="utf-8")
    assert "datetime.now()" not in fuente


# ── Portal: redaccion de IBAN, DNI y telefonos con espacios ──────────────────

@pytest.mark.parametrize("texto,nota", [
    ("Mi cuenta ES91 2100 0418 4502 0005 1332 gracias", "iban"),
    ("DNI 12345678-Z", "id_number"),
    ("NIE X1234567L", "id_number"),
    ("llamame al +34 600 12 34 56", "number"),
    ("o al 600-123-456", "number"),
])
def test_la_redaccion_del_portal_ve_formatos_con_espacios(texto, nota):
    from app.services.portal_conversation_service.politicas import _redact_sensitive
    salida, cambiado, notas = _redact_sensitive(texto, [])
    assert cambiado and nota in notas and "REDACTED" in salida


def test_la_redaccion_no_toca_fechas_ni_importes():
    from app.services.portal_conversation_service.politicas import _redact_sensitive
    texto = "Reunion el 2026-11-23 10:00, importe 1.250,00"
    assert _redact_sensitive(texto, [])[1] is False


# ── ml_trainer: una sola clase no rompe el trabajo ───────────────────────────

def test_el_entrenamiento_con_una_sola_clase_se_omite(db, monkeypatch):
    from app.services import ml_trainer
    n = ml_trainer.MIN_TRAINING_SAMPLES
    monkeypatch.setattr(ml_trainer, "extract_training_dataset", lambda db, org: ([[0.0]] * n, [1] * n, ["p"] * n))
    monkeypatch.setattr(ml_trainer, "_SKLEARN_AVAILABLE", True)
    r = ml_trainer.train_model(db, "1")
    assert (r["status"], r["reason"]) == ("skipped", "single_class")
