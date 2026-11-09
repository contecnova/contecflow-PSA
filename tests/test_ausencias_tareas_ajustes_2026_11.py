"""Ausencias, bloqueo de imputaciones y edición masiva de tareas (revisión 2026-11).

Medido antes:
- unas vacaciones se aceptaban aunque pasaran del saldo;
- los días de vacaciones y de bloqueo de Admin no se leían (se usaba el fichero);
- la edición masiva cambiaba el estado sin las reglas de transición.
"""
from __future__ import annotations

from datetime import date

from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services import settings_service
from app.services.imputation_service import get_lockout_cutoff
from app.services.tasks.bulk import bulk_update_tasks
from tests.conftest import auth


def _dias_de_vacaciones(db, n):
    settings_service.set_runtime_value(db, "locale", "DEFAULT_VACATION_DAYS_PER_YEAR", n, "1")


def test_EL_HALLAZGO_unas_vacaciones_no_pasan_del_saldo(client, dev_token, db):
    _dias_de_vacaciones(db, 3)
    r = client.post("/api/v1/absences/my", headers=auth(dev_token),
                    json={"type": "vacation", "start_date": "2031-03-03", "end_date": "2031-03-07"})
    assert r.status_code == 400, r.text
    assert "te quedan 3" in r.json()["detail"]


def test_dentro_del_saldo_se_acepta_y_editar_no_cuenta_dos_veces(client, dev_token, db):
    _dias_de_vacaciones(db, 5)
    r = client.post("/api/v1/absences/my", headers=auth(dev_token),
                    json={"type": "vacation", "start_date": "2031-03-03", "end_date": "2031-03-07"})
    assert r.status_code == 200, r.text
    aid = r.json()["data"]["id"]
    # Los mismos cinco días: la propia solicitud ya contaba como pendiente.
    r = client.patch(f"/api/v1/absences/my/{aid}", headers=auth(dev_token),
                     json={"type": "vacation", "start_date": "2031-03-03", "end_date": "2031-03-07"})
    assert r.status_code == 200, r.text


def test_una_baja_no_consume_saldo(client, dev_token, db):
    _dias_de_vacaciones(db, 0)
    r = client.post("/api/v1/absences/my", headers=auth(dev_token),
                    json={"type": "sick", "start_date": "2031-04-07", "end_date": "2031-04-11"})
    assert r.status_code == 200, r.text


def test_EL_HALLAZGO_el_bloqueo_lee_el_ajuste_de_admin(db):
    usuario = db.query(User).filter(User.username == "dev_test").one()
    settings_service.set_runtime_value(db, "locale", "DEFAULT_IMPUTATION_LOCKOUT_DAYS", 3, "1")
    a = get_lockout_cutoff(usuario, db)
    settings_service.set_runtime_value(db, "locale", "DEFAULT_IMPUTATION_LOCKOUT_DAYS", 10, "1")
    b = get_lockout_cutoff(usuario, db)
    assert isinstance(a, date) and (a - b).days == 7


def test_EL_HALLAZGO_la_edicion_masiva_respeta_las_transiciones(client, admin_token, db):
    r = client.post("/api/v1/projects", headers=auth(admin_token),
                    json={"name": "Proyecto MASIVA", "code": "MASIVA", "status": "active", "billing_type": "time_material"})
    assert r.status_code in (200, 201), r.text
    tarea = Task(code="MASIVA-1", project_id=r.json()["data"]["id"], title="Cancelada",
                 status=TaskStatus.cancelled, priority=TaskPriority.medium)
    db.add(tarea)
    db.commit()
    admin = db.query(User).filter(User.username == "admin").one()
    r = bulk_update_tasks([tarea.id], {"status": TaskStatus.todo}, admin, db)
    assert r["updated"] == 0
    assert r["skipped"] == [{"id": tarea.id, "reason": "invalid_transition"}]
    db.refresh(tarea)
    assert tarea.status == TaskStatus.cancelled
