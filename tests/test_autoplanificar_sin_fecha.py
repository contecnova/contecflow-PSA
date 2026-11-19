"""Auto-planificar tareas sin fecha con el motor (19-11-2026, `planificador/sin_fecha.py`).

Lo que se mide: sin IA; cada tarea en el horario de su responsable llenando sus
horas libres (la segunda de la misma persona empieza cuando acaba la primera);
la sucesora espera a su predecesora; la carga que ya tenía cuenta; la prioridad
ordena; sin estimación vale una jornada; el endpoint responde lo de siempre.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core import timeutil
from app.models.bookings import DependencyType, TaskDependency
from app.models.project import Project, ProjectType
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services.planificador import sin_fecha
from app.services.planificador.calendario import cargar_calendarios


@pytest.fixture
def pm(db):
    return db.get(User, "pm-test-id")


@pytest.fixture
def proyecto(db):
    p = Project(id=str(uuid.uuid4()), organization_id="1", code=f"AP-{uuid.uuid4().hex[:5]}",
                name="Autoplan", project_type=ProjectType.development, start_date=timeutil.today())
    db.add(p)
    db.commit()
    return p


def _tarea(db, p, titulo, horas=None, quien="dev-test-id", **kw):
    t = Task(id=str(uuid.uuid4()), organization_id="1", project_id=p.id, code=f"T-{uuid.uuid4().hex[:6]}",
             title=titulo, status=TaskStatus.todo, estimated_hours=horas, assignee_id=quien, **kw)
    db.add(t)
    db.commit()
    return t


def _plan(db, pm, p, **kw):
    return {x["task_id"]: x for x in sin_fecha.proponer(db, pm, project_id=p.id, **kw)["scheduled"]}


def _cal(db, uid="dev-test-id"):
    empresa, cals = cargar_calendarios(db, "1", {uid}, timeutil.today())
    return cals.get(uid) or empresa


def test_la_misma_persona_encadena_sus_tareas_por_prioridad(db, pm, proyecto):
    jornada = _cal(db).horas(_cal(db).siguiente(timeutil.today()))
    baja = _tarea(db, proyecto, "Baja", horas=jornada, priority=TaskPriority.low)
    alta = _tarea(db, proyecto, "Alta", horas=jornada, priority=TaskPriority.high)
    plan = _plan(db, pm, proyecto)
    a, b = plan[alta.id], plan[baja.id]
    assert a["suggested_start"] == a["suggested_due"]           # una jornada, un día
    assert b["suggested_start"] > a["suggested_due"]            # la baja va después
    assert a["motivo"]["codigo"] == "planificada" and a["motivo"]["origen_horas"] == "estimacion"


def test_la_sucesora_espera_a_su_predecesora(db, pm, proyecto):
    pred = _tarea(db, proyecto, "Pred", horas=16, quien="dev-test-id")
    suc = _tarea(db, proyecto, "Suc", horas=4, quien="pm-test-id")   # otra persona, libre
    db.add(TaskDependency(organization_id="1", predecessor_id=pred.id, successor_id=suc.id,
                          dependency_type=DependencyType.finish_to_start, lag_days=0, link_type="schedule",
                          is_active=True))
    db.commit()
    plan = _plan(db, pm, proyecto)
    assert plan[suc.id]["suggested_start"] > plan[pred.id]["suggested_due"]
    assert plan[suc.id]["motivo"]["espera_predecesora"] is True


def test_la_carga_que_ya_tiene_cuenta(db, pm, proyecto):
    cal = _cal(db)
    hoy = cal.siguiente(timeutil.today())
    ocupada = Task(id=str(uuid.uuid4()), organization_id="1", project_id=proyecto.id, code="T-OCUP",
                   title="Ya planificada", status=TaskStatus.todo, assignee_id="dev-test-id",
                   estimated_hours=cal.horas(hoy), start_date=hoy, due_date=hoy)
    db.add(ocupada)
    db.commit()
    nueva = _tarea(db, proyecto, "Nueva", horas=1)
    assert _plan(db, pm, proyecto)[nueva.id]["suggested_start"] > hoy.isoformat()


def test_sin_estimacion_vale_una_jornada_y_sin_responsable_usa_la_empresa(db, pm, proyecto):
    t = _tarea(db, proyecto, "Sin estimar", quien=None)
    m = _plan(db, pm, proyecto)[t.id]["motivo"]
    assert m["origen_horas"] == "jornada" and m["sin_responsable"] is True


def test_max_tareas_y_recuento(db, pm, proyecto):
    for i in range(3):
        _tarea(db, proyecto, f"T{i}", horas=2)
    r = sin_fecha.proponer(db, pm, project_id=proyecto.id, max_tareas=2)
    assert len(r["scheduled"]) == 2 and r["unscheduled_count"] == 3


def test_endpoint_responde_rapido_y_sin_ia(client, pm_token, db, proyecto, monkeypatch):
    import app.services.ai_modules.client_portal as cp
    monkeypatch.setattr(cp, "call_ai_unified", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sin IA")),
                        raising=False)
    t = _tarea(db, proyecto, "Por API", horas=3)
    r = client.post("/api/v1/ai-modules/smart-schedule", json={"project_id": proyecto.id, "max_tasks": 20},
                    headers={"Authorization": f"Bearer {pm_token}"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    fila = next(x for x in d["scheduled"] if x["task_id"] == t.id)
    assert fila["title"] == "Por API" and fila["suggested_start"] and fila["suggested_due"]
