"""Herramientas del asistente (chat, agente, MCP), pipeline, épicas y wiki por rol
(segunda auditoría 2026-11).

Escenario: P1 donde el empleado (dev) tiene una tarea; P2 de otro PM, sin nada suyo.
"""
from __future__ import annotations

import pytest

from app.models.epics import Epic, WikiPage, WikiSpace
from app.models.financial import ProjectMilestone
from app.models.pipeline import Contract, ContractType
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.service_desk import Ticket
from app.models.service_desk._enums import TicketType
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services.ai_chat.tool_execution.executor import _HANDLERS, execute_tool
from app.services.ai_chat.tool_execution.politica import POLITICAS
from app.services.ai_chat.tool_execution.schema import AGENT_TOOLS
from tests.conftest import auth

DEV, PM, ADMIN = "dev-test-id", "pm-test-id", "admin-test-id"


def test_toda_herramienta_tiene_politica_y_su_ruta_existe():
    from app.main import app
    nombres = {h["name"] for h in AGENT_TOOLS}
    assert nombres <= set(_HANDLERS) and set(_HANDLERS) == set(POLITICAS)
    rutas = {(m, r.path) for r in app.routes for m in getattr(r, "methods", None) or ()}
    sin_ruta = [n for n, p in POLITICAS.items() if (p.metodo, "/api/v1" + p.ruta) not in rutas]
    assert not sin_ruta, sin_ruta


def test_la_politica_de_cada_herramienta_es_una_capacidad_del_catalogo():
    """23-11-2026 (M9): la herramienta pide una capacidad, como su ruta, no una lista de roles."""
    from app.core.capacidades import CAPACIDADES
    malas = [n for n, p in POLITICAS.items() if p.capacidad is not None and p.capacidad not in CAPACIDADES]
    assert not malas, malas


@pytest.fixture
def escenario(db, dev_token, pm_token, admin_token):
    for pid, pm in (("p-ia-1", PM), ("p-ia-2", ADMIN)):
        db.add(Project(id=pid, organization_id=1, code=pid.upper(), name=f"IA {pid}",
                       project_type=ProjectType.consulting, status=ProjectStatus.active,
                       pm_id=pm, created_by=ADMIN))
    db.flush()
    db.add(Task(id="t-ia-dev", organization_id=1, code="T-IA-DEV", project_id="p-ia-1", title="t",
                assignee_id=DEV, reporter_id=ADMIN, created_by=ADMIN,
                status=TaskStatus.todo, priority=TaskPriority.medium))
    for mid, pid in (("m-ia-1", "p-ia-1"), ("m-ia-2", "p-ia-2")):
        db.add(ProjectMilestone(id=mid, organization_id=1, project_id=pid, name=mid))
    db.add(Contract(id="c-ia", organization_id=1, code="CTR-IA", name="c", project_id="p-ia-2",
                    client_name="X", contract_type=ContractType.fixed_price))
    db.add(Ticket(id="tk-ia", organization_id=1, number="TK-IA", ticket_type=TicketType.incident,
                  title="ajeno", description="d", created_by_user_id=ADMIN))
    db.add(Epic(id="e-ia-2", organization_id=1, project_id="p-ia-2", title="épica"))
    db.add(WikiSpace(id="w-ia-2", organization_id=1, project_id="p-ia-2", name="w", slug="w-ia-2"))
    db.flush()
    db.add(WikiPage(id="wp-ia-2", organization_id=1, space_id="w-ia-2", title="pág", slug="pag"))
    db.commit()


def _yo(db, uid):
    return db.query(User).filter(User.id == uid).first()


def test_empleado_herramientas_de_lectura_acotadas(db, escenario):
    dev = _yo(db, DEV)
    usuarios = execute_tool("get_users_list", {}, db, dev)["users"]
    assert all(u["email"] is None for u in usuarios if u["id"] != DEV)
    hitos = {m["id"] for m in execute_tool("get_milestones", {}, db, dev)["milestones"]}
    assert "m-ia-1" in hitos and "m-ia-2" not in hitos
    assert "error" in execute_tool("get_contracts", {}, db, dev)
    assert "error" in execute_tool("get_pipeline", {}, db, dev)


def test_empleado_no_escribe_lo_que_su_rol_no_permite(db, escenario):
    dev = _yo(db, DEV)
    assert "error" in execute_tool("update_project_status", {"project_id": "p-ia-1", "status": "on_hold"}, db, dev)
    assert "error" in execute_tool("reassign_tickets", {"from_user_name": "a", "to_user_name": "b"}, db, dev)
    r = execute_tool("update_ticket_status", {"ticket_id": "tk-ia", "status": "resolved"}, db, dev)
    assert "error" in r
    db.expire_all()
    assert db.query(Project.status).filter(Project.id == "p-ia-1").scalar() == ProjectStatus.active


def test_pm_solo_cambia_sus_proyectos(db, escenario):
    pm = _yo(db, PM)
    assert "error" in execute_tool("update_project_status", {"project_id": "p-ia-2", "status": "on_hold"}, db, pm)
    assert execute_tool("update_project_status", {"project_id": "p-ia-1", "status": "on_hold"}, db, pm)["ok"]


def test_pipeline_solo_gestion(client, dev_token, pm_token):
    for ruta in ("/api/v1/pipeline", "/api/v1/pipeline/pipeline"):
        assert client.get(ruta, headers=auth(dev_token)).status_code == 403
        assert client.get(ruta, headers=auth(pm_token)).status_code == 200


def test_epicas_y_wiki_siguen_a_su_proyecto(client, escenario, dev_token, admin_token):
    assert client.get("/api/v1/epics", params={"project_id": "p-ia-2"}, headers=auth(dev_token)).status_code == 404
    assert client.get("/api/v1/epics/e-ia-2", headers=auth(dev_token)).status_code == 404
    assert client.get("/api/v1/epics/wiki/pages/wp-ia-2", headers=auth(dev_token)).status_code == 404
    espacios = client.get("/api/v1/epics/wiki/spaces", headers=auth(dev_token)).json()["items"]
    assert "w-ia-2" not in {e["id"] for e in espacios}
    assert client.get("/api/v1/epics/wiki/pages/wp-ia-2", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/v1/epics", params={"project_id": "p-ia-2"}, headers=auth(admin_token)).status_code == 200


# ── Seguimiento #31 ───────────────────────────────────────────────────────────

def test_git_pr_y_despliegues_siguen_a_su_proyecto(db, escenario):
    from app.models.git_integration import GitPullRequest
    from app.services.git_service import list_pull_requests
    for prid, pid in (("pr-ia-1", "p-ia-1"), ("pr-ia-2", "p-ia-2")):
        db.add(GitPullRequest(id=prid, organization_id=1, project_id=pid, repo_full_name="o/r", pr_number=1))
    db.commit()
    assert {p.id for p in list_pull_requests(db, _yo(db, DEV))} == {"pr-ia-1"}
    assert {"pr-ia-1", "pr-ia-2"} <= {p.id for p in list_pull_requests(db, _yo(db, ADMIN))}


def test_comentarios_en_hilo_exigen_ver_la_entidad(client, db, escenario, dev_token, admin_token):
    url = "/api/v1/epics/comments"
    assert client.get(url, params={"entity_type": "task", "entity_id": "t-ia-dev"}, headers=auth(dev_token)).status_code == 200
    assert client.get(url, params={"entity_type": "ticket", "entity_id": "tk-ia"}, headers=auth(dev_token)).status_code == 404
    assert client.get(url, params={"entity_type": "epic", "entity_id": "e-ia-2"}, headers=auth(dev_token)).status_code == 404
    assert client.get(url, params={"entity_type": "otra", "entity_id": "x"}, headers=auth(dev_token)).status_code == 404
    assert client.get(url, params={"entity_type": "otra", "entity_id": "x"}, headers=auth(admin_token)).status_code == 200


def test_plantillas_de_wiki_del_externo_solo_del_sistema(client, db, sub_token, dev_token):
    from app.models.epics import WikiTemplate
    db.add(WikiTemplate(id="wt-emp", organization_id=1, name="De empresa", is_system=False))
    db.commit()
    ids = lambda tok: {t["id"] for t in client.get("/api/v1/epics/wiki/templates", headers=auth(tok)).json()["items"]}
    assert "wt-emp" in ids(dev_token) and "wt-emp" not in ids(sub_token)


def test_nql_no_pierde_letras_y_task_count_solo_activos(db, escenario):
    from app.models.epics import EpicTask
    from app.services.epics_service import parse_nql, serialize_epic
    c = parse_nql('status = done AND title = "and data"')
    assert c["status"]["val"] == "done" and c["title"]["val"] == "and data"
    db.add(EpicTask(epic_id="e-ia-2", task_id="t-ia-dev", is_active=False))
    db.commit()
    assert serialize_epic(db.query(Epic).filter(Epic.id == "e-ia-2").first())["task_count"] == 0
