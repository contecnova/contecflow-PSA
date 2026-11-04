"""Ausencias paginadas y tareas filtradas por fecha.

Auditoria 2026-11: `/absences` ignoraba `page_size` y devolvia las 50 primeras
sin total; el calendario mandaba `due_date_from/to` a `/tasks`, que los ignoraba.
"""
from datetime import date, timedelta

from app.models.resources import Absence, AbsenceStatus, AbsenceType
from tests.conftest import auth


def test_EL_HALLAZGO_las_ausencias_paginan_con_total(client, admin_token, db):
    hoy = date.today()
    for i in range(60):
        db.add(Absence(user_id="dev-test-id", organization_id="1", status=AbsenceStatus.approved,
                       type=AbsenceType.vacation,
                       start_date=hoy + timedelta(days=i), end_date=hoy + timedelta(days=i)))
    db.commit()
    r1 = client.get("/api/v1/absences?page=1&page_size=50", headers=auth(admin_token)).json()
    r2 = client.get("/api/v1/absences?page=2&page_size=50", headers=auth(admin_token)).json()
    assert r1["meta"]["total"] == 60
    assert len(r1["items"]) == 50 and len(r2["items"]) == 10
    assert not {a["id"] for a in r1["items"]} & {a["id"] for a in r2["items"]}


def test_EL_HALLAZGO_el_calendario_filtra_tareas_por_fecha(client, pm_token, db):
    pid = client.post("/api/v1/projects", headers=auth(pm_token),
                      json={"name": "Cal", "code": "CAL1", "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    for titulo, fecha in (("dentro", "2026-11-10"), ("fuera", "2026-12-10")):
        client.post("/api/v1/tasks", headers=auth(pm_token), json={"title": titulo, "project_id": pid, "due_date": fecha})
    r = client.get("/api/v1/tasks?due_date_from=2026-11-01&due_date_to=2026-11-30", headers=auth(pm_token))
    assert [t["title"] for t in r.json()["items"]] == ["dentro"]
