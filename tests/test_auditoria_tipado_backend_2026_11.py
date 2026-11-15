"""Segunda auditoria 2026-11: fallos de backend hallados al tipar el frontend.

Un test por arreglo; cada uno falla con el codigo anterior.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from tests.conftest import auth


def _proyecto(db, code="TIP1", name="Proyecto tipado", pm_id="pm-test-id"):
    from app.models.project import Project, ProjectStatus, ProjectType
    p = Project(code=code, name=name, status=ProjectStatus.active,
                project_type=ProjectType.consulting, pm_id=pm_id, created_by="admin-test-id")
    db.add(p)
    db.commit()
    return p


# 1 ── la ejecucion del agente solo la ve su dueno
def test_detalle_de_ejecucion_del_agente_solo_para_su_dueno(db):
    from app.models.ai_chat import AIAgentExecution
    from app.services.ai_chat.agent_execution_service import get_agent_detail_with_steps
    e = AIAgentExecution(user_id="admin-test-id", instruction="secreto", status="done")
    db.add(e)
    db.commit()
    assert get_agent_detail_with_steps(db, e.id, "admin-test-id")["instruction"] == "secreto"
    with pytest.raises(ValueError):
        get_agent_detail_with_steps(db, e.id, "dev-test-id")


# 2 ── `organization_id` de la query no sustituye al tenant
def test_correlacion_de_alertas_no_deja_elegir_otra_organizacion():
    from app.api.v1.endpoints.service_desk.alert_correlation import _org_objetivo
    from app.core.errores import ErrorDeDominio
    normal = SimpleNamespace(organization_id="org-a", is_superadmin=False)
    assert _org_objetivo(normal, None) == "org-a"
    with pytest.raises(ErrorDeDominio):
        _org_objetivo(normal, "org-b")
    assert _org_objetivo(SimpleNamespace(organization_id="1", is_superadmin=True), "org-b") == "org-b"


# 3 ── CMDB 3D: sin CIs, grafo vacio (sin demo) y filtrado por organizacion
def test_grafo_cmdb_3d_vacio_y_por_organizacion(db):
    from app.models.service_desk import ConfigurationItem
    from app.models.service_desk.cmdb import CIType
    from app.services.service_desk.cmdb_3d_service import get_3d_graph
    assert get_3d_graph(db, org_id="1")["nodes"] == []
    db.add(ConfigurationItem(code="CI-1", name="Servidor real", ci_type=list(CIType)[0], organization_id="1"))
    db.commit()
    assert [n["name"] for n in get_3d_graph(db, org_id="1")["nodes"]] == ["Servidor real"]
    assert get_3d_graph(db, org_id="otra")["nodes"] == []


# 4 ── voz: el resumen solo encuentra proyectos visibles para el rol
def test_resumen_por_voz_respeta_la_visibilidad_de_proyectos(db):
    from app.models.user import User
    from app.services.ai_modules.voice import _voice_handle_get_summary
    _proyecto(db, name="Confidencial")
    dev = db.get(User, "dev-test-id")
    resultado = {}
    _voice_handle_get_summary(db, dev, {"project_name": "Confidencial"}, resultado)
    assert resultado["action"].startswith("No encontré")
    admin = db.get(User, "admin-test-id")
    _voice_handle_get_summary(db, admin, {"project_name": "Confidencial"}, resultado)
    assert "Confidencial" in resultado["action"] and not resultado["action"].startswith("No")


# 6 ── el export UAT no revienta con una tarea enlazada
def test_export_uat_con_tarea_enlazada(db):
    from app.models.raci import UATCase
    from app.models.task import Task
    from app.services.raci_service import export_uat_report
    p = _proyecto(db)
    t = Task(code="T-UAT", title="Tarea UAT", project_id=p.id, created_by="admin-test-id")
    db.add(t)
    db.flush()
    db.add(UATCase(project_id=p.id, task_id=t.id, title="Caso"))
    db.commit()
    assert "**Tarea vinculada:** Tarea UAT" in export_uat_report(p.id, db)["text"]


# 7 ── Jira sin proyecto: no crea Task(project_id=None); proyecto ajeno: 404
def test_sync_de_jira_sin_proyecto_omite_las_nuevas(db):
    from app.core.errores import ErrorDeDominio
    from app.services.jira_service import sync_jira_issues
    issue = {"key": "J-1", "id": "1", "fields": {"summary": "Nueva"}}
    r = sync_jira_issues(db, [issue], None, "admin-test-id", dry_run=False, org_id="1")
    assert r["created"] == 0 and r["skipped_without_project"] == 1
    with pytest.raises(ErrorDeDominio):
        sync_jira_issues(db, [issue], "no-existe", "admin-test-id", dry_run=False, org_id="1")


# 8 ── e-firma: los ids son UUID
def test_esign_acepta_ids_uuid():
    from app.api.v1.endpoints.esign import EnvelopeCreate, EnvelopeOut
    doc = "5f0c6c2e-8a51-4c43-9d0e-7a1f0c2b9e11"
    assert EnvelopeCreate(document_id=doc, subject="s", signers=[]).document_id == doc
    ahora = datetime.now(timezone.utc)
    out = EnvelopeOut.model_validate(dict(
        id="e-uuid", document_id=doc, provider="manual", subject=None, message=None, status="draft",
        signing_url=None, completed_pdf_path=None, sent_at=None, completed_at=None, expires_at=None,
        created_at=ahora, signers=[]))
    assert out.id == "e-uuid"


# 9 ── RGPD: tras el borrado no se reescribe el id del interesado
def test_borrado_rgpd_no_reescribe_al_interesado(client, admin_token, db):
    from app.services import bi_gdpr_service as svc
    svc.record_consent(db, user_id="sujeto-x", consented=True, org_id="1")
    dsr = svc.create_dsr(db, subject_id="sujeto-x", request_type="erasure", org_id="1",
                         requester_user_id="admin-test-id")
    db.commit()
    r = client.post(f"/api/v1/bi/gdpr/dsr/{dsr['id']}/erasure-execute", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert svc.get_consent(db, user_id="sujeto-x", org_id="1") is None
    assert svc.get_consent_history(db, user_id="sujeto-x", org_id="1") == []
    assert svc.get_dsr(db, dsr_id=dsr["id"], org_id="1")["subject_id"] != "sujeto-x"


# 10 ── una metrica mala no tira el lote
def test_forecast_multi_aisla_la_metrica_mala(client, admin_token):
    r = client.post("/api/v1/bi/forecast/multi", headers=auth(admin_token), json={"forecasts": [
        {"metric": "utilization", "values": [1, 2, 3, 4]},
        {"metric": "utilization", "values": [1]},
    ]})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["results"]) == 1 and len(data["errors"]) == 1


# 11 ── O365: misma forma con y sin datos
def test_adopcion_o365_sin_datos_usa_by_product(db):
    from app.services.bi_o365_service import get_adoption_summary
    r = get_adoption_summary(db, "1")
    assert r["by_product"] == {} and "products" not in r and r["total_users"] == 0


# 12 ── auto-resolucion: config y estadisticas de la organizacion
def test_auto_resolucion_config_y_stats_por_organizacion(db):
    from app.services.service_desk import ai_auto_resolution_service as s
    from app.services.service_desk.auto_resolucion_operaciones import guardar_configuracion
    guardar_configuracion(db, {"default_job_limit": 7}, "1")
    assert s.get_auto_resolution_config(db, "1")["default_job_limit"] == 7
    assert s.get_auto_resolution_config(db, None)["default_job_limit"] == 100
    s._save_feedback_stats(db, {"cat::p": {"total": 2, "success": 1}}, s._feedback_key_de_organizacion("1"))
    db.commit()
    assert s.get_auto_resolution_stats(db, "1")["feedback_total_validated"] == 2


# 13 ── incidente mayor: fechas ISO
def test_incidente_mayor_fechas_iso():
    from app.services.service_desk.major_incident_service import serialize_major_incident
    mi = SimpleNamespace(id="1", number="MI1", title="t", status=SimpleNamespace(value="open"),
                         severity="P1", declared_at=datetime(2026, 11, 14, 10, tzinfo=timezone.utc),
                         resolved_at=None, commander=None, impact_statement=None, notifications_sent=0)
    assert serialize_major_incident(mi)["declared_at"] == "2026-11-14T10:00:00+00:00"


# 14 ── reglas de encaminamiento: objetos, no texto
def test_regla_de_encaminamiento_devuelve_objetos(db):
    from app.services.service_desk.routing_rule_service import build_routing_rule, serialize_routing_rule
    regla = build_routing_rule(db, {"name": "r", "conditions": {"priority": "p1"}, "actions": {"assign_group": "g"}})
    out = serialize_routing_rule(regla)
    assert out["conditions"] == {"priority": "p1"} and out["actions"] == {"assign_group": "g"}


# 15 ── timesheet sin imputaciones borradas
def test_timesheet_oculta_imputaciones_borradas(db):
    from app.models.imputation import Imputation
    from app.services.timesheet_service import get_timesheet_lines
    p = _proyecto(db)
    lunes = date(2026, 11, 9)
    db.add_all([Imputation(user_id="dev-test-id", project_id=p.id, date=lunes, hours=1),
                Imputation(user_id="dev-test-id", project_id=p.id, date=lunes, hours=2, is_active=False)])
    db.commit()
    assert [l["hours"] for l in get_timesheet_lines(db, "dev-test-id", lunes)] == [1]


# 16 ── skills: el empleado quita las suyas, no las de otro
def test_empleado_quita_sus_skills_y_no_las_ajenas(client, dev_token, db):
    from app.models.resources import Skill, SkillCategory, SkillLevel, UserSkill
    s = Skill(name="Python", category=list(SkillCategory)[0])
    db.add(s)
    db.flush()
    mia = UserSkill(user_id="dev-test-id", skill_id=s.id, level=list(SkillLevel)[0])
    ajena = UserSkill(user_id="pm-test-id", skill_id=s.id, level=list(SkillLevel)[0])
    db.add_all([mia, ajena])
    db.commit()
    h = auth(dev_token)
    assert client.delete(f"/api/v1/skills/users/dev-test-id/{ajena.id}", headers=h).status_code == 404
    assert client.delete(f"/api/v1/skills/users/dev-test-id/{mia.id}", headers=h).status_code == 200


# 17 ── certificaciones: sobre APIResponse
def test_certificacion_editar_y_borrar_con_sobre(client, admin_token, db):
    from app.models.training import Certification
    c = Certification(user_id="admin-test-id", name="PMP")
    db.add(c)
    db.commit()
    h = auth(admin_token)
    r = client.patch(f"/api/v1/training/certifications/{c.id}", headers=h,
                     json={"user_id": "admin-test-id", "name": "PMP 2"})
    assert r.json()["data"] == {"id": c.id}
    assert client.delete(f"/api/v1/training/certifications/{c.id}", headers=h).json()["data"] == {"deleted": True}


# 18 ── inscripcion: `cancelled`, no `dropped`
def test_estado_de_inscripcion_alineado_con_el_modelo():
    from pydantic import ValidationError
    from app.schemas.training import EnrollmentIn
    assert EnrollmentIn(course_id="c", user_id="u", status="cancelled").status.value == "cancelled"
    with pytest.raises(ValidationError):
        EnrollmentIn(course_id="c", user_id="u", status="dropped")


# 19 y 20 ── menciones: paginacion comun y `context_text`
def test_menciones_paginadas_con_context_text(client, admin_token, db):
    from app.models.epics import Mention
    for i in range(3):
        db.add(Mention(mentioned_user="admin-test-id", entity_type="task", entity_id=f"t{i}",
                       context_text=f"hola {i}"))
    db.commit()
    r = client.get("/api/v1/activity/mentions/my", headers=auth(admin_token), params={"page": 1, "page_size": 2})
    body = r.json()
    assert len(body["items"]) == 2 and body["meta"]["total"] == 3 and body["meta"]["has_more"]
    assert body["items"][0]["context_text"] == body["items"][0]["context"]


# 21 ── un caso UAT borrado no se edita
def test_caso_uat_borrado_no_se_edita(db):
    from app.models.raci import UATCase
    from app.services.raci_service import update_uat_case
    p = _proyecto(db)
    c = UATCase(project_id=p.id, title="Caso", is_active=False)
    db.add(c)
    db.commit()
    with pytest.raises(ValueError):
        update_uat_case(p.id, c.id, SimpleNamespace(model_dump=lambda **_: {"title": "x"}, status=None), db)


# 22 ── entrar como: sobre completo
def test_entrar_como_devuelve_el_sobre(client, superadmin_token):
    r = client.post("/api/v1/organizations/1/impersonate", headers=auth(superadmin_token),
                    json={"user_id": "pm-test-id", "reason": "Soporte"})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"data", "meta"} and r.cookies.get("access_token")


# 23 ── carteras: la pagina se aplica
def test_carteras_paginadas(client, admin_token, db):
    from app.models.portfolio import Portfolio
    db.add_all([Portfolio(name=f"C{i}", owner_id="admin-test-id") for i in range(3)])
    db.commit()
    body = client.get("/api/v1/portfolios", headers=auth(admin_token), params={"page": 2, "page_size": 2}).json()
    assert [x["name"] for x in body["items"]] == ["C2"] and body["meta"]["total"] == 3


# 24 ── BPMN: una clave propia no duplica la global; la copia propia la personaliza
def test_bpmn_clave_unica_contra_el_catalogo_global(db):
    from app.services import bpmn_process_service as svc
    from app.db.session import sin_filtro_de_tenant
    from tests.conftest import fila_global
    with fila_global(db):
        svc.create_process(db, name="Global", category="x", key="incidencias", organization_id=None)
    assert svc.clave_unica(db, "incidencias", "1") == "incidencias_2"
    svc.create_process(db, name="Propia", category="x", key="incidencias", organization_id="1")
    with sin_filtro_de_tenant(db):
        nombres = [p.name for p in svc.list_processes(db, organization_id="1") if p.key == "incidencias"]
    assert nombres == ["Propia"]


# 5 ── Git: los ids son UUID; listar y abrir un PR real no da 500
def test_git_lista_y_abre_un_pr_real(client, admin_token, db):
    from app.models.git_integration import GitPullRequest
    from app.models.task import Task
    p = _proyecto(db)
    t = Task(code="T-GIT", title="Tarea git", project_id=p.id, created_by="admin-test-id")
    db.add(t)
    db.flush()
    pr = GitPullRequest(repo_full_name="org/repo", pr_number=7, project_id=p.id, task_id=t.id)
    db.add(pr)
    db.commit()
    h = auth(admin_token)
    r = client.get("/api/v1/git/pull-requests", headers=h, params={"project_id": p.id})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["items"]] == [pr.id]
    assert client.get(f"/api/v1/git/pull-requests/{pr.id}", headers=h).json()["data"]["task_id"] == t.id
    assert client.get(f"/api/v1/git/tasks/{t.id}/pr-status", headers=h).json()["data"]["pr"]["id"] == pr.id
