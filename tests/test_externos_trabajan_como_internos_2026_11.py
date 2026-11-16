"""Externos como internos (16-11-2026): el subcontratado trabaja como un interno
sobre lo suyo, con la seguridad de un externo.

Las rutas de trabajo pasan de `require_internal_user` a `require_worker`; el
ámbito lo sigue poniendo cada servicio (o el endpoint). Escenario: P1, donde el
subcontratado es miembro activo y tiene una tarea; P2, ajeno, con una tarea de
hr. Un ticket asignado al subcontratado y otro ajeno.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.project import Project, ProjectMember, ProjectStatus, ProjectType
from app.models.service_desk import KBArticle, Ticket
from app.models.service_desk._enums import KBStatus
from app.models.task import Task, TaskPriority, TaskStatus
from tests.conftest import auth

SUB, DEV, PM, HR, ADMIN = "sub-test-id", "dev-test-id", "pm-test-id", "hr-test-id", "admin-test-id"
P1, P2 = "p-ext-1", "p-ext-2"


@pytest.fixture
def escenario(db):
    for pid, codigo, pm in ((P1, "PRJ-E1", PM), (P2, "PRJ-E2", None)):
        db.add(Project(id=pid, organization_id=1, code=codigo, name=codigo, project_type=ProjectType.consulting,
                       status=ProjectStatus.active, pm_id=pm, created_by=ADMIN))
    db.flush()
    db.add(ProjectMember(project_id=P1, user_id=SUB, is_active=True))
    for tid, pid, quien in (("t-e1", P1, SUB), ("t-e2", P2, HR)):
        db.add(Task(id=tid, organization_id=1, code=tid.upper(), project_id=pid, title=tid, assignee_id=quien,
                    reporter_id=ADMIN, created_by=ADMIN, status=TaskStatus.todo, priority=TaskPriority.medium))
    for tid, numero, quien in (("tk-e1", "INC-7701", SUB), ("tk-e2", "INC-7702", HR)):
        db.add(Ticket(id=tid, number=numero, ticket_type="incident", title=numero, description="d",
                      organization_id="1", assigned_to_user_id=quien))
    db.commit()


# ── Tareas ────────────────────────────────────────────────────────────────────

def test_crea_tarea_en_su_proyecto_y_no_en_uno_ajeno(client, sub_token, escenario):
    ok = client.post("/api/v1/tasks", headers=auth(sub_token), json={"title": "nueva", "project_id": P1})
    assert ok.status_code in (200, 201), ok.text
    assert ok.json()["data"]["project_id"] == P1
    ajeno = client.post("/api/v1/tasks", headers=auth(sub_token), json={"title": "nueva", "project_id": P2})
    assert ajeno.status_code in (403, 404), ajeno.text


def test_no_asigna_la_tarea_a_quien_no_ve(client, sub_token, escenario):
    r = client.post("/api/v1/tasks", headers=auth(sub_token),
                    json={"title": "x", "project_id": P1, "assignee_id": HR})
    assert r.status_code == 404, r.text
    r = client.post("/api/v1/tasks", headers=auth(sub_token),
                    json={"title": "x", "project_id": P1, "parent_task_id": "t-e2"})
    assert r.status_code == 404, r.text


def test_el_empleado_crea_solo_donde_trabaja(client, dev_token, escenario, db):
    assert client.post("/api/v1/tasks", headers=auth(dev_token),
                       json={"title": "x", "project_id": P1}).status_code in (403, 404)
    db.add(ProjectMember(project_id=P1, user_id=DEV, is_active=True))
    db.commit()
    r = client.post("/api/v1/tasks", headers=auth(dev_token), json={"title": "x", "project_id": P1})
    assert r.status_code in (200, 201), r.text


def test_comenta_en_su_tarea_y_no_en_una_ajena(client, sub_token, escenario):
    ok = client.post("/api/v1/tasks/t-e1/comments", headers=auth(sub_token), json={"content": "hecho"})
    assert ok.status_code in (200, 201), ok.text
    ajena = client.post("/api/v1/tasks/t-e2/comments", headers=auth(sub_token), json={"content": "x"})
    assert ajena.status_code in (403, 404), ajena.text


# ── Imputaciones ──────────────────────────────────────────────────────────────

def test_imputa_en_su_proyecto_y_no_en_uno_ajeno(client, sub_token, escenario):
    hoy = str(date.today())
    ok = client.post("/api/v1/imputations", headers=auth(sub_token),
                     json={"project_id": P1, "task_id": "t-e1", "date": hoy, "hours": 2})
    assert ok.status_code in (200, 201), ok.text
    ajeno = client.post("/api/v1/imputations", headers=auth(sub_token),
                        json={"project_id": P2, "date": hoy, "hours": 2})
    assert ajeno.status_code in (403, 404), ajeno.text


# ── Service desk ──────────────────────────────────────────────────────────────

def test_trabaja_su_ticket_y_no_uno_ajeno(client, sub_token, escenario):
    h = auth(sub_token)
    assert client.post("/api/v1/sd/tickets/tk-e1/comments", headers=h,
                       json={"body": "mirando", "is_public": False}).status_code == 200
    assert client.post("/api/v1/sd/tickets/tk-e1/time-log", headers=h, json={"minutes": 30}).status_code == 200
    assert client.post("/api/v1/sd/tickets/tk-e1/watch", headers=h).status_code in (200, 201)
    assert client.post("/api/v1/sd/tickets/tk-e1/sla/pause", headers=h, json={}).status_code == 200
    assert client.post("/api/v1/sd/tickets/tk-e1/sla/resume", headers=h).status_code == 200
    assert client.get("/api/v1/sd/tickets/tk-e1/lifecycle", headers=h).status_code == 200
    for metodo, ruta, cuerpo in (
        ("POST", "comments", {"body": "x", "is_public": False}),
        ("POST", "time-log", {"minutes": 30}),
        ("POST", "watch", None),
        ("DELETE", "watch", None),
        ("POST", "sla/pause", {}),
        ("POST", "sla/resume", None),
        ("POST", "escalate?to_level=l2", None),
        ("POST", "restore-pending", None),
        ("GET", "lifecycle", None),
    ):
        r = client.request(metodo, f"/api/v1/sd/tickets/tk-e2/{ruta}", headers=h, json=cuerpo)
        assert r.status_code == 404, f"{metodo} {ruta}: {r.status_code} {r.text}"


def test_abre_ticket_solo_de_lo_suyo(client, sub_token, escenario):
    h = auth(sub_token)
    ok = client.post("/api/v1/sd/tickets", headers=h,
                     json={"title": "no arranca", "description": "d", "project_id": P1})
    assert ok.status_code == 200, ok.text
    assert client.get(f"/api/v1/sd/tickets/{ok.json()['data']['id']}", headers=h).status_code == 200
    ajeno = client.post("/api/v1/sd/tickets", headers=h,
                        json={"title": "x", "description": "d", "project_id": P2})
    assert ajeno.status_code == 404, ajeno.text
    a_otro = client.post("/api/v1/sd/tickets", headers=h,
                         json={"title": "x", "description": "d", "assigned_to_user_id": HR})
    assert a_otro.status_code == 404, a_otro.text


# ── Ausencias y gastos propios ────────────────────────────────────────────────

def test_pide_su_ausencia(client, sub_token, escenario):
    h = auth(sub_token)
    assert client.get("/api/v1/absences/types", headers=h).status_code == 200
    inicio = date.today() + timedelta(days=60)
    r = client.post("/api/v1/absences/my", headers=h,
                    json={"type": "vacation", "start_date": str(inicio), "end_date": str(inicio + timedelta(days=2))})
    assert r.status_code in (200, 201), r.text
    mias = client.get("/api/v1/absences/my", headers=h)
    assert mias.status_code == 200 and all(a.get("user_id") in (None, SUB) for a in mias.json()["items"])
    # Las de la organización, no.
    assert client.get("/api/v1/absences/inbox", headers=h).status_code == 403
    assert client.get("/api/v1/absences/roster", headers=h).status_code == 403


def test_presenta_su_gasto_solo_en_su_proyecto(client, sub_token, escenario):
    h = auth(sub_token)
    base = {"category": "travel", "description": "tren", "amount": 20, "expense_date": str(date.today()),
            "is_billable": False}
    assert client.post("/api/v1/expenses", headers=h, json={**base, "project_id": P1}).status_code == 200
    assert client.post("/api/v1/expenses", headers=h, json={**base, "project_id": P2}).status_code == 404


# ── Base de conocimiento: solo lo publicado ───────────────────────────────────

def test_lee_solo_articulos_publicados(client, sub_token, dev_token, db):
    db.add(KBArticle(id="kb-pub", number="KB-7701", title="publicado", body="b", status=KBStatus.published))
    db.add(KBArticle(id="kb-bor", number="KB-7702", title="borrador", body="b", status=KBStatus.draft))
    db.commit()
    ids = {a["id"] for a in client.get("/api/v1/sd/kb", headers=auth(sub_token)).json()["items"]}
    assert "kb-pub" in ids and "kb-bor" not in ids
    assert client.get("/api/v1/sd/kb/kb-bor", headers=auth(sub_token)).status_code == 404
    assert client.get("/api/v1/sd/kb/kb-pub", headers=auth(sub_token)).status_code == 200
    # El interno sigue viendo el borrador.
    assert client.get("/api/v1/sd/kb/kb-bor", headers=auth(dev_token)).status_code == 200


# ── Sigue fuera de la organización y las finanzas ────────────────────────────

@pytest.mark.parametrize("metodo,ruta", [
    ("GET", "/api/v1/invoices"),
    ("GET", "/api/v1/users/org-chart"),
    ("GET", "/api/v1/profitability/summary"),
    ("GET", "/api/v1/planning/workload"),
    ("POST", "/api/v1/sd/tickets/tk-e1/links"),
    ("POST", "/api/v1/sd/tickets/tk-e1/to-kb?title=x"),
    ("POST", "/api/v1/expenses/ocr"),
])
def test_sigue_sin_acceso_a_la_organizacion(client, sub_token, escenario, metodo, ruta):
    r = client.request(metodo, ruta, headers=auth(sub_token), json={})
    assert r.status_code == 403, f"{metodo} {ruta}: {r.status_code} {r.text[:200]}"
