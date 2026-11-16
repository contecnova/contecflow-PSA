"""Externos como internos: dominio (16-11-2026, migracion 178).

Asignar = miembro; terminar = deja de serlo. Una sola fuente de horas: la
imputacion del externo lleva la tarifa del proveedor y alimenta `hours_logged`;
el parte manual es solo para quien no tiene acceso y nunca cuenta dos veces.
Acceso que caduca, ventana de disponibilidad, habilidades en `user_skills` y
conciliacion de facturas.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.enterprise import (
    Notification, Subcontractor, SubcontractorAssignment, SubcontractorInvoice, SubcontractorRate,
    SubcontractorTimeLog, SubcontractorWorker,
)
from app.models.imputation import Imputation
from app.models.project import Project, ProjectMember, ProjectStatus, ProjectType
from app.models.user import User
from app.schemas.enterprise import AssignmentCreate, WorkerCreate, WorkerSkillCreate, WorkerUpdate
from app.services.enterprise_service import subcontratas as svc
from tests.conftest import TEST_PASSWORD, auth

ADMIN, PM = "admin-test-id", "pm-test-id"
HOY = date.today()


@pytest.fixture
def base(db):
    db.add(Project(id="p-x1", organization_id=1, code="PX1", name="PX1", project_type=ProjectType.consulting,
                   status=ProjectStatus.active, pm_id=PM, created_by=ADMIN))
    sub = Subcontractor(id="sub-1", organization_id=1, code="SUB-0001", name="Proveedor Uno", currency="EUR")
    db.add(sub)
    db.flush()
    db.add(SubcontractorRate(id="rate-1", organization_id=1, subcontractor_id="sub-1", description="Senior",
                             cost_rate=60.0, currency="EUR", valid_from=HOY - timedelta(days=60)))
    db.commit()
    return sub


def _admin(db):
    return db.get(User, ADMIN)


def _alta(db, sub, **extra):
    datos = dict(name="Ana Externa", email="ana@prov.com", cost_rate=40.0, internal_owner_id=PM,
                 available_from=HOY - timedelta(days=30), available_until=HOY + timedelta(days=60))
    datos.update(extra)
    return svc.create_worker_with_user(sub, WorkerCreate(**datos), _admin(db), db)


def _asignar(db, sub, worker_id, **extra):
    datos = dict(project_id="p-x1", worker_id=worker_id, rate_id="rate-1", hours_contracted=10,
                 start_date=HOY - timedelta(days=20), end_date=HOY + timedelta(days=30))
    datos.update(extra)
    return svc.create_subcontractor_assignment(sub.id, AssignmentCreate(**datos), _admin(db), db)


def test_alta_exige_responsable_interno(db, base):
    from app.core.errores import ErrorDeDominio
    with pytest.raises(ErrorDeDominio):
        _alta(db, base, internal_owner_id=None)


def test_alta_con_y_sin_acceso(db, base):
    con = _alta(db, base)
    assert con["temp_password"] and con["login_username"] and con["has_access"]
    assert con["access_until"] == str(HOY + timedelta(days=60))  # por defecto, disponible hasta
    sin = _alta(db, base, name="Luis Sinacceso", email="luis@prov.com", has_access=False)
    assert "temp_password" not in sin and sin["login_username"] is None
    u = db.get(User, sin["user_id"])
    assert u.hashed_password is None and u.is_active and u.role == "subcontractor"
    assert u.external_company == "Proveedor Uno"


def test_asignar_crea_miembro_y_terminar_lo_quita(db, base):
    w = _alta(db, base)
    r = _asignar(db, base, w["id"], member_role="qa", allocation_pct=50)
    m = db.get(ProjectMember, r["project_member_id"])
    assert m.user_id == w["user_id"] and m.is_active and m.allocation_pct == 50 and m.role.value == "qa"
    svc.end_subcontractor_assignment(None, r["id"], None, _admin(db), db)
    db.expire_all()
    assert db.get(ProjectMember, r["project_member_id"]).is_active is False
    assert db.get(SubcontractorAssignment, r["id"]).is_active is False


def test_tarifa_de_otro_proveedor_no_vale(db, base):
    from app.core.errores import ErrorDeDominio
    db.add(Subcontractor(id="sub-2", organization_id=1, code="SUB-0002", name="Otro"))
    db.flush()
    db.add(SubcontractorRate(id="rate-2", organization_id=1, subcontractor_id="sub-2", description="x", cost_rate=1))
    db.commit()
    w = _alta(db, base)
    with pytest.raises(ErrorDeDominio):
        _asignar(db, base, w["id"], rate_id="rate-2")


def test_imputacion_del_externo_cuesta_su_tarifa_y_suma_a_la_asignacion(client, db, base):
    w = _alta(db, base)
    r = _asignar(db, base, w["id"])
    tok = client.post("/api/v1/auth/login", json={"username": w["login_username"], "password": w["temp_password"]})
    assert tok.status_code == 200, tok.text
    h = auth(tok.cookies.get("access_token"))
    imp = client.post("/api/v1/imputations", headers=h,
                      json={"project_id": "p-x1", "date": str(HOY), "hours": 9, "description": "trabajo"})
    assert imp.status_code in (200, 201), imp.text
    db.expire_all()
    fila = db.query(Imputation).filter(Imputation.user_id == w["user_id"]).one()
    assert fila.cost_amount == pytest.approx(9 * 60.0)  # tarifa del proveedor, no la del trabajador
    a = db.get(SubcontractorAssignment, r["id"])
    assert a.hours_logged == pytest.approx(9)
    # 90 % >= umbral (80 %): aviso al responsable interno / PM, una vez
    avisos = db.query(Notification).filter(Notification.type == "budget_warning").all()
    assert {n.user_id for n in avisos} == {PM}
    assert a.consumption_alert_pct == 80.0
    # Terminada la asignacion, ya no imputa ahi
    svc.end_subcontractor_assignment(None, r["id"], None, _admin(db), db)
    otra = client.post("/api/v1/imputations", headers=h,
                       json={"project_id": "p-x1", "date": str(HOY - timedelta(days=1)), "hours": 1})
    assert otra.status_code == 403, otra.text


def test_parte_manual_solo_sin_acceso_y_sin_doble_coste(db, base):
    from app.core.errores import ErrorDeDominio
    from app.services.costes_de_proyecto import costes_externos
    con = _alta(db, base)
    rc = _asignar(db, base, con["id"])
    with pytest.raises(ErrorDeDominio):
        svc.create_timelog(base.id, {"assignment_id": rc["id"], "log_date": str(HOY), "hours": 2}, db)
    sin = _alta(db, base, name="Luis Sinacceso", email="luis@prov.com", has_access=False)
    rs = _asignar(db, base, sin["id"])
    svc.create_timelog(base.id, {"assignment_id": rs["id"], "log_date": str(HOY), "hours": 3}, db)
    db.expire_all()
    assert db.get(SubcontractorAssignment, rs["id"]).hours_logged == pytest.approx(3)
    assert costes_externos(db, "p-x1", "EUR")["subcontrata"] == pytest.approx(180.0)
    # Si esa persona tiene una imputacion ese dia en el proyecto, el parte no cuenta
    db.add(Imputation(user_id=sin["user_id"], project_id="p-x1", date=HOY, hours=3, cost_amount=180.0))
    db.commit()
    assert costes_externos(db, "p-x1", "EUR")["subcontrata"] == 0
    db.expire_all()
    assert db.get(SubcontractorAssignment, rs["id"]).hours_logged == pytest.approx(3)


def test_sin_acceso_o_caducado_no_entra(client, db, base):
    w = _alta(db, base)
    login = {"username": w["login_username"], "password": w["temp_password"]}
    tok = client.post("/api/v1/auth/login", json=login)
    assert tok.status_code == 200
    h = auth(tok.cookies.get("access_token"))
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    svc.update_worker(w["id"], WorkerUpdate(access_until=HOY - timedelta(days=1)), db, _admin(db))
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert client.post("/api/v1/auth/login", json=login).status_code == 401


def test_caducidad_avisa_antes_y_quita_el_acceso(db, base):
    from app.services.externos.ciclo import caducar_accesos
    w = _alta(db, base, access_until=HOY + timedelta(days=5))
    r = caducar_accesos(db, None, HOY)
    db.commit()  # como el trabajo diario (`en_cada_organizacion`)
    assert r["avisados"] == 1
    assert db.query(Notification).filter(Notification.type == "system").count() == 2
    assert caducar_accesos(db, None, HOY)["avisados"] == 0  # una sola vez
    r = caducar_accesos(db, None, HOY + timedelta(days=6))
    assert r["caducados"] == 1
    assert db.get(SubcontractorWorker, w["id"]).has_access is False


def test_baja_termina_asignaciones_y_desactiva(db, base):
    w = _alta(db, base)
    r = _asignar(db, base, w["id"])
    svc.delete_worker(w["id"], db, _admin(db))
    db.expire_all()
    assert db.get(User, w["user_id"]).is_active is False
    assert db.get(ProjectMember, r["project_member_id"]).is_active is False


def test_habilidades_en_user_skills_y_smartmatch_las_ve(db, base):
    from app.models.resources import Skill, SkillCategory, UserSkill
    from app.services.billing_reports_service.smartmatch import smartmatch
    db.add(Skill(id="sk-k8s", name="Kubernetes", category=SkillCategory.technical))
    db.commit()
    w = _alta(db, base)
    svc.add_worker_skill(w["id"], WorkerSkillCreate(skill_id="sk-k8s", level="expert"), db)
    assert db.query(UserSkill).filter(UserSkill.user_id == w["user_id"]).one().level.value == "expert"
    res = smartmatch({"skills": ["kubernetes"], "hours_needed": 20}, db)
    assert res["candidates"][0]["user_id"] == w["user_id"]


def test_ventana_limita_reservas_y_calendario(db, base):
    from app.core.errores import ErrorDeDominio
    from app.services.bookings_service.reservas import comprobar_capacidad
    from app.services.planificador.calendario import cargar_calendarios
    w = _alta(db, base, available_until=HOY + timedelta(days=10))
    with pytest.raises(ErrorDeDominio):
        comprobar_capacidad(db, w["user_id"], HOY, HOY + timedelta(days=20), 8, "hard")
    _emp, cals = cargar_calendarios(db, 1, [w["user_id"]], HOY)
    fuera = HOY + timedelta(days=14)
    assert not cals[w["user_id"]].es_laborable(fuera)
    from app.services.resource_analytics import get_user_week_hours
    lunes = fuera - timedelta(days=fuera.weekday())
    assert get_user_week_hours(db, w["user_id"], lunes)["out_of_contract_hours"] > 0


def test_conciliacion_de_facturas(db, base):
    sin = _alta(db, base, has_access=False)
    r = _asignar(db, base, sin["id"])
    svc.create_timelog(base.id, {"assignment_id": r["id"], "log_date": str(HOY - timedelta(days=2)), "hours": 5}, db)
    db.add(SubcontractorInvoice(id="inv-1", organization_id=1, subcontractor_id="sub-1", assignment_id=r["id"],
                                invoice_number="F-1", issue_date=HOY, amount=400.0, total=484.0, currency="EUR"))
    db.commit()
    fila = svc.reconcile_invoices("sub-1", db)[0]
    assert fila["expected_amount"] == pytest.approx(300.0) and fila["difference"] == pytest.approx(100.0)


def test_no_se_crea_un_externo_suelto_desde_usuarios(client, admin_token):
    r = client.post("/api/v1/users", headers=auth(admin_token), json={
        "username": "suelto", "email": "suelto@x.com", "full_name": "Suelto", "role": "subcontractor",
        "password": TEST_PASSWORD + "Aa1!"})
    assert r.status_code == 400, r.text


def test_migracion_nivel_de_habilidad():
    import importlib.util
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1] / "alembic/versions/178_externos_como_internos.py"
    spec = importlib.util.spec_from_file_location("mig178", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert (m.nivel("beginner"), m.nivel("EXPERT"), m.nivel(None)) == ("basic", "expert", "intermediate")
