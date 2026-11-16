"""Planificador (rev. 173) contra la base: dependencias únicas, CPM guardado,
línea base vigente en /tasks, cascada con los cuatro tipos, nivelación y vistas."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.core import timeutil
from app.models.bookings import DependencyType, TaskDependency
from app.models.project import Project, ProjectType
from app.models.task import Task, TaskStatus
from app.models.user import User


def _lunes_siguiente() -> date:
    hoy = timeutil.today()
    return hoy + timedelta(days=(7 - hoy.weekday()) % 7 or 7)


@pytest.fixture
def pm(db):
    return db.get(User, "pm-test-id")


@pytest.fixture
def proyecto(db):
    p = Project(id=str(uuid.uuid4()), organization_id="1", code=f"PL-{uuid.uuid4().hex[:5]}",
                name="Plan", project_type=ProjectType.development, start_date=_lunes_siguiente())
    db.add(p)
    db.commit()
    return p


def _tarea(db, p, titulo, dias, **kw):
    inicio = kw.pop("inicio", p.start_date)
    t = Task(id=str(uuid.uuid4()), organization_id="1", project_id=p.id,
             code=f"T-{uuid.uuid4().hex[:6]}", title=titulo, status=kw.pop("status", TaskStatus.todo),
             start_date=inicio, due_date=inicio + timedelta(days=dias - 1), **kw)
    db.add(t)
    db.commit()
    return t


def _dep(db, a, b, tipo=DependencyType.finish_to_start, lag=0, link="schedule"):
    db.add(TaskDependency(organization_id="1", predecessor_id=a.id, successor_id=b.id,
                          dependency_type=tipo, lag_days=lag, link_type=link, is_active=True))
    db.commit()


# ── Dependencias: un solo modelo ─────────────────────────────────────────────

def test_blocked_by_se_guarda_como_fs_al_reves(db, proyecto, pm):
    from app.services.task_service import create_task_dependency
    a, b = _tarea(db, proyecto, "A", 1), _tarea(db, proyecto, "B", 1)
    d = create_task_dependency(db, a.id, b.id, "blocked_by", 0, pm.id)
    assert (d["predecessor_id"], d["successor_id"], d["dependency_type"]) == (b.id, a.id, "FS")
    assert d["link_type"] == "schedule"


def test_vinculo_informativo_no_planifica_ni_cierra_ciclos(db, proyecto, pm):
    from app.services.task_service import create_task_dependency
    a, b = _tarea(db, proyecto, "A", 1), _tarea(db, proyecto, "B", 1)
    create_task_dependency(db, a.id, b.id, "FS", 0, pm.id)
    d = create_task_dependency(db, b.id, a.id, "relates_to", 0, pm.id)   # no es un ciclo
    assert d["link_type"] == "relates_to"


def test_actualizar_dependencia_cambia_tipo_y_desfase(db, proyecto, pm):
    from app.services.task_service import create_task_dependency, update_task_dependency
    a, b = _tarea(db, proyecto, "A", 1), _tarea(db, proyecto, "B", 1)
    d = create_task_dependency(db, a.id, b.id, "FS", 0, pm.id)
    d2 = update_task_dependency(db, d["id"], {"dependency_type": "SS", "lag_days": 2})
    assert (d2["dependency_type"], d2["lag_days"]) == ("SS", 2)


def test_la_api_duplicada_de_dependencias_ya_no_existe(client, admin_token):
    r = client.get("/api/v1/task-dependencies/x", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code in (404, 405)


# ── CPM guardado y /tasks ───────────────────────────────────────────────────

def test_calcular_plan_guarda_critica_y_holgura(db, proyecto, pm):
    from app.services.planificador.servicio import calcular_plan
    a = _tarea(db, proyecto, "A", 3)
    b = _tarea(db, proyecto, "B", 2)
    c = _tarea(db, proyecto, "C", 1)
    _dep(db, a, b)
    plan = calcular_plan(db, pm, proyecto.id)
    nodos = {n["id"]: n for n in plan["nodes"]}
    assert nodos[a.id]["is_critical"] and nodos[b.id]["is_critical"]
    assert not nodos[c.id]["is_critical"] and nodos[c.id]["total_float"] == 4
    db.expire_all()
    assert db.get(Task, a.id).is_critical is True
    assert db.get(Task, c.id).total_float_days == 4


def test_tasks_devuelve_critica_holgura_y_linea_base(client, admin_token, db, proyecto, pm):
    from app.services.baselines_service import crear_linea_base
    from app.services.planificador.servicio import calcular_plan
    a = _tarea(db, proyecto, "A", 2)
    calcular_plan(db, pm, proyecto.id)
    crear_linea_base(db, pm, proyecto.id, name="Inicial", description=None, is_initial=True)
    r = client.get(f"/api/v1/tasks?project_id={proyecto.id}", headers={"Authorization": f"Bearer {admin_token}"})
    fila = next(t for t in r.json()["items"] if t["id"] == a.id)
    assert fila["is_critical"] is True
    assert fila["total_float_days"] == 0
    assert fila["baseline_start"] == a.start_date.isoformat()
    assert fila["baseline_end"] == a.due_date.isoformat()


def test_lineas_base_vigente_y_comparar_dos(db, proyecto, pm):
    from app.services import baselines_service as svc
    t = _tarea(db, proyecto, "A", 2)
    b1 = svc.crear_linea_base(db, pm, proyecto.id, name="B1", description=None, is_initial=True)
    assert b1.is_current
    t.due_date = t.due_date + timedelta(days=3)
    db.commit()
    b2 = svc.crear_linea_base(db, pm, proyecto.id, name="B2", description=None, is_initial=False)
    assert not b2.is_current
    svc.marcar_vigente(db, pm, proyecto.id, b2.id)
    db.refresh(b1)
    assert not b1.is_current
    cmp = svc.comparar_con_linea_base(db, pm, proyecto.id, b1.id, against_id=b2.id)
    assert cmp["summary"]["tasks_slipped"] == 1
    assert cmp["summary"]["max_slip_days"] == 3


# ── Cascada con los cuatro tipos ─────────────────────────────────────────────

def test_cascada_sigue_un_vinculo_ss_con_desfase(db, proyecto):
    from app.services.tasks.scheduling import cascade_reschedule
    a = _tarea(db, proyecto, "A", 5)
    b = _tarea(db, proyecto, "B", 2)
    _dep(db, a, b, DependencyType.start_to_start, lag=1)
    # Mover el fin de A una semana mueve su inicio (misma duración) y empuja a B.
    cascade_reschedule(a.id, a.due_date + timedelta(days=7), db)
    db.expire_all()
    a2, b2 = db.get(Task, a.id), db.get(Task, b.id)
    assert a2.start_date == proyecto.start_date + timedelta(days=7)
    assert b2.start_date == a2.start_date + timedelta(days=1)


def test_cascada_no_mueve_una_sucesora_que_ya_cumple(db, proyecto):
    from app.services.tasks.scheduling import cascade_reschedule
    a = _tarea(db, proyecto, "A", 1)
    b = _tarea(db, proyecto, "B", 1, inicio=proyecto.start_date + timedelta(days=14))
    _dep(db, a, b)
    r = cascade_reschedule(a.id, a.due_date + timedelta(days=1), db)
    assert [m["task_id"] for m in r["rescheduled"]] == [a.id]


# ── Nivelación ───────────────────────────────────────────────────────────────

def test_nivelacion_mueve_la_tarea_con_holgura(db, proyecto, pm):
    from app.services.planificador import nivelacion
    # «Otra» (de otra persona) marca el fin del proyecto a dos semanas: las dos
    # tareas de dev tienen holgura. El lunes dev tiene 16 h (Larga 8 + Corta 8);
    # la semana entera la ocupa Larga, así que Corta tiene que ir al lunes siguiente.
    _tarea(db, proyecto, "Otra", 10, assignee_id="pm-test-id", estimated_hours=10)
    _tarea(db, proyecto, "Larga", 5, assignee_id="dev-test-id", estimated_hours=40)
    corta = _tarea(db, proyecto, "Corta", 1, assignee_id="dev-test-id", estimated_hours=8)
    propuesta = nivelacion.proponer(db, pm, proyecto.id)
    assert propuesta["overallocations_before"]
    assert [m["task_id"] for m in propuesta["moves"]] == [corta.id]
    assert not propuesta["overallocations_after"]
    db.expire_all()
    assert db.get(Task, corta.id).start_date == proyecto.start_date   # proponer no escribe
    nivelacion.aplicar(db, pm, proyecto.id)
    db.expire_all()
    assert db.get(Task, corta.id).start_date > proyecto.start_date


# ── Vistas guardadas ─────────────────────────────────────────────────────────

def test_vistas_propias_y_compartidas(db, pm):
    from app.core.errores import ErrorDeDominio
    from app.services import vistas_guardadas as svc
    dev = db.get(User, "dev-test-id")
    propia = svc.crear(db, dev, {"name": "Mi tabla", "view_type": "table", "config": {"columns": ["title"]}})
    with pytest.raises(ErrorDeDominio):
        svc.crear(db, dev, {"name": "Para todos", "view_type": "table", "is_shared": True})
    svc.crear(db, pm, {"name": "Del PM", "view_type": "timeline", "is_shared": True})
    nombres = {v["name"] for v in svc.listar(db, dev)}
    assert nombres == {"Mi tabla", "Del PM"}
    assert propia["config"] == {"columns": ["title"]}
    with pytest.raises(ErrorDeDominio):
        svc.crear(db, dev, {"name": "Mala", "view_type": "pizarra"})


# ── Carga por persona ────────────────────────────────────────────────────────

def test_carga_por_semana_reparte_las_horas_en_dias_laborables(db, proyecto, pm):
    from app.services.planificador.carga import carga_por_semana
    _tarea(db, proyecto, "Semana", 5, assignee_id="dev-test-id", estimated_hours=60)
    r = carga_por_semana(db, pm, proyecto.id, desde=proyecto.start_date, semanas=2)
    fila = next(p for p in r["people"] if p["user_id"] == "dev-test-id")
    primera, segunda = fila["weeks"]
    assert primera["hours"] == 60 and primera["capacity"] == 40
    assert primera["state"] == "over" and primera["pct"] == 150.0
    assert segunda["hours"] == 0


def test_rutas_del_planificador_responden(client, admin_token, db, proyecto):
    _tarea(db, proyecto, "A", 2)
    h = {"Authorization": f"Bearer {admin_token}"}
    for ruta in (f"/api/v1/planning/projects/{proyecto.id}/schedule",
                 f"/api/v1/planning/projects/{proyecto.id}/leveling",
                 f"/api/v1/planning/projects/{proyecto.id}/evm",
                 f"/api/v1/planning/projects/{proyecto.id}/evm/curve",
                 f"/api/v1/planning/workload?project_id={proyecto.id}",
                 "/api/v1/planning/views",
                 "/api/v1/portfolio-intake/proposals",
                 "/api/v1/templates"):
        assert client.get(ruta, headers=h).status_code == 200, ruta
