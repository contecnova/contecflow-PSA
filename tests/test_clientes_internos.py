"""Clientes internos: showback, chargeback, portal interno y gobierno (rev. 193).

Ver docs/CLIENTES_INTERNOS.md. Lo que se mide:
- validación de la ficha (tipo, subtipo, modo, método, intercompañía, tarifa);
- miembros deducidos de RR. HH. (sin altas) y papeles;
- coste por fuente (horas, precio cerrado, catálogo, reparto);
- cargos: borrador, emisión, exceso de presupuesto con aprobación y
  segregación, exportación CSV, anulación;
- portal acotado a las unidades de quien llama;
- retención, controles de cumplimiento, capacidades y tipo de aprobación.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.core.errores import ErrorDeDominio
from tests.conftest import auth

B = "/api/v1/internal-clients"
P = "/api/v1/internal-portal"


def _usuario(db, username):
    from app.models.user import User
    return db.query(User).filter(User.username == username).first()


def _departamento(db, nombre="Marketing", manager_id=None):
    from app.models.settings import Department
    d = Department(organization_id="1", name=nombre, manager_id=manager_id)
    db.add(d)
    db.commit()
    return d


def _unidad(db, **kw):
    from app.models.clients import Client
    datos = {"organization_id": "1", "name": "Marketing", "kind": "interno", "internal_type": "departamento",
             "finance_mode": "chargeback", "cost_method": "horas_coste", "is_active": True}
    datos.update(kw)
    c = Client(**datos)
    db.add(c)
    db.commit()
    return c


def _proyecto(db, unidad, **kw):
    from app.models.project import Project
    datos = {"organization_id": "1", "code": "INT-1", "name": "Web interna", "project_type": "internal",
             "client_id": unidad.id}
    datos.update(kw)
    p = Project(**datos)
    db.add(p)
    db.commit()
    return p


def _imputar(db, user, proyecto, horas, coste, dia):
    from app.models.imputation import Imputation
    db.add(Imputation(organization_id="1", user_id=user.id, project_id=proyecto.id, date=dia, hours=horas,
                      cost_amount=coste))
    db.commit()


# ── Validación ───────────────────────────────────────────────────────────────

def test_validar_ficha():
    from app.services.clientes_internos.unidades import validar
    assert validar({"name": "X"})  # sin kind: externo, sin campos internos
    d = validar({"kind": "externo", "finance_mode": "chargeback"})
    assert d["finance_mode"] is None
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "otro"})
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "internal_type": "planeta"})
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "finance_mode": "intercompania"}, org_id="1")
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "finance_mode": "intercompania", "group_organization_id": "1"}, org_id="1")
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "cost_method": "tarifa_interna"})
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "transfer_markup_pct": 5000})
    d = validar({"kind": "interno"})
    assert d["finance_mode"] == "showback" and d["cost_method"] == "horas_coste"


def test_clientes_existentes_son_externos(db, client, admin_token):
    r = client.post("/api/v1/clients", json={"name": "Cliente de fuera"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["kind"] == "externo"
    r = client.post("/api/v1/clients", json={"name": "Finanzas", "kind": "interno", "internal_type": "departamento"},
                    headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["kind"] == "interno"
    internos = client.get("/api/v1/clients?kind=interno", headers=auth(admin_token)).json()["items"]
    assert [c["name"] for c in internos] == ["Finanzas"]


# ── Miembros y papeles ───────────────────────────────────────────────────────

def test_miembros_deducidos_y_papeles(db):
    from app.services.clientes_internos import unidades as U
    jefe = _usuario(db, "pm_test")
    empleado = _usuario(db, "dev_test")
    dep = _departamento(db, "Marketing", manager_id=jefe.id)
    empleado.department = "Marketing"
    db.commit()
    u = _unidad(db, department_id=dep.id)
    ids = U.miembros_ids(db, u)
    assert empleado.id in ids and jefe.id in ids
    assert U.papel(db, jefe, u) == "responsable"
    assert U.papel(db, empleado, u) == "miembro"
    hr = _usuario(db, "hr_test")
    assert U.papel(db, hr, u) is None  # ni de la unidad ni dirección
    U.designar(db, jefe, u.id, empleado.id, "usuario_clave")
    assert U.papel(db, empleado, u) == "usuario_clave"
    assert "interno_sin_responsable" not in U.avisos(db, u) or u.business_owner_id is None


# ── Coste ────────────────────────────────────────────────────────────────────

def test_coste_por_fuentes(db):
    from app.models.clientes_internos import InternalSharedCost
    from app.services.clientes_internos import costes as C
    empleado = _usuario(db, "dev_test")
    dep = _departamento(db)
    empleado.department = "Marketing"
    db.commit()
    u = _unidad(db, department_id=dep.id)
    p = _proyecto(db, u)
    _imputar(db, empleado, p, 10, 400.0, date(2026, 3, 10))
    _imputar(db, empleado, p, 5, 200.0, date(2026, 4, 2))  # fuera del periodo
    cerrado = _proyecto(db, u, code="INT-2", name="Cerrado", billing_type="fixed_price", contract_amount=1200,
                        start_date=date(2026, 1, 1), end_date_planned=date(2026, 12, 31))
    _imputar(db, empleado, cerrado, 8, 320.0, date(2026, 3, 5))  # precio cerrado: no suma horas
    db.add(InternalSharedCost(organization_id="1", name="Red", monthly_amount=300, criterion="usuarios"))
    db.commit()
    r = C.coste(db, u, date(2026, 3, 1), date(2026, 3, 31))
    assert r["by_source"]["horas"] == 400.0
    assert r["by_source"]["precio_cerrado"] == 100.0  # 1200 / 12 meses
    assert r["by_source"]["reparto"] == 300.0         # única unidad: todo el servicio
    assert r["total"] == pytest.approx(800.0)


def test_reparto_fijo_debe_sumar_100(db):
    from app.services.clientes_internos import costes as C
    admin = _usuario(db, "admin")
    u = _unidad(db)
    with pytest.raises(ErrorDeDominio):
        C.guardar_servicio(db, admin, {"name": "ERP", "monthly_amount": 100, "criterion": "fijo",
                                       "fixed_shares": {u.id: 60}})
    s = C.guardar_servicio(db, admin, {"name": "ERP", "monthly_amount": 100, "criterion": "fijo",
                                       "fixed_shares": {u.id: 100}})
    assert C.reparto_de_servicio(db, admin, s["id"], "2026-03")["shares"][0]["amount"] == 100.0


# ── Cargos ───────────────────────────────────────────────────────────────────

def _con_coste(db):
    empleado = _usuario(db, "dev_test")
    u = _unidad(db, erp_account="6290001")
    p = _proyecto(db, u)
    _imputar(db, empleado, p, 10, 500.0, date(2026, 3, 10))
    return u


def test_cargo_borrador_emision_y_exportacion(db):
    from app.services.clientes_internos import cargos as K
    admin = _usuario(db, "admin")
    u = _con_coste(db)
    c = K.generar(db, admin, u.id, "2026-03")
    assert c["status"] == "borrador" and c["number"].startswith("NC-202603-") and c["total"] == 500.0
    with pytest.raises(ErrorDeDominio):
        K.generar(db, admin, u.id, "2026-03")  # uno vivo por unidad y mes
    assert K.emitir(db, admin, c["id"])["status"] == "emitido"  # sin presupuesto: no hay exceso
    with pytest.raises(ErrorDeDominio):
        K.exportar(db, admin, "2026-03")  # sin cuenta de TI (ajuste por empresa) no hay asiento
    from app.services.settings_service import set_runtime_value
    set_runtime_value(db, "presupuestos", "INTERNAL_IT_ERP_ACCOUNT", "7050000", "1")
    csv = K.exportar(db, admin, "2026-03")
    assert "6290001" in csv and "7050000" in csv and "500.00" in csv
    assert K.cargo_dict(db, K.cargo_o_404(db, c["id"]))["status"] == "exportado"
    with pytest.raises(ErrorDeDominio):
        K.anular(db, admin, c["id"])


def test_exceso_de_presupuesto_exige_responsable_y_segregacion(db):
    from app.models.mfa import Budget
    from app.services.clientes_internos import cargos as K
    admin = _usuario(db, "admin")
    responsable = _usuario(db, "pm_test")
    u = _con_coste(db)
    u.business_owner_id = responsable.id
    db.add(Budget(organization_id="1", name="Marketing 2026", year=2026, total_amount=100, cliente_id=u.id,
                  estado="aprobado"))
    db.commit()
    c = K.generar(db, admin, u.id, "2026-03")
    assert K.emitir(db, admin, c["id"])["status"] == "por_aprobar"
    with pytest.raises(ErrorDeDominio):
        K.decidir(db, admin, c["id"], True)  # quien generó y emitió no aprueba
    with pytest.raises(ErrorDeDominio):
        K.decidir(db, _usuario(db, "hr_test"), c["id"], True)  # no es el responsable
    assert K.decidir(db, responsable, c["id"], True)["status"] == "emitido"


def test_tipo_de_aprobacion_registrado():
    from app.services.approval_engine import fuentes
    from app.services.approval_engine._base import _FINANCIAL_ENTITY_TYPES
    assert "internal_charge" in fuentes.TIPOS and "internal_charge" in _FINANCIAL_ENTITY_TYPES


# ── Portal interno ───────────────────────────────────────────────────────────

def test_portal_acotado_a_mis_unidades(db, client, dev_token, hr_token):
    empleado = _usuario(db, "dev_test")
    dep = _departamento(db)
    empleado.department = "Marketing"
    db.commit()
    u = _unidad(db, department_id=dep.id)
    otra = _unidad(db, name="Ventas")
    yo = client.get(f"{P}/me", headers=auth(dev_token)).json()["data"]
    assert yo["enabled"] and [x["id"] for x in yo["units"]] == [u.id]
    assert yo["units"][0]["can_see_costs"] is False
    assert client.get(f"{P}/units/{u.id}/projects", headers=auth(dev_token)).status_code == 200
    assert client.get(f"{P}/units/{otra.id}/projects", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{P}/units/{u.id}/cost", headers=auth(dev_token)).status_code == 403  # miembro: sin costes
    r = client.post(f"{P}/units/{u.id}/satisfaction", json={"score": 9}, headers=auth(dev_token))
    assert r.status_code == 201, r.text
    assert client.post(f"{P}/units/{u.id}/satisfaction", json={"score": 9},
                       headers=auth(dev_token)).status_code == 409  # una por mes
    r = client.post(f"{P}/units/{u.id}/requests", json={"title": "Nueva intranet", "kind": "proyecto"},
                    headers=auth(dev_token))
    assert r.status_code == 201, r.text
    assert client.get(f"{P}/me", headers=auth(hr_token)).json()["data"]["enabled"] is False


def test_firma_de_uat_por_usuario_clave(db):
    from app.models.client_portal import UATSession
    from app.services.clientes_internos import portal, unidades as U
    empleado = _usuario(db, "dev_test")
    u = _unidad(db)
    p = _proyecto(db, u)
    U.designar(db, _usuario(db, "admin"), u.id, empleado.id, "usuario_clave")
    s = UATSession(organization_id="1", code="UAT-001", project_id=p.id, title="Pruebas")
    db.add(s)
    db.commit()
    r = portal.firmar_uat(db, empleado, s.id, "passed", "ok")
    assert r["signed"] and db.get(UATSession, s.id).internal_signed_by == empleado.id
    with pytest.raises(ErrorDeDominio):
        portal.firmar_uat(db, empleado, s.id, "passed", None)


# ── GRC ──────────────────────────────────────────────────────────────────────

def test_retencion_y_controles(db):
    from app.db.bloqueo_legal import TIPOS
    from app.services.clientes_internos.cumplimiento import controles
    assert {"internal_satisfaction", "internal_client_roles", "internal_charges"} <= set(TIPOS)
    _unidad(db, finance_mode="chargeback")
    ids = {c["id"]: c["status"] for c in controles(db, "1", lambda i, e, m, f, mk: {"id": i, "status": e})}
    assert ids["internal_units_owner"] == "attention"
    assert ids["internal_chargeback_erp"] == "attention"
    assert ids["internal_charges_sod"] == "info"


def test_capacidades():
    from app.core.capacidades import CAPACIDADES
    assert "employee" in CAPACIDADES["interno.portal"].roles
    assert "subcontractor" not in CAPACIDADES["interno.portal"].roles
    assert CAPACIDADES["interno.gestionar"].roles == ("admin", "pm")
    assert CAPACIDADES["interno.cargos"].roles == ("admin",)


def test_guardas(client, dev_token, pm_token):
    assert client.get(f"{B}/overview", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{B}/overview", headers=auth(pm_token)).status_code == 200
    assert client.get(f"{B}/shared-costs", headers=auth(pm_token)).status_code == 403


# ── Ajuste de la cuenta de TI, precio del catálogo y filtro externos/internos ─

def test_cuenta_de_ti_se_valida(db):
    from app.services.settings_service import set_runtime_value
    from app.core.codigos_de_error import ErrorConCodigo
    with pytest.raises(ErrorConCodigo):
        set_runtime_value(db, "presupuestos", "INTERNAL_IT_ERP_ACCOUNT", "cuenta;DROP", "1")
    with pytest.raises(ErrorConCodigo):
        set_runtime_value(db, "presupuestos", "INTERNAL_IT_ERP_ACCOUNT", "x" * 41, "1")
    set_runtime_value(db, "presupuestos", "INTERNAL_IT_ERP_ACCOUNT", " CC-TI/01 ", "1")
    from app.services.clientes_internos.cargos import cuenta_de_ti
    assert cuenta_de_ti(db, "1") == "CC-TI/01"


def test_cuenta_erp_de_la_unidad_se_valida():
    from app.services.clientes_internos.unidades import validar
    with pytest.raises(ErrorDeDominio):
        validar({"kind": "interno", "erp_account": "mal;valor"})
    assert validar({"kind": "interno", "erp_account": " 629.0001 "})["erp_account"] == "629.0001"


def test_filtro_externos_internos(db, client, pm_token):
    from app.models.clients import Client
    from app.models.portfolio import PortfolioProposal
    from app.services.clientes_internos.unidades import filtrar_proyectos
    u = _unidad(db)
    externo = Client(organization_id="1", name="Fuera", is_active=True)
    db.add(externo)
    db.commit()
    p_int = _proyecto(db, u)
    p_ext = _proyecto(db, externo, code="EXT-1", name="Externo")
    p_sin = _proyecto(db, u, code="SIN-1", name="Sin cliente", client_id=None)
    assert [p.id for p in filtrar_proyectos(db, [p_int, p_ext, p_sin], "interno")] == [p_int.id]
    assert {p.id for p in filtrar_proyectos(db, [p_int, p_ext, p_sin], "externo")} == {p_ext.id, p_sin.id}
    db.add_all([PortfolioProposal(organization_id="1", title="De la unidad", client_id=u.id, status="draft"),
                PortfolioProposal(organization_id="1", title="De fuera", client_id=externo.id, status="draft")])
    db.commit()
    r = client.get("/api/v1/portfolio-intake/proposals?client_kind=interno", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    filas = r.json().get("items") or r.json().get("data") or []
    assert [f["title"] for f in filas] == ["De la unidad"] and filas[0]["client_kind"] == "interno"
    assert client.get("/api/v1/dashboard/projects-health?client_kind=interno", headers=auth(pm_token)).status_code == 200
    assert client.get("/api/v1/profitability/summary?client_kind=externo", headers=auth(pm_token)).status_code == 200


def test_precio_interno_del_catalogo_cuenta(db):
    from app.models.service_desk.catalog import ServiceCategory, ServiceItem
    from app.models.service_desk.tickets import Ticket
    from app.models.service_desk._enums import TicketType
    from app.services.clientes_internos import costes as C
    from datetime import datetime, timezone
    u = _unidad(db)
    cat = ServiceCategory(organization_id="1", name="Puestos")
    db.add(cat)
    db.flush()
    s = ServiceItem(organization_id="1", category_id=cat.id, name="Alta de portátil", internal_price=150)
    db.add(s)
    db.flush()
    db.add(Ticket(organization_id="1", number="REQ-1", title="Portátil", description="Alta",
                  ticket_type=TicketType.service_request,
                  client_id=u.id, service_item_id=s.id,
                  resolved_at=datetime(2026, 3, 15, tzinfo=timezone.utc)))
    db.commit()
    assert C.coste(db, u, date(2026, 3, 1), date(2026, 3, 31))["by_source"]["catalogo"] == 150.0
