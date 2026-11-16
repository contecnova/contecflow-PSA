"""Rev. 173: valor ganado único, cartera (intake → fases → proyecto) y plantillas unificadas."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.project import Project, ProjectType
from app.models.task import Task, TaskStatus
from app.models.user import User


@pytest.fixture
def pm(db):
    return db.get(User, "pm-test-id")


def _proyecto(db, **kw):
    p = Project(id=str(uuid.uuid4()), organization_id="1", code=f"EV-{uuid.uuid4().hex[:5]}", name="EVM",
                project_type=ProjectType.development, **kw)
    db.add(p)
    db.commit()
    return p


# ── Valor ganado ─────────────────────────────────────────────────────────────

def test_indicadores_cumplen_sus_identidades():
    from app.services.evm_service import indicadores
    i = indicadores(bac=1000, pv=500, ev=400, ac=500)
    assert i.cpi == 0.8 and i.spi == 0.8
    assert i.cv == -100 and i.sv == -100
    assert i.eac == pytest.approx(500 + 600 / 0.8)
    assert i.vac == pytest.approx(1000 - i.eac)
    assert i.tcpi == pytest.approx(600 / 500)


def test_ev_cuenta_el_avance_real_y_pv_sale_de_la_linea_base(db, pm):
    """Dos tareas de 10 h con presupuesto 1.000: una terminada y otra al 50 %.
    Toda la línea base está en el pasado: PV = BAC."""
    from app.services.baselines_service import crear_linea_base
    from app.services.evm_service import evm_de_proyecto
    hoy = timeutil.today()
    p = _proyecto(db, budget_amount=1000.0, start_date=hoy - timedelta(days=30))
    for estado, avance in ((TaskStatus.done, None), (TaskStatus.in_progress, 50.0)):
        db.add(Task(id=str(uuid.uuid4()), organization_id="1", project_id=p.id, code=f"E-{uuid.uuid4().hex[:6]}",
                    title="t", status=estado, progress_pct=avance, estimated_hours=10,
                    start_date=hoy - timedelta(days=20), due_date=hoy - timedelta(days=10)))
    db.commit()
    crear_linea_base(db, pm, p.id, name="B", description=None, is_initial=True)
    d = evm_de_proyecto(db, p, ac=500.0)
    assert d["pv_source"] == "baseline"
    assert d["bac"] == 1000.0
    assert d["pv"] == 1000.0
    assert d["ev"] == 750.0          # 500 + 50 % de 500
    assert d["cpi"] == 1.5


def test_las_tres_pantallas_dan_el_mismo_evm(db):
    from app.services.portfolio_service import get_evm_quick
    from app.services.profitability_service import calc_project_profitability
    from app.services.project_service import calculate_evm
    p = _proyecto(db, budget_amount=2000.0, start_date=timeutil.today() - timedelta(days=5),
                  end_date_planned=timeutil.today() + timedelta(days=5))
    db.add(Task(id=str(uuid.uuid4()), organization_id="1", project_id=p.id, code="E-1", title="t",
                status=TaskStatus.in_review, estimated_hours=4))
    db.commit()
    ficha, rapida, pnl = calculate_evm(p.id, db), get_evm_quick(db, p.id), calc_project_profitability(p, db)
    assert ficha["ev"] == rapida["ev"] == pnl["ev"]
    assert ficha["pv"] == pnl["pv"]


def test_punto_de_curva_s_es_uno_por_dia(db):
    from app.models.planificacion import EvmSnapshot
    from app.services.evm_service import guardar_punto
    p = _proyecto(db, budget_amount=100.0)
    guardar_punto(db, p)
    guardar_punto(db, p)
    db.commit()
    assert db.query(EvmSnapshot).filter(EvmSnapshot.project_id == p.id).count() == 1


# ── Cartera ──────────────────────────────────────────────────────────────────

def test_intake_puntuacion_fases_y_proyecto(db, pm):
    from app.services import cartera_service as svc
    valor = svc.guardar_criterio(db, pm, {"name": "Valor", "weight": 3})
    riesgo = svc.guardar_criterio(db, pm, {"name": "Riesgo", "weight": 1, "inverse": True})
    svc.guardar_fase(db, pm, {"name": "Idea", "sort_order": 1, "min_score": 60})
    svc.guardar_fase(db, pm, {"name": "Caso de negocio", "sort_order": 2})
    p = svc.guardar(db, pm, {"title": "CRM nuevo", "estimated_budget": 5000, "estimated_hours": 80,
                             "roles_needed": [{"role": "Developer", "hours": 80}],
                             "scores": {valor["id"]: 8, riesgo["id"]: 2}})
    # (3·8 + 1·(10−2)) / 4 / 10 × 100 = 80
    assert p["score"] == 80.0
    p = svc.enviar_a_fase(db, pm, p["id"])
    assert p["status"] == "in_review"
    p = svc.decidir_en_pantalla(db, pm, p["id"], True, None)
    assert (p["status"], p["gate_index"]) == ("in_progress", 1)
    svc.enviar_a_fase(db, pm, p["id"])
    p = svc.decidir_en_pantalla(db, pm, p["id"], True, "ok")
    assert p["status"] == "approved"
    p = svc.convertir_en_proyecto(db, pm, p["id"], {})
    assert p["status"] == "converted" and p["project_id"]
    assert db.get(Project, p["project_id"]).budget_amount == 5000


def test_no_se_envia_por_debajo_del_minimo(db, pm):
    from app.services import cartera_service as svc
    c = svc.guardar_criterio(db, pm, {"name": "Valor", "weight": 1})
    svc.guardar_fase(db, pm, {"name": "Idea", "min_score": 70})
    p = svc.guardar(db, pm, {"title": "Floja", "scores": {c["id"]: 5}})
    with pytest.raises(ErrorDeDominio) as e:
        svc.enviar_a_fase(db, pm, p["id"])
    assert e.value.status_code == 422


def test_capacidad_compara_horas_pedidas_y_libres(db, pm):
    from app.services import cartera_service as svc
    dev = db.get(User, "dev-test-id")
    dev.job_title = "Developer"
    db.commit()
    hoy = timeutil.today()
    p = svc.guardar(db, pm, {"title": "Cap", "wanted_start": hoy, "wanted_end": hoy + timedelta(days=13),
                             "roles_needed": [{"role": "Developer", "hours": 1000}]})
    cap = svc.capacidad(db, pm, p["id"])
    fila = cap["roles"][0]
    assert fila["people"] == 1
    assert fila["capacity_hours"] > 0
    assert fila["gap_hours"] > 0 and cap["fits"] is False


# ── Plantillas unificadas ────────────────────────────────────────────────────

def test_plantilla_con_dependencias_se_aplica_planificada(db, pm):
    from app.models.bookings import TaskDependency
    from app.services.plantillas_de_proyecto import crear, crear_desde_proyecto, instanciar
    t = crear(db, pm, {
        "name": "Implantación",
        "phases": [{"name": "Análisis", "estimated_weeks": 1, "tasks": [
            {"key": "req", "title": "Requisitos", "duration_days": 3},
            {"key": "dis", "title": "Diseño", "duration_days": 2},
        ]}],
        "dependencies": [{"predecessor": "req", "successor": "dis", "dependency_type": "FS"}],
        "roles": [{"role_name": "Analista", "estimated_hours": 40}],
        "documents": [{"name": "Acta de inicio", "is_required": True, "due_week_offset": 0}],
    })
    r = instanciar(db, pm, t.id, {"name": "Cliente X", "start_date": "2026-11-02"})
    assert r["tasks_created"] == 2 and r["dependencies_created"] == 1
    tareas = {x.title: x for x in db.query(Task).filter(Task.project_id == r["project_id"]).all()}
    assert tareas["Diseño"].start_date > tareas["Requisitos"].due_date
    assert db.query(TaskDependency).filter(TaskDependency.successor_id == tareas["Diseño"].id).count() == 1
    vuelta = crear_desde_proyecto(db, pm, r["project_id"], "Copia", None)
    assert vuelta["dependencies_exported"] == 1


def test_la_ruta_de_exportar_ya_no_es_un_simulacro(client, admin_token, db):
    p = _proyecto(db)
    r = client.post(f"/api/v1/projects/{p.id}/export-template", json={"name": "Desde proyecto"},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["data"]["template_id"] != "tpl-123"
