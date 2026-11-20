"""Proveedores, migracion 191: portal del proveedor, aprobacion por importe y fuentes de medicion.

Diseno: docs/PROVEEDORES_Y_EXTERNALIZACION.md §13-§16. Cubre:

- Aprobacion de estados de cuenta con el motor comun (tipo `supplier_statement`):
  flujo por importe -> bandeja (`pending_approval`); decision final aprueba o
  deja en disputa; segregacion tambien en la bandeja; disputar la saca de la
  bandeja; sin flujo que encaje, aprobacion directa como antes.
- Portal del proveedor: solo contactos marcados con acceso vigente, solo lo de
  su proveedor, sin datos internos; informes con tipo y evidencias; auditoria.
- Fuentes de medicion: CMDB (filtros, software instalado, propietarios, retirados
  fuera), sistema externo por API e importacion (sin guardar identificadores),
  agregacion del mes, trabajo diario, mes cerrado intocable.
- Referencias de la ficha (selectores) y validacion de presupuesto, centro de
  coste, catalogo SD, contrato ALM y sesion UAT.
- Migracion 191 encadenada tras la 190 e idempotente.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.conftest import auth
from tests.test_proveedores_y_externalizacion import ADMIN, B, _datos, _empresa, _items, _servicio_con_tickets

PORTAL = "/api/v1/supplier-portal"
SUB_USER = "sub-test-id"


# ── Aprobacion por importe (motor comun) ─────────────────────────────────────

def _estado_conciliado(db, client, pm_token, factura="inv-191"):
    """Estado de cuenta cerrado por el PM y conciliado con una factura sin autor (1000 EUR)."""
    from app.models.enterprise import SubcontractorInvoice
    sub, c, _ = _servicio_con_tickets(db, client, pm_token, resueltos=2, incumplidos=0)
    _datos(client.post(f"{B}/{sub['id']}/documents", headers=auth(pm_token),
                       json={"doc_type": "nda", "expires_at": str(date.today() + timedelta(days=365))}))
    _datos(client.post(f"{B}/contracts/{c['id']}/activate", headers=auth(pm_token)))
    st = _datos(client.post(f"{B}/contracts/{c['id']}/statements", headers=auth(pm_token),
                            json={"period_start": "2026-01-01", "period_end": "2026-01-31"}))
    db.add(SubcontractorInvoice(id=factura, subcontractor_id=sub["id"], invoice_number="F-191",
                                issue_date=date(2026, 2, 1), amount=1000, total=1210, currency="EUR"))
    db.commit()
    st = _datos(client.post(f"{B}/statements/{st['id']}/reconcile", headers=auth(pm_token), json={"invoice_id": factura}))
    assert st["status"] == "reconciled"
    return sub, c, st


def _flujo(client, admin_token, condiciones: dict):
    r = client.post("/api/v1/approvals/workflows", headers=auth(admin_token), json={
        "name": "Estados de cuenta grandes", "entity_type": "supplier_statement", "is_default": False,
        "trigger_conditions": json.dumps(condiciones)})
    assert r.status_code in (200, 201), r.text
    wf = r.json()["data"]
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token), json={
        "step_order": 1, "name": "Dirección", "approver_type": "role", "approver_role": "admin", "timeout_hours": 48})
    assert r.status_code in (200, 201), r.text
    return wf


def test_el_tipo_esta_registrado_en_el_motor():
    from app.services.approval_engine import fuentes
    from app.services.approval_engine._base import _FINANCIAL_ENTITY_TYPES
    from app.services.grc_sod import MODULO_GRC_DE_ENTIDAD
    assert "supplier_statement" in fuentes.TIPOS
    assert "supplier_statement" in _FINANCIAL_ENTITY_TYPES
    assert MODULO_GRC_DE_ENTIDAD["supplier_statement"] == "invoices"


def test_aprobar_con_flujo_por_importe_va_a_la_bandeja_y_se_aplica(client, pm_token, admin_token, db):
    from app.models.billing_reports import ApprovalRequest
    from app.models.enterprise import SubcontractorInvoice
    from app.models.proveedores import SupplierStatement
    _flujo(client, admin_token, {"amount_gt": 500})
    sub, c, st = _estado_conciliado(db, client, pm_token)
    enviado = _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token)))
    assert enviado["status"] == "pending_approval" and enviado["approval_request_id"]
    req = db.get(ApprovalRequest, enviado["approval_request_id"])
    assert req.entity_type == "supplier_statement" and req.status == "pending"
    # En la bandeja no se reconcilia ni se aprueba desde la ficha.
    r = client.post(f"{B}/statements/{st['id']}/reconcile", headers=auth(pm_token), json={"invoice_id": "inv-191"})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_aprobacion_en_bandeja"
    r = client.post(f"{B}/statements/{st['id']}/approve", headers=auth(admin_token))
    assert r.status_code == 409 and r.json()["code"] == "proveedor_aprobacion_en_bandeja"
    # Decide la bandeja (admin: ni cerró el periodo ni registró la factura).
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", headers=auth(admin_token),
                    json={"decision": "approved"})
    assert r.status_code == 200, r.text
    db.expire_all()
    estado = db.get(SupplierStatement, st["id"])
    assert estado.status == "approved" and estado.approved_by == "admin-test-id"
    assert db.get(SubcontractorInvoice, "inv-191").status == "approved"


def test_rechazo_en_la_bandeja_deja_el_estado_en_disputa(client, pm_token, admin_token, db):
    from app.models.proveedores import SupplierStatement
    _flujo(client, admin_token, {"amount_gt": 500})
    _, _, st = _estado_conciliado(db, client, pm_token, factura="inv-191-r")
    enviado = _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token)))
    r = client.post(f"/api/v1/approvals/requests/{enviado['approval_request_id']}/decide", headers=auth(admin_token),
                    json={"decision": "rejected", "note": "Faltan partes del servicio"})
    assert r.status_code == 200, r.text
    db.expire_all()
    estado = db.get(SupplierStatement, st["id"])
    assert estado.status == "disputed" and estado.dispute_reason == "Faltan partes del servicio"


def test_segregacion_tambien_en_la_bandeja(client, pm_token, admin_token, db):
    """Quien cerró el periodo no lo aprueba ni desde la bandeja."""
    from app.models.proveedores import SupplierStatement
    _flujo(client, admin_token, {"amount_gt": 500})
    _, _, st = _estado_conciliado(db, client, pm_token, factura="inv-191-s")
    db.get(SupplierStatement, st["id"]).closed_by = "admin-test-id"
    db.commit()
    enviado = _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token)))
    r = client.post(f"/api/v1/approvals/requests/{enviado['approval_request_id']}/decide", headers=auth(admin_token),
                    json={"decision": "approved"})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_segregacion_aprobacion"
    db.expire_all()
    assert db.get(SupplierStatement, st["id"]).status == "pending_approval"


def test_disputar_en_la_bandeja_cancela_la_solicitud(client, pm_token, admin_token, db):
    from app.models.billing_reports import ApprovalRequest
    _flujo(client, admin_token, {"amount_gt": 500})
    _, _, st = _estado_conciliado(db, client, pm_token, factura="inv-191-d")
    enviado = _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token)))
    disputado = _datos(client.post(f"{B}/statements/{st['id']}/dispute", headers=auth(pm_token),
                                   json={"reason": "Importe mal"}))
    assert disputado["status"] == "disputed"
    db.expire_all()
    assert db.get(ApprovalRequest, enviado["approval_request_id"]).status == "cancelled"


def test_sin_flujo_que_encaje_aprobacion_directa_con_segregacion(client, pm_token, admin_token, db):
    _flujo(client, admin_token, {"amount_gt": 50000})   # no encaja con 1000 y no es por defecto
    _, _, st = _estado_conciliado(db, client, pm_token, factura="inv-191-n")
    sod = client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token))
    assert sod.status_code == 409 and sod.json()["code"] == "proveedor_segregacion_aprobacion"
    assert _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(admin_token)))["status"] == "approved"


def test_contexto_de_aprobacion_en_moneda_de_la_empresa(client, pm_token, db):
    from app.services.proveedores.facturacion import contexto_de_aprobacion, exigir_estado
    _, c, st = _estado_conciliado(db, client, pm_token, factura="inv-191-c")
    ctx = contexto_de_aprobacion(db, exigir_estado(db, st["id"]))
    assert ctx["amount"] == 1000.0 and ctx["contract_id"] == c["id"] and ctx["statement_currency"] == "EUR"


# ── Portal del proveedor ─────────────────────────────────────────────────────

@pytest.fixture
def portal(client, pm_token, sub_token, db):
    """Proveedor con servicio y paquete; el usuario externo de prueba es su persona (sin marca de portal)."""
    from app.models.enterprise import SubcontractorWorker
    sub = _empresa(client, pm_token, "Portal SA", ["managed_services"])
    otro = _empresa(client, pm_token, "Otro SA", ["managed_services"])
    s = _datos(client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "SOC 24x7", "internal_owner_id": ADMIN}))
    s_otro = _datos(client.post(f"{B}/{otro['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "SOC de otro"}))
    w = SubcontractorWorker(id="w-portal", organization_id=1, subcontractor_id=sub["id"], user_id=SUB_USER,
                            name="Contacto Portal", email="contacto@portal.example", has_access=True,
                            internal_owner_id=ADMIN, is_active=True)
    db.add(w)
    db.commit()
    return {"sub": sub, "otro": otro, "servicio": s, "servicio_otro": s_otro, "worker": w, "token": sub_token}


def test_sin_marca_de_contacto_no_hay_portal(client, portal, pm_token):
    tk = portal["token"]
    assert _datos(client.get(f"{PORTAL}/me", headers=auth(tk))) == {"enabled": False}
    r = client.get(f"{PORTAL}/services", headers=auth(tk))
    assert r.status_code == 403 and r.json()["code"] == "proveedor_portal_sin_acceso"
    # Un interno no tiene la capacidad `proveedores.portal`: 403 en todo el portal.
    assert client.get(f"{PORTAL}/me", headers=auth(pm_token)).status_code == 403
    assert client.get(f"{PORTAL}/reports", headers=auth(pm_token)).status_code == 403


def test_marcar_contacto_exige_acceso_vigente_y_se_audita(client, portal, pm_token, db):
    from app.models.enterprise import AuditLog
    sub = portal["sub"]
    w = portal["worker"]
    w.has_access = False
    db.commit()
    r = client.put(f"{B}/{sub['id']}/portal-contacts/{w.id}", headers=auth(pm_token), json={"supplier_portal": True})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_portal_requiere_acceso"
    w.has_access = True
    db.commit()
    items = _items(client.put(f"{B}/{sub['id']}/portal-contacts/{w.id}", headers=auth(pm_token),
                              json={"supplier_portal": True}))
    assert any(x["worker_id"] == w.id and x["supplier_portal"] for x in items)
    assert db.query(AuditLog).filter(AuditLog.resource == "subcontractor_workers", AuditLog.resource_id == w.id).count() >= 1
    assert _items(client.get(f"{B}/{sub['id']}/portal-contacts", headers=auth(pm_token)))[0]["supplier_portal"] is True


def _activar(client, portal, pm_token):
    _items(client.put(f"{B}/{portal['sub']['id']}/portal-contacts/{portal['worker'].id}", headers=auth(pm_token),
                      json={"supplier_portal": True}))


def test_el_contacto_ve_solo_lo_suyo_sin_datos_internos(client, portal, pm_token):
    _activar(client, portal, pm_token)
    tk = portal["token"]
    yo = _datos(client.get(f"{PORTAL}/me", headers=auth(tk)))
    assert yo["enabled"] and yo["supplier"]["id"] == portal["sub"]["id"] and yo["can_write"]
    servicios = _items(client.get(f"{PORTAL}/services", headers=auth(tk)))
    assert [s["id"] for s in servicios] == [portal["servicio"]["id"]]
    assert "internal_owner_id" not in servicios[0] and "notes" not in servicios[0]
    r = client.get(f"{PORTAL}/services/{portal['servicio_otro']['id']}/sla", headers=auth(tk))
    assert r.status_code == 404
    assert _items(client.get(f"{PORTAL}/statements", headers=auth(tk))) == []
    consumo = _datos(client.get(f"{PORTAL}/usage", headers=auth(tk)))
    assert consumo["contracts"] == []


def test_el_contacto_sube_informes_y_evidencias_de_su_proveedor(client, portal, pm_token, db):
    from app.models.enterprise import AuditLog, Notification
    _activar(client, portal, pm_token)
    tk = portal["token"]
    ajeno = client.post(f"{PORTAL}/reports", headers=auth(tk), json={
        "report_type": "sla_evidence", "service_id": portal["servicio_otro"]["id"], "summary": "x"})
    assert ajeno.status_code == 404
    sin_destino = client.post(f"{PORTAL}/reports", headers=auth(tk), json={"report_type": "service_log", "summary": "x"})
    assert sin_destino.status_code == 422
    mal_enlace = client.post(f"{PORTAL}/reports", headers=auth(tk), json={
        "report_type": "sla_evidence", "service_id": portal["servicio"]["id"], "summary": "x",
        "attachments": [{"url": "javascript:alert(1)"}]})
    assert mal_enlace.status_code == 422
    r = _datos(client.post(f"{PORTAL}/reports", headers=auth(tk), json={
        "report_type": "sla_evidence", "service_id": portal["servicio"]["id"], "summary": "SLA de noviembre",
        "period_start": "2026-11-01", "period_end": "2026-11-30",
        "attachments": [{"name": "Informe SIEM", "url": "https://siem.example/informe/11"}]}))
    assert r["submitted_via"] == "portal" and r["report_type"] == "sla_evidence" and r["attachments"][0]["kind"] == "link"
    assert "reviewed_by" not in r
    assert db.query(AuditLog).filter(AuditLog.resource == "supplier_reports", AuditLog.resource_id == r["id"]).count() == 1
    # El responsable interno del servicio recibe el aviso y lo ve en la ficha.
    assert db.query(Notification).filter(Notification.user_id == ADMIN).count() >= 1
    internos = _items(client.get(f"{B}/{portal['sub']['id']}/reports", headers=auth(pm_token)))
    assert any(x["id"] == r["id"] and x["submitted_via"] == "portal" for x in internos)
    assert [x["id"] for x in _items(client.get(f"{PORTAL}/reports", headers=auth(tk)))] == [r["id"]]


def test_proveedor_suspendido_solo_lectura_y_acceso_caducado_fuera(client, portal, pm_token, db):
    _activar(client, portal, pm_token)
    tk = portal["token"]
    from app.models.enterprise import Subcontractor
    sub = db.get(Subcontractor, portal["sub"]["id"])
    sub.lifecycle_status = "suspended"
    db.commit()
    assert _datos(client.get(f"{PORTAL}/me", headers=auth(tk)))["can_write"] is False
    r = client.post(f"{PORTAL}/reports", headers=auth(tk), json={
        "report_type": "periodic", "service_id": portal["servicio"]["id"], "summary": "x"})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_no_activo"
    portal["worker"].access_until = date.today() - timedelta(days=1)
    db.commit()
    assert client.get(f"{PORTAL}/me", headers=auth(tk)).status_code == 401


def test_capacidad_del_portal_solo_para_externos(db):
    from app.core.capacidades import CAPACIDADES
    assert CAPACIDADES["proveedores.portal"].roles == ("subcontractor",)


# ── Fuentes de medicion ──────────────────────────────────────────────────────

def _cis(db):
    from app.models.service_desk._enums import CIStatus, CIType
    from app.models.service_desk.cmdb import ConfigurationItem as CI
    filas = [
        CI(id="ci-1", organization_id=1, code="EP-001", name="Portátil 1", ci_type=CIType.endpoint, owner_user_id=ADMIN),
        CI(id="ci-2", organization_id=1, code="EP-002", name="Portátil 2", ci_type=CIType.endpoint, owner_user_id=ADMIN),
        CI(id="ci-3", organization_id=1, code="EP-003", name="Portátil 3", ci_type=CIType.endpoint, owner_user_id="pm-test-id"),
        CI(id="ci-4", organization_id=1, code="EP-004", name="Retirado", ci_type=CIType.endpoint, status=CIStatus.retired),
        CI(id="ci-5", organization_id=1, code="SRV-001", name="Servidor", ci_type=CIType.server),
    ]
    db.add_all(filas)
    db.commit()


def _servicio_medido(client, pm_token, fuente: str, config: dict, unidad="device_month", nombre="Medidos SA"):
    sub = _empresa(client, pm_token, nombre, ["managed_services"])
    c = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token), json={"title": "Por dispositivo"}))
    s = _datos(client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "EDR gestionado", "contract_id": c["id"], "unit": unidad,
        "metering_source": fuente, "metering_config": config}))
    _datos(client.post(f"{B}/contracts/{c['id']}/pricing", headers=auth(pm_token), json={
        "model": "per_unit", "unit": unidad, "unit_price": 3, "service_id": s["id"]}))
    return sub, c, s


def test_medicion_desde_la_cmdb_cuenta_y_acumula_el_mes(client, pm_token, db):
    from app.models.proveedores import SupplierUsageRecord
    _cis(db)
    _, c, s = _servicio_medido(client, pm_token, "cmdb", {"ci_types": ["endpoint"]})
    assert s["metering_source"] == "cmdb" and s["metering_config"]["count"] == "devices"
    previa = _datos(client.post(f"{B}/metering/preview", headers=auth(pm_token), json={
        "metering_source": "cmdb", "metering_config": {"ci_types": ["endpoint"]}, "unit": "device_month"}))
    assert previa["quantity"] == 3.0 and "EP-004" not in previa["detail"]["examples"]   # el retirado no cuenta
    m = _datos(client.post(f"{B}/services/{s['id']}/metering/measure", headers=auth(pm_token)))
    assert m["usage"]["quantity"] == 3.0 and m["usage"]["source"] == "cmdb"
    _datos(client.post(f"{B}/services/{s['id']}/metering/measure", headers=auth(pm_token)))
    assert db.query(SupplierUsageRecord).filter(SupplierUsageRecord.service_id == s["id"]).count() == 1


def test_medicion_cmdb_por_propietarios_y_con_software_instalado(client, pm_token, db):
    from app.models.cmdb_software import SoftwareInstance, SoftwareProduct
    from app.services.proveedores.medicion import vista_previa
    _cis(db)
    db.add(SoftwareProduct(id="sw-edr", organization_id=1, name="Agente EDR", match_key="agente-edr"))
    db.add(SoftwareInstance(id="si-1", organization_id=1, product_id="sw-edr", ci_id="ci-1"))
    db.add(SoftwareInstance(id="si-2", organization_id=1, product_id="sw-edr", ci_id="ci-3", status="retired"))
    db.commit()
    assert vista_previa(db, "cmdb", {"ci_types": ["endpoint"], "count": "owners"}, "user_month")["quantity"] == 2.0
    assert vista_previa(db, "cmdb", {"software_product_id": "sw-edr"}, "device_month")["quantity"] == 1.0


def test_medicion_solo_con_unidad_por_dispositivo_o_usuario(client, pm_token):
    sub = _empresa(client, pm_token, "Sin unidad SA", ["managed_services"])
    r = client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "x", "unit": "ticket", "metering_source": "cmdb", "metering_config": {}})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_medicion_sin_unidad"
    r = client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "x", "unit": "device_month", "metering_source": "cmdb",
        "metering_config": {"ci_types": ["tostadora"]}})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_medicion_filtro_no_valido"
    r = client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token), json={
        "service_type": "soc", "name": "x", "unit": "device_month", "metering_source": "external", "metering_config": {}})
    assert r.status_code == 422


def test_recuento_externo_por_api_agrega_y_no_guarda_identificadores(client, pm_token, db):
    from app.models.proveedores import SupplierUsageRecord
    _, c, s = _servicio_medido(client, pm_token, "external", {"system": "SIEM", "aggregation": "max"})
    _datos(client.post(f"{B}/services/{s['id']}/metering/ingest", headers=auth(pm_token),
                       json={"quantity": 120, "as_of": "2026-01-10"}))
    u = _datos(client.post(f"{B}/services/{s['id']}/metering/ingest", headers=auth(pm_token),
                           json={"items": ["pc-1", "PC-1", "pc-2", " pc-3 "], "as_of": "2026-01-20"}))
    assert u["quantity"] == 120.0                       # agregacion: el maximo del mes
    assert u["detail"]["last"] == 3.0 and u["source"] == "api" and u["source_system"] == "SIEM"
    fila = db.query(SupplierUsageRecord).filter(SupplierUsageRecord.id == u["id"]).one()
    assert "pc-1" not in json.dumps(fila.detail).lower()   # RGPD: solo el numero
    p = _datos(client.get(f"{B}/contracts/{c['id']}/forecast", headers=auth(pm_token),
                          params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    assert p["subtotal"] == 360.0                        # 120 dispositivos x 1 mes x 3
    futura = client.post(f"{B}/services/{s['id']}/metering/ingest", headers=auth(pm_token),
                         json={"quantity": 1, "as_of": str(date.today() + timedelta(days=2))})
    assert futura.status_code == 422 and futura.json()["code"] == "proveedor_medicion_fecha_futura"


def test_recuento_externo_rechazado_si_la_fuente_es_otra(client, pm_token):
    _, _, s = _servicio_medido(client, pm_token, "cmdb", {}, nombre="CMDB SA")
    r = client.post(f"{B}/services/{s['id']}/metering/ingest", headers=auth(pm_token), json={"quantity": 5})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_medicion_fuente_distinta"


def test_importacion_de_recuentos_fila_a_fila(client, pm_token):
    sub, _, s = _servicio_medido(client, pm_token, "external", {"system": "MDM"}, nombre="Import SA")
    _, _, ajeno = _servicio_medido(client, pm_token, "external", {"system": "MDM"}, nombre="Ajeno SA")
    r = _datos(client.post(f"{B}/{sub['id']}/metering/import", headers=auth(pm_token), json={"rows": [
        {"service_id": s["id"], "as_of": "2026-01-31", "quantity": 40},
        {"service_id": ajeno["id"], "as_of": "2026-01-31", "quantity": 40},
    ]}))
    assert r["imported"] == 1 and r["failed"] == 1 and r["rows"][1]["ok"] is False


def test_trabajo_diario_mide_los_servicios_de_la_cmdb(client, pm_token, db):
    from app.models.proveedores import SupplierUsageRecord
    from app.services.proveedores.medicion import medir_todo
    _cis(db)
    _, _, s = _servicio_medido(client, pm_token, "cmdb", {"ci_types": ["endpoint"]}, nombre="Diario SA")
    r = medir_todo(db, None)
    assert r["supplier_metering_measured"] >= 1 and r["supplier_metering_failed"] == 0
    fila = db.query(SupplierUsageRecord).filter(SupplierUsageRecord.service_id == s["id"]).one()
    assert fila.quantity == 3.0 and fila.source == "cmdb" and fila.detail["n_samples"] == 1


def test_mes_cerrado_en_un_estado_de_cuenta_no_se_toca(client, pm_token, db):
    from app.models.proveedores import SupplierStatement, SupplierUsageRecord
    _, _, ext = _servicio_medido(client, pm_token, "external", {"system": "SIEM"}, nombre="Cerrado SA")
    u = _datos(client.post(f"{B}/services/{ext['id']}/metering/ingest", headers=auth(pm_token),
                           json={"quantity": 10, "as_of": "2026-01-05"}))
    st = SupplierStatement(id="st-cerrado", organization_id=1, subcontractor_id=ext["subcontractor_id"],
                           contract_id=ext["contract_id"], period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    db.add(st)
    db.flush()
    db.query(SupplierUsageRecord).filter(SupplierUsageRecord.id == u["id"]).update({"statement_id": "st-cerrado"})
    db.commit()
    r = client.post(f"{B}/services/{ext['id']}/metering/ingest", headers=auth(pm_token),
                    json={"quantity": 99, "as_of": "2026-01-20"})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_consumo_en_estado_de_cuenta"


# ── Referencias de la ficha ──────────────────────────────────────────────────

def test_referencias_y_validacion_de_los_selectores(client, pm_token, db):
    from app.models.alm import ALMCostCenter
    db.add(ALMCostCenter(id="cc-191", organization_id=1, code="CC-191", name="Seguridad"))
    db.commit()
    ref = _datos(client.get(f"{B}/references", headers=auth(pm_token)))
    for k in ("budgets", "cost_centers", "alm_contracts", "service_items", "uat_sessions", "ci_types",
              "ci_classes", "software_products"):
        assert k in ref
    assert any(x["id"] == "cc-191" for x in ref["cost_centers"]) and "endpoint" in ref["ci_types"]
    sub = _empresa(client, pm_token, "Selectores SA", ["managed_services"])
    ok = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token),
                            json={"title": "Con centro", "cost_center_id": "cc-191"}))
    assert ok["cost_center_id"] == "cc-191"
    for campo in ("budget_id", "cost_center_id"):
        r = client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token), json={"title": "x", campo: "no-existe"})
        assert r.status_code == 404, campo
    for campo in ("service_item_id", "alm_contract_id"):
        r = client.post(f"{B}/{sub['id']}/services", headers=auth(pm_token),
                        json={"service_type": "soc", "name": "x", campo: "no-existe"})
        assert r.status_code == 404, campo


# ── Migracion 191 ────────────────────────────────────────────────────────────

def test_migracion_191_encadenada_e_idempotente():
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "191_proveedores_portal_y_aprobacion.py"
    spec = importlib.util.spec_from_file_location("migracion_191", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "191_proveedores_portal_y_aprobacion"
    assert m.down_revision == "190_cmdb_software_y_vulnerabilidades"
    columnas = {(t, c.name) for t, c in m.COLUMNAS}
    assert ("subcontractor_workers", "supplier_portal") in columnas
    assert ("supplier_statements", "approval_request_id") in columnas
    # Idempotente: cada columna se crea solo si no existe (el modelo ya las declara).
    from app.models.enterprise import SubcontractorWorker
    from app.models.proveedores import SupplierReport, SupplierService, SupplierStatement, SupplierUsageRecord
    modelos = {"subcontractor_workers": SubcontractorWorker, "supplier_services": SupplierService,
               "supplier_usage_records": SupplierUsageRecord, "supplier_reports": SupplierReport,
               "supplier_statements": SupplierStatement}
    for tabla, nombre in columnas:
        assert nombre in modelos[tabla].__table__.c, (tabla, nombre)
