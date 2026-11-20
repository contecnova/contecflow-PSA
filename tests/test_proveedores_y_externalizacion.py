"""Proveedores y externalizacion (19-11-2026, migracion 189).

Diseno: docs/PROVEEDORES_Y_EXTERNALIZACION.md. Cubre:

- Alta de freelance en un paso (proveedor + persona + usuario = recurso).
- Reglas de asignacion: freelance -> su persona; empresa con personas -> no
  asignable; outsourcing -> asignable como unidad, excluyente con el asignado;
  suspendido -> nada nuevo; asignacion sin persona -> paquete de trabajo.
- Paquetes: ciclo, rechazo con motivo, aceptacion con UAT.
- Calculo de cobro: escalados, meses, cuota con exceso, creditos por SLA,
  minimo por linea, minimo comprometido y tope del contrato.
- Estados de cuenta: conciliacion, tolerancia y segregacion de la aprobacion.
- GRC: requisitos para activar, riesgo, accesos, baja, controles, bloqueo legal.
- Formacion/evaluaciones de externos solo con `training_enabled`.
- Clasificacion de los datos existentes (migracion).
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth

import app.services.proveedores.asignabilidad  # noqa: F401  (registra el before_flush de Task)

ADMIN, PM = "admin-test-id", "pm-test-id"
P1 = "p-prov-1"
B = "/api/v1/suppliers"


def _datos(r):
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


def _items(r):
    """Listas: `APIListResponse` (`items` + `meta`)."""
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    return cuerpo["items"] if "items" in cuerpo else cuerpo["data"]


@pytest.fixture
def proyecto(db):
    db.add(Project(id=P1, organization_id=1, code="PRJ-PV1", name="Proyecto proveedores",
                   project_type=ProjectType.consulting, status=ProjectStatus.active, pm_id=PM, created_by=ADMIN))
    db.commit()
    return P1


def _empresa(client, token, nombre: str, modos: list) -> dict:
    sub = _datos(client.post("/api/v1/enterprise/subcontractors", headers=auth(token),
                             json={"name": nombre, "currency": "EUR"}))
    return _datos(client.patch(f"{B}/{sub['id']}/classification", headers=auth(token),
                               json={"kind": "company", "engagement_modes": modos, "internal_owner_id": ADMIN}))


def _freelance(client, token, nombre="Ana Freelance") -> dict:
    return _datos(client.post(f"{B}/freelance", headers=auth(token), json={
        "name": nombre, "email": "ana.freelance@example.com", "internal_owner_id": ADMIN, "cost_rate": 50,
        "has_access": False, "role": "Dev"}))


# ── Alta de freelance ────────────────────────────────────────────────────────

def test_alta_de_freelance_crea_persona_recurso_y_contrato(client, pm_token, db):
    from app.models.enterprise import SubcontractorWorker
    from app.models.proveedores import SupplierContract
    from app.models.user import User, UserRole
    r = _freelance(client, pm_token)
    sub = r["supplier"]
    assert sub["kind"] == "freelance" and sub["engagement_modes"] == ["staff_augmentation"]
    w = db.get(SubcontractorWorker, r["worker"]["id"])
    assert sub["freelancer_worker_id"] == w.id
    u = db.get(User, w.user_id)
    assert u is not None and u.role == UserRole.subcontractor  # es el recurso (Recursos, capacidad, tareas)
    c = db.query(SupplierContract).filter(SupplierContract.subcontractor_id == sub["id"]).one()
    assert c.contract_type == "freelance" and c.status == "draft"
    assert [(x.model, x.unit, x.unit_price) for x in c.lines] == [("per_resource", "hour", 50)]
    perfil = _datos(client.get(f"{B}/{sub['id']}/profile", headers=auth(pm_token)))
    assert perfil["assign_to"] == "person" and len(perfil["workers"]) == 1


def test_freelance_exige_responsable_interno(client, pm_token):
    r = client.post(f"{B}/freelance", headers=auth(pm_token), json={"name": "Sin responsable",
                                                                     "internal_owner_id": "no-existe"})
    assert r.status_code == 400 and r.json()["code"] == "externo_responsable_no_valido"


def test_no_se_clasifica_freelance_con_varias_personas(client, pm_token, db):
    from app.models.enterprise import SubcontractorWorker
    sub = _empresa(client, pm_token, "Dos Personas SL", ["staff_augmentation"])
    for n in ("Uno", "Dos"):
        db.add(SubcontractorWorker(subcontractor_id=sub["id"], name=n, is_active=True))
    db.commit()
    r = client.patch(f"{B}/{sub['id']}/classification", headers=auth(pm_token), json={"kind": "freelance"})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_freelance_una_persona"


# ── Reglas de asignacion ─────────────────────────────────────────────────────

def _tarea(client, token, **extra):
    return client.post("/api/v1/tasks", headers=auth(token), json={"title": "T", "project_id": P1, **extra})


def test_al_freelance_se_le_asigna_su_persona_no_la_empresa(client, pm_token, proyecto, db):
    from app.models.enterprise import SubcontractorWorker
    r = _freelance(client, pm_token)
    no = _tarea(client, pm_token, supplier_id=r["supplier"]["id"])
    assert no.status_code == 422 and no.json()["code"] == "proveedor_freelance_asigna_persona"
    w = db.get(SubcontractorWorker, r["worker"]["id"])
    assert _tarea(client, pm_token, assignee_id=w.user_id).status_code in (200, 201)


def test_empresa_con_personas_no_es_asignable_como_unidad(client, pm_token, proyecto):
    sub = _empresa(client, pm_token, "Staff SL", ["staff_augmentation"])
    r = _tarea(client, pm_token, supplier_id=sub["id"])
    assert r.status_code == 422 and r.json()["code"] == "proveedor_no_asignable"
    assert all(s["id"] != sub["id"] for s in _items(client.get(f"{B}/assignable", headers=auth(pm_token))))


def test_outsourcing_asignable_y_excluyente_con_el_asignado(client, pm_token, proyecto):
    sub = _empresa(client, pm_token, "Outsourcing SA", ["outsourcing"])
    wp = _datos(client.post(f"{B}/{sub['id']}/work-packages", headers=auth(pm_token),
                            json={"project_id": P1, "title": "Módulo de pagos", "scope_type": "tasks", "price": 10000}))
    ok = _tarea(client, pm_token, supplier_id=sub["id"], supplier_work_package_id=wp["id"])
    assert ok.status_code in (200, 201), ok.text
    assert ok.json()["data"]["supplier_name"] == "Outsourcing SA"
    doble = _tarea(client, pm_token, supplier_id=sub["id"], assignee_id=PM)
    assert doble.status_code == 422 and doble.json()["code"] == "proveedor_asignacion_exclusiva"
    lista = _items(client.get(f"{B}/assignable", headers=auth(pm_token), params={"project_id": P1}))
    assert any(s["id"] == sub["id"] and s["work_packages"][0]["id"] == wp["id"] for s in lista)
    por_proyecto = _datos(client.get(f"{B}/by-project/{P1}", headers=auth(pm_token)))
    assert por_proyecto["tasks"][0]["supplier_id"] == sub["id"]


def test_proveedor_suspendido_no_recibe_trabajo(client, pm_token, proyecto):
    sub = _empresa(client, pm_token, "Suspendida SA", ["outsourcing"])
    _datos(client.post(f"{B}/{sub['id']}/suspend", headers=auth(pm_token), json={"reason": "impago"}))
    r = _tarea(client, pm_token, supplier_id=sub["id"])
    assert r.status_code == 422 and r.json()["code"] == "proveedor_no_activo"
    _datos(client.post(f"{B}/{sub['id']}/reactivate", headers=auth(pm_token)))
    assert _tarea(client, pm_token, supplier_id=sub["id"]).status_code in (200, 201)


def test_asignacion_sin_persona_ya_no_existe(client, pm_token, proyecto):
    sub = _empresa(client, pm_token, "Sin Persona SA", ["staff_augmentation"])
    r = client.post(f"/api/v1/enterprise/subcontractors/{sub['id']}/assignments", headers=auth(pm_token),
                    json={"project_id": P1})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_asignacion_sin_persona"


def test_el_empleado_no_externaliza(client, dev_token, pm_token, proyecto, db):
    from app.models.project import ProjectMember
    sub = _empresa(client, pm_token, "Out Emp SA", ["outsourcing"])
    db.add(ProjectMember(project_id=P1, user_id="dev-test-id", is_active=True))
    db.commit()
    r = _tarea(client, dev_token, supplier_id=sub["id"])
    assert r.status_code == 403


def test_lectura_para_gestores_escritura_para_admin_y_pm(client, hr_token, sub_token, pm_token):
    sub = _empresa(client, pm_token, "Permisos SA", ["outsourcing"])
    assert client.get(f"{B}/{sub['id']}/profile", headers=auth(hr_token)).status_code == 200
    assert client.post(f"{B}/{sub['id']}/contracts", headers=auth(hr_token), json={"title": "x"}).status_code == 403
    assert client.get(f"{B}/overview", headers=auth(sub_token)).status_code == 403


# ── Paquetes de trabajo ──────────────────────────────────────────────────────

def test_ciclo_del_paquete_rechazo_y_aceptacion_con_uat(client, pm_token, proyecto, db):
    from app.models.client_portal import UATSession, UATStatus
    sub = _empresa(client, pm_token, "Ciclo SA", ["outsourcing"])
    uat = UATSession(id="uat-pv-1", organization_id=1, code="UAT-PV1", project_id=P1, title="UAT")
    db.add(uat)
    db.commit()
    wp = _datos(client.post(f"{B}/{sub['id']}/work-packages", headers=auth(pm_token), json={
        "project_id": P1, "title": "Fase 2", "scope_type": "project", "uat_session_id": "uat-pv-1",
        "planned_end": str(date.today() + timedelta(days=10))}))
    w = wp["id"]
    assert client.post(f"{B}/work-packages/{w}/accept", headers=auth(pm_token)).status_code == 409
    _datos(client.post(f"{B}/work-packages/{w}/start", headers=auth(pm_token)))
    _datos(client.post(f"{B}/work-packages/{w}/deliver", headers=auth(pm_token)))
    sin_motivo = client.post(f"{B}/work-packages/{w}/reject", headers=auth(pm_token), json={})
    assert sin_motivo.status_code == 422
    rech = _datos(client.post(f"{B}/work-packages/{w}/reject", headers=auth(pm_token), json={"reason": "fallos"}))
    assert rech["status"] == "rejected" and rech["rejections"] == 1
    _datos(client.post(f"{B}/work-packages/{w}/deliver", headers=auth(pm_token)))
    pendiente = client.post(f"{B}/work-packages/{w}/accept", headers=auth(pm_token))
    assert pendiente.status_code == 409 and pendiente.json()["code"] == "proveedor_uat_pendiente"
    uat.status = UATStatus.passed
    db.commit()
    ok = _datos(client.post(f"{B}/work-packages/{w}/accept", headers=auth(pm_token)))
    assert ok["status"] == "accepted" and ok["accepted_at"] == str(date.today())


# ── Calculo de cobro (puro) ──────────────────────────────────────────────────

def test_escalado_graduado_y_meses():
    from app.services.proveedores.consumo import meses
    from app.services.proveedores.facturacion import precio_por_tramos
    tramos = [{"from": 0, "to": 100, "price": 10}, {"from": 100, "to": None, "price": 8}]
    assert precio_por_tramos(50, tramos) == 500
    assert precio_por_tramos(150, tramos) == 100 * 10 + 50 * 8
    assert meses(date(2026, 1, 1), date(2026, 1, 31)) == 1.0
    assert meses(date(2026, 1, 1), date(2026, 3, 31)) == 3.0
    assert meses(date(2026, 2, 15), date(2026, 2, 28)) == pytest.approx(14 / 28, abs=1e-4)


def test_tramos_solapados_se_rechazan(client, pm_token):
    sub = _empresa(client, pm_token, "Tramos SA", ["managed_services"])
    c = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token), json={"title": "Servicio"}))
    r = client.post(f"{B}/contracts/{c['id']}/pricing", headers=auth(pm_token), json={
        "model": "per_unit", "unit": "ticket", "tiers": [{"from": 0, "to": 100, "price": 10},
                                                         {"from": 50, "to": None, "price": 8}]})
    assert r.status_code == 422 and r.json()["code"] == "proveedor_tramos_no_validos"


def _servicio_con_tickets(db, client, token, resueltos: int, incumplidos: int):
    """Proveedor de service desk con su cola, cuota con exceso por ticket y credito por SLA."""
    from app.models.service_desk import AgentGroup, Ticket
    from app.models.service_desk._enums import SupportLevel
    sub = _empresa(client, token, "Service Desk Ext SL", ["managed_services"])
    g = AgentGroup(id="grp-pv", organization_id=1, name="Cola proveedor", support_level=SupportLevel.l1)
    db.add(g)
    db.commit()
    c = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(token), json={"title": "SD externalizado"}))
    s = _datos(client.post(f"{B}/{sub['id']}/services", headers=auth(token), json={
        "service_type": "service_desk", "name": "Service desk 24x7", "contract_id": c["id"], "agent_group_id": "grp-pv",
        "sla_target_pct": 95, "credit_rules": [{"below_pct": 95, "credit_pct": 10}]}))
    _datos(client.post(f"{B}/contracts/{c['id']}/pricing", headers=auth(token), json={
        "model": "subscription", "unit": "ticket", "unit_price": 1000, "period": "monthly", "included_units": 2,
        "overage_price": 50, "service_id": s["id"]}))
    for i in range(resueltos):
        creado = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)
        db.add(Ticket(id=f"tk-pv-{i}", number=f"INC-PV{i}", ticket_type="incident", title="t", description="d",
                      organization_id="1", assigned_group_id="grp-pv", created_at=creado,
                      resolved_at=creado + timedelta(hours=4), sla_resolution_breached=i < incumplidos))
    db.commit()
    return sub, c, s


def test_prevision_cuota_con_exceso_y_credito_por_sla(client, pm_token, db):
    sub, c, s = _servicio_con_tickets(db, client, pm_token, resueltos=4, incumplidos=1)
    sla = _datos(client.get(f"{B}/services/{s['id']}/sla", headers=auth(pm_token),
                            params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    assert sla["tickets_resolved"] == 4 and sla["resolution_met_pct"] == 75.0 and sla["met"] is False
    p = _datos(client.get(f"{B}/contracts/{c['id']}/forecast", headers=auth(pm_token),
                          params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    # 1000 de cuota + (4 - 2 incluidos) x 50 = 1100; credito del 10 % por SLA 75 % < 95 %.
    assert p["subtotal"] == 1100.0
    assert p["credits"] == 110.0
    assert p["expected_amount"] == 990.0


def test_minimo_por_linea_minimo_comprometido_y_tope(client, pm_token, db):
    from app.models.proveedores import SupplierContract
    sub = _empresa(client, pm_token, "Minimos SA", ["managed_services"])
    c = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token), json={
        "title": "Con mínimos", "committed_minimum": 800, "minimum_period": "monthly"}))
    _datos(client.post(f"{B}/contracts/{c['id']}/pricing", headers=auth(pm_token), json={
        "model": "per_unit", "unit": "call", "unit_price": 2, "min_amount": 500, "period": "monthly"}))
    p = _datos(client.get(f"{B}/contracts/{c['id']}/forecast", headers=auth(pm_token),
                          params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    assert p["subtotal"] == 500.0          # minimo de la linea (0 llamadas registradas)
    assert p["adjustments"] == 300.0       # hasta el minimo comprometido del contrato
    assert p["expected_amount"] == 800.0
    assert {w["code"] for w in p["warnings"]} >= {"minimo_comprometido", "sin_medicion"}
    db.get(SupplierContract, c["id"]).total_cap = 600
    db.commit()
    p = _datos(client.get(f"{B}/contracts/{c['id']}/forecast", headers=auth(pm_token),
                          params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    assert p["expected_amount"] == 600.0 and any(w["code"] == "tope_alcanzado" for w in p["warnings"])


def test_consumo_registrado_por_unidad(client, pm_token):
    sub = _empresa(client, pm_token, "SOC SA", ["managed_services"])
    c = _datos(client.post(f"{B}/{sub['id']}/contracts", headers=auth(pm_token), json={"title": "SOC"}))
    linea = _datos(client.post(f"{B}/contracts/{c['id']}/pricing", headers=auth(pm_token), json={
        "model": "per_unit", "unit": "device_month", "unit_price": 3}))
    _datos(client.post(f"{B}/{sub['id']}/usage", headers=auth(pm_token), json={
        "pricing_line_id": linea["id"], "period_start": "2026-01-01", "period_end": "2026-01-31", "quantity": 200}))
    p = _datos(client.get(f"{B}/contracts/{c['id']}/forecast", headers=auth(pm_token),
                          params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    assert p["subtotal"] == 600.0  # 200 dispositivos x 1 mes x 3


# ── Estados de cuenta: conciliacion y segregacion ────────────────────────────

def test_cierre_conciliacion_y_segregacion(client, pm_token, admin_token, db):
    from app.models.enterprise import SubcontractorInvoice
    sub, c, _ = _servicio_con_tickets(db, client, pm_token, resueltos=2, incumplidos=0)
    bloqueado = client.post(f"{B}/contracts/{c['id']}/activate", headers=auth(pm_token))
    assert bloqueado.status_code == 409 and bloqueado.json()["code"] == "proveedor_requisitos_grc_pendientes"
    _datos(client.post(f"{B}/{sub['id']}/documents", headers=auth(pm_token),
                       json={"doc_type": "nda", "expires_at": str(date.today() + timedelta(days=365))}))
    _datos(client.post(f"{B}/contracts/{c['id']}/activate", headers=auth(pm_token)))
    st = _datos(client.post(f"{B}/contracts/{c['id']}/statements", headers=auth(pm_token),
                            json={"period_start": "2026-01-01", "period_end": "2026-01-31"}))
    assert st["expected_amount"] == 1000.0 and st["status"] == "closed"
    otra = client.post(f"{B}/contracts/{c['id']}/statements", headers=auth(pm_token),
                       json={"period_start": "2026-01-15", "period_end": "2026-02-15"})
    assert otra.status_code == 409 and otra.json()["code"] == "proveedor_periodo_ya_cerrado"
    fuera = SubcontractorInvoice(id="inv-pv-1", subcontractor_id=sub["id"], invoice_number="F-1",
                                 issue_date=date(2026, 2, 1), amount=1200, total=1452, currency="EUR")
    db.add(fuera)
    db.commit()
    disputado = _datos(client.post(f"{B}/statements/{st['id']}/reconcile", headers=auth(pm_token),
                                   json={"invoice_id": "inv-pv-1"}))
    assert disputado["status"] == "disputed" and disputado["difference"] == 200.0
    fuera.amount = 1010  # 1 % de diferencia: dentro de la tolerancia del 2 %
    db.commit()
    ok = _datos(client.post(f"{B}/statements/{st['id']}/reconcile", headers=auth(pm_token),
                            json={"invoice_id": "inv-pv-1"}))
    assert ok["status"] == "reconciled"
    sod = client.post(f"{B}/statements/{st['id']}/approve", headers=auth(pm_token))
    assert sod.status_code == 409 and sod.json()["code"] == "proveedor_segregacion_aprobacion"
    aprobado = _datos(client.post(f"{B}/statements/{st['id']}/approve", headers=auth(admin_token)))
    assert aprobado["status"] == "approved"
    assert db.get(SubcontractorInvoice, "inv-pv-1").status == "approved"


def test_lo_aprobado_con_proyecto_entra_en_el_coste_sin_las_horas(db):
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierContract, SupplierStatement
    from app.services.proveedores.facturacion import partidas
    s = Subcontractor(id="sub-pv-c", code="SUB-9001", name="Coste SA", organization_id=1)
    c = SupplierContract(id="c-pv-c", subcontractor_id="sub-pv-c", title="c", organization_id=1)
    db.add_all([s, c])
    db.flush()
    db.add(SupplierStatement(subcontractor_id="sub-pv-c", contract_id="c-pv-c", period_start=date(2026, 1, 1),
                             period_end=date(2026, 1, 31), currency="EUR", status="approved", organization_id=1,
                             lines=[{"model": "fixed_price", "amount": 5000, "project_id": P1},
                                    {"model": "per_resource", "amount": 999, "project_id": P1},
                                    {"model": "credit", "amount": -100, "project_id": P1}]))
    db.commit()
    filas = partidas(db, [P1], "EUR")
    assert sorted(x[3] for x in filas) == [-100.0, 5000.0]
    assert all(x[2] == "subcontrata" for x in filas)


# ── GRC de terceros ──────────────────────────────────────────────────────────

def test_requisitos_segun_datos_y_riesgo(client, pm_token):
    sub = _empresa(client, pm_token, "Datos SA", ["managed_services"])
    _datos(client.patch(f"{B}/{sub['id']}/classification", headers=auth(pm_token), json={"data_access": True}))
    c = _datos(client.get(f"{B}/{sub['id']}/compliance", headers=auth(pm_token)))
    assert set(c["missing"]) == {"nda", "dpa_art28"} and c["status"] == "blocked"
    ev = _datos(client.post(f"{B}/{sub['id']}/risk-assessments", headers=auth(pm_token), json={
        "criteria": {"data_access": 5, "criticality": 4, "dependency": 3, "financial": 2, "location": 2,
                     "security": 4}, "due_diligence_done": True}))
    assert ev["level"] in ("high", "critical")
    c = _datos(client.get(f"{B}/{sub['id']}/compliance", headers=auth(pm_token)))
    assert {"security_certification", "insurance"} <= set(c["missing"])
    for tipo in ("nda", "dpa_art28", "iso27001", "insurance_cyber"):
        _datos(client.post(f"{B}/{sub['id']}/documents", headers=auth(pm_token), json={"doc_type": tipo}))
    assert _datos(client.get(f"{B}/{sub['id']}/compliance", headers=auth(pm_token)))["missing"] == []


def test_puntuacion_de_riesgo():
    from app.services.proveedores.grc import puntuar
    assert puntuar({c: 1 for c in ("data_access", "criticality", "dependency", "financial", "location",
                                   "security")}) == (0.0, "low")
    assert puntuar({"data_access": 5, "criticality": 1})[1] == "high"  # un 5 en datos sube a alto
    with pytest.raises(Exception):
        puntuar({"data_access": 7})


def test_acceso_a_datos_personales_exige_declararlo_y_se_revoca(client, pm_token):
    sub = _empresa(client, pm_token, "Accesos SA", ["managed_services"])
    r = client.post(f"{B}/{sub['id']}/access-grants", headers=auth(pm_token),
                    json={"system": "CRM", "personal_data": True})
    assert r.status_code == 409 and r.json()["code"] == "proveedor_sin_acceso_a_datos"
    g = _datos(client.post(f"{B}/{sub['id']}/access-grants", headers=auth(pm_token), json={"system": "SIEM"}))
    rev = _datos(client.post(f"{B}/access-grants/{g['id']}/revoke", headers=auth(pm_token), json={"reason": "fin"}))
    assert rev["active"] is False


def test_baja_completa_del_proveedor(client, pm_token, db):
    from app.models.enterprise import SubcontractorWorker
    r = _freelance(client, pm_token, "Baja Freelance")
    sid = r["supplier"]["id"]
    _datos(client.post(f"{B}/{sid}/access-grants", headers=auth(pm_token), json={"system": "VPN"}))
    baja = _datos(client.post(f"{B}/{sid}/offboard", headers=auth(pm_token), json={"reason": "fin de contrato"}))
    assert baja["lifecycle_status"] == "offboarded"
    assert baja["offboarding"]["workers"] == 1 and baja["offboarding"]["access_grants"] == 1
    assert baja["offboarding"]["contracts"] == 1
    assert db.get(SubcontractorWorker, r["worker"]["id"]).is_active is False
    again = client.post(f"{B}/{sid}/offboard", headers=auth(pm_token), json={})
    assert again.status_code == 409


def test_controles_de_terceros_y_bloqueo_legal(db):
    from app.db.bloqueo_legal import TIPOS
    from app.models.enterprise import Subcontractor
    from app.services.proveedores.grc import controles
    db.add(Subcontractor(id="sub-pv-g", code="SUB-9002", name="GRC SA", organization_id="1", data_access=True,
                         lifecycle_status="active"))
    db.commit()
    medidos = {c[0]: c for c in controles(db, "1")}
    assert set(medidos) == {"third_party_dpa", "third_party_documents", "third_party_reviews", "third_party_access"}
    assert medidos["third_party_dpa"][1] == "attention"
    assert {"supplier_documents", "supplier_access_grants"} <= set(TIPOS)


def test_formacion_interna_solo_con_training_enabled(client, pm_token, db):
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    from app.services.proveedores.asignabilidad import participa_en_desarrollo
    r = _freelance(client, pm_token, "Formacion Freelance")
    w = db.get(SubcontractorWorker, r["worker"]["id"])
    assert participa_en_desarrollo(db, w.user_id) is False
    assert participa_en_desarrollo(db, PM) is True
    db.get(Subcontractor, r["supplier"]["id"]).training_enabled = True
    db.commit()
    assert participa_en_desarrollo(db, w.user_id) is True


def test_rgpd_del_freelance(client, pm_token, db):
    from app.models.enterprise import SubcontractorWorker
    from app.models.user import User
    from app.services.proveedores.grc import datos_personales, suprimir
    r = _freelance(client, pm_token, "Rgpd Freelance")
    w = db.get(SubcontractorWorker, r["worker"]["id"])
    u = db.get(User, w.user_id)
    copia = datos_personales(db, u)
    assert copia["supplier"]["kind"] == "freelance" and copia["worker"]["email"] == "ana.freelance@example.com"
    assert suprimir(db, u) == {"workers": 1, "freelance_supplier": 1}
    assert w.email is None


def test_cuadro_de_mando(client, pm_token, db):
    sub, c, s = _servicio_con_tickets(db, client, pm_token, resueltos=4, incumplidos=0)
    sc = _datos(client.get(f"{B}/{sub['id']}/scorecard", headers=auth(pm_token),
                           params={"desde": "2026-01-01", "hasta": "2026-01-31"}))
    dims = {d["key"]: d for d in sc["dimensions"]}
    assert dims["sla"]["value"] == 100.0
    assert dims["compliance"]["value"] == 0.0  # sin NDA: bloqueado
    assert sc["score"] is not None and sc["tone"] in ("success", "warning", "danger")


def test_catalogos_de_configuracion(client, pm_token):
    tipos = _items(client.get("/api/v1/settings/supplier-service-types", headers=auth(pm_token)))
    unidades = _items(client.get("/api/v1/settings/supplier-billing-units", headers=auth(pm_token)))
    assert {"soc", "service_desk", "payroll"} <= {x["value"] for x in tipos}
    assert {"hour", "ticket", "device_month"} <= {x["value"] for x in unidades}


def test_plantilla_de_contrato_se_copia_con_sus_lineas(client, pm_token):
    sub = _empresa(client, pm_token, "Plantilla SA", ["managed_services"])
    t = _datos(client.post(f"{B}/contract-templates", headers=auth(pm_token),
                           json={"title": "SOC estándar", "contract_type": "service", "modes": ["managed_services"]}))
    _datos(client.post(f"{B}/contracts/{t['id']}/pricing", headers=auth(pm_token), json={
        "model": "subscription", "unit_price": 2500, "period": "monthly"}))
    c = _datos(client.post(f"{B}/{sub['id']}/contracts/from-template/{t['id']}", headers=auth(pm_token)))
    assert c["status"] == "draft" and c["is_template"] is False
    assert [(x["model"], x["unit_price"]) for x in c["lines"]] == [("subscription", 2500)]


# ── Migracion: clasificacion de lo existente ─────────────────────────────────

def _migracion():
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "189_proveedores_y_externalizacion.py"
    spec = importlib.util.spec_from_file_location("migracion_189", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_clasificacion_de_proveedores_existentes():
    m = _migracion()
    assert m.clasificar("Juan Pérez", None, [("w1", "juan perez")], 0) == ("freelance", ["staff_augmentation"], "w1")
    assert m.clasificar("JP Consulting", "12345678Z", [("w1", "Juan")], 0)[0] == "freelance"
    assert m.clasificar("Acme SL", "B12345678", [("w1", "Uno"), ("w2", "Dos")], 1) == (
        "company", ["staff_augmentation", "outsourcing"], None)
    assert m.clasificar("Out SL", "B1", [], 2) == ("company", ["outsourcing"], None)
    assert m.es_nif_de_persona("ES-X1234567L") and not m.es_nif_de_persona("B12345678")
