"""Plantillas de proyecto: un solo servicio (rev. 173, 16-11-2026).

Había tres puertas sobre las mismas tablas (`project_templates` y sus hijas),
cada una con su copia: `billing_reports_service/plantillas.py` (la que usaba la
pantalla: alta, lista e instanciar), `advanced_config_service/plantillas.py`
(alta, lista, borrar, aplicar a un proyecto, exportar, documentos y roles) y
`POST /projects/{id}/export-template`, que **no hacía nada** (devolvía siempre
`{"template_id": "tpl-123"}`). Las dos copias de «crear» y de «listar»
guardaban y devolvían cosas distintas, e instanciar no copiaba riesgos ni
entregables mientras que aplicar sí.

Ahora todo pasa por aquí, y las tres puertas llaman a estas funciones. Una
plantilla lleva:

  · fases y tareas (con su rol y su duración en días laborables);
  · **dependencias** entre tareas (FS/SS/FF/SF con desfase);
  · roles (qué perfil, cuántas horas), documentos requeridos, riesgos y
    entregables.

Aplicarla crea fases, tareas, dependencias, riesgos, entregables (los
documentos requeridos también, como entregables) y **planifica las fechas con
el planificador** (camino crítico con el calendario de la empresa). Crear una
plantilla desde un proyecto hace el camino inverso.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.advanced_config import (
    ProjectTemplate, TemplateDeliverable, TemplatePhase, TemplateRisk, TemplateTask, TemplateTaskDependency,
)
from app.models.marketplace import TemplateDocument, TemplateRole

TIPOS_DE_DEPENDENCIA = ("FS", "SS", "FF", "SF")


def _org(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def _enum(valor, defecto: str) -> str:
    if valor is None:
        return defecto
    return getattr(valor, "value", None) or str(valor)


def propia(db: Session, user, template_id: str) -> ProjectTemplate:
    """La plantilla, si es de la empresa del usuario. 404 si no."""
    q = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id)
    if user is not None and not getattr(user, "is_superadmin", False):
        q = q.filter(ProjectTemplate.organization_id == _org(user))
    t = q.first()
    if not t:
        raise ErrorDeDominio(404, "Plantilla no encontrada")
    return t


# ── Lectura ──────────────────────────────────────────────────────────────────

def _cargar(db: Session, filtro):
    return (db.query(ProjectTemplate)
            .options(joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
                     joinedload(ProjectTemplate.risks), joinedload(ProjectTemplate.deliverables))
            .filter(filtro))


def detalle(db: Session, t: ProjectTemplate) -> dict:
    deps = db.query(TemplateTaskDependency).filter(TemplateTaskDependency.template_id == t.id).all()
    documentos = db.query(TemplateDocument).filter(TemplateDocument.template_id == t.id).all()
    roles = db.query(TemplateRole).filter(TemplateRole.template_id == t.id).all()
    fases = sorted(t.phases, key=lambda x: x.order or 0)
    return {
        "id": t.id, "name": t.name, "description": t.description, "project_type": t.project_type,
        "estimated_weeks": t.estimated_weeks, "estimated_hours": t.estimated_hours,
        "is_active": bool(t.is_active),
        "phase_count": len(fases), "task_count": sum(len(p.tasks) for p in fases),
        "risk_count": len(t.risks), "deliverable_count": len(t.deliverables),
        "document_count": len(documentos), "role_count": len(roles), "dependency_count": len(deps),
        "phases": [{
            "id": p.id, "name": p.name, "description": p.description, "order": p.order,
            "estimated_weeks": p.estimated_weeks, "estimated_hours": p.estimated_hours,
            "tasks": [{"id": k.id, "title": k.title, "description": k.description,
                       "estimated_hours": k.estimated_hours, "skill_required": k.skill_required,
                       "role_name": k.role_name, "duration_days": k.duration_days, "order": k.order}
                      for k in sorted(p.tasks, key=lambda x: x.order or 0)],
        } for p in fases],
        "dependencies": [{"id": d.id, "predecessor_id": d.predecessor_id, "successor_id": d.successor_id,
                          "dependency_type": d.dependency_type, "lag_days": d.lag_days} for d in deps],
        "risks": [{"id": r.id, "title": r.title, "category": r.category, "probability": r.probability,
                   "impact": r.impact, "mitigation_plan": r.mitigation_plan} for r in t.risks],
        "deliverables": [{"id": d.id, "name": d.name, "format": d.format,
                          "acceptance_criteria": d.acceptance_criteria, "week_offset": d.week_offset,
                          "billing_pct": d.billing_pct} for d in t.deliverables],
        "documents": [{"id": d.id, "name": d.name, "document_type": d.document_type,
                       "description": d.description, "url": d.url, "is_required": d.is_required,
                       "due_week_offset": d.due_week_offset} for d in documentos],
        "roles": [{"id": r.id, "role_name": r.role_name, "skill_required": r.skill_required,
                   "min_seniority": r.min_seniority, "estimated_hours": r.estimated_hours,
                   "is_mandatory": r.is_mandatory, "notes": r.notes} for r in roles],
    }


def listar(db: Session, user) -> list[dict]:
    filtro = ProjectTemplate.is_active.is_(True)
    q = _cargar(db, filtro)
    if user is not None and not getattr(user, "is_superadmin", False):
        q = q.filter(ProjectTemplate.organization_id == _org(user))
    return [detalle(db, t) for t in q.order_by(ProjectTemplate.name).all()]


def obtener(db: Session, user, template_id: str) -> dict:
    propia(db, user, template_id)
    return detalle(db, _cargar(db, ProjectTemplate.id == template_id).first())


# ── Alta y baja ──────────────────────────────────────────────────────────────

def crear(db: Session, user, datos: dict) -> ProjectTemplate:
    """Plantilla con fases, tareas, dependencias, riesgos, entregables, documentos y roles.

    Las dependencias se dan con las claves de las tareas en el propio cuerpo:
    cada tarea puede llevar `key` (si no, «fase.tarea» por posición) y cada
    dependencia `predecessor`/`successor` con esas claves.
    """
    from app.services.audit import audit_log

    if not (datos.get("name") or "").strip():
        raise ErrorDeDominio(422, "La plantilla necesita un nombre")
    org = _org(user)
    t = ProjectTemplate(organization_id=org, name=datos["name"].strip(), description=datos.get("description"),
                        project_type=datos.get("project_type"), estimated_weeks=datos.get("estimated_weeks"),
                        estimated_hours=datos.get("estimated_hours"), created_by=getattr(user, "id", None))
    db.add(t)
    db.flush()
    claves: dict[str, str] = {}
    for i, fd in enumerate(datos.get("phases") or []):
        fase = TemplatePhase(organization_id=org, template_id=t.id, name=fd.get("name") or f"{i + 1}",
                             description=fd.get("description"),
                             order=fd.get("order", fd.get("phase_order", i)),
                             estimated_weeks=fd.get("estimated_weeks"), estimated_hours=fd.get("estimated_hours"))
        db.add(fase)
        db.flush()
        for j, kd in enumerate(fd.get("tasks") or []):
            tarea = TemplateTask(organization_id=org, phase_id=fase.id, title=kd.get("title") or "",
                                 description=kd.get("description"), estimated_hours=kd.get("estimated_hours"),
                                 skill_required=kd.get("skill_required") or kd.get("role_required"),
                                 role_name=kd.get("role_name"), duration_days=kd.get("duration_days"),
                                 order=kd.get("order", kd.get("task_order", j)))
            db.add(tarea)
            db.flush()
            claves[str(kd.get("key") or f"{i}.{j}")] = tarea.id
    for dd in datos.get("dependencies") or []:
        pred, suc = claves.get(str(dd.get("predecessor"))), claves.get(str(dd.get("successor")))
        tipo = (dd.get("dependency_type") or "FS").upper()
        if not pred or not suc or pred == suc:
            raise ErrorDeDominio(422, "Una dependencia de la plantilla apunta a una tarea que no está")
        if tipo not in TIPOS_DE_DEPENDENCIA:
            raise ErrorDeDominio(422, f"Tipo de dependencia no válido: {tipo}")
        db.add(TemplateTaskDependency(organization_id=org, template_id=t.id, predecessor_id=pred,
                                      successor_id=suc, dependency_type=tipo, lag_days=int(dd.get("lag_days") or 0)))
    for rd in datos.get("risks") or []:
        db.add(TemplateRisk(organization_id=org, template_id=t.id, title=rd.get("title") or "",
                            category=rd.get("category"), probability=rd.get("probability") or "medium",
                            impact=rd.get("impact") or "moderate", mitigation_plan=rd.get("mitigation_plan")))
    for ed in datos.get("deliverables") or []:
        db.add(TemplateDeliverable(
            organization_id=org, template_id=t.id, name=ed.get("name") or ed.get("title") or "",
            format=ed.get("format"), acceptance_criteria=ed.get("acceptance_criteria"),
            week_offset=ed.get("week_offset") if ed.get("week_offset") is not None else ed.get("deliverable_order"),
            billing_pct=ed.get("billing_pct")))
    for dd in datos.get("documents") or []:
        db.add(TemplateDocument(organization_id=org, template_id=t.id, name=dd.get("name") or "",
                                document_type=dd.get("document_type") or "spec", description=dd.get("description"),
                                url=dd.get("url"), is_required=bool(dd.get("is_required")),
                                due_week_offset=dd.get("due_week_offset")))
    for rd in datos.get("roles") or []:
        db.add(TemplateRole(organization_id=org, template_id=t.id,
                            role_name=rd.get("role_name") or rd.get("name") or "",
                            skill_required=rd.get("skill_required"), min_seniority=rd.get("min_seniority"),
                            estimated_hours=rd.get("estimated_hours"),
                            is_mandatory=bool(rd.get("is_mandatory", True)), notes=rd.get("notes")))
    audit_log(db, user, "CREATE", "project_templates", t.id, t.name)
    db.commit()
    db.refresh(t)
    return t


def borrar(db: Session, user, template_id: str) -> dict:
    from app.services.audit import audit_log
    t = propia(db, user, template_id)
    t.is_active = False
    audit_log(db, user, "DELETE", "project_templates", t.id, t.name)
    db.commit()
    return {"ok": True}


# ── Aplicar e instanciar ─────────────────────────────────────────────────────

def aplicar(db: Session, user, template_id: str, project_id: str, inicio: Optional[date] = None) -> dict:
    """Copia la plantilla en un proyecto y planifica sus fechas con el CPM."""
    from app.models.bookings import DependencyType, TaskDependency
    from app.models.pipeline import Risk
    from app.models.project import Project, ProjectMember, ProjectPhase
    from app.models.resources import Deliverable
    from app.models.task import Task, TaskPriority, TaskStatus
    from app.models.user import User
    from app.services.audit import audit_log
    from app.services.numbering import next_numbered_code
    from app.services.planificador.calendario import calendario_de_empresa
    from app.services.planificador.servicio import aplicar_plan, proyecto_visible

    propia(db, user, template_id)
    proyecto: Project = proyecto_visible(db, user, project_id)
    t = _cargar(db, ProjectTemplate.id == template_id).first()
    org = proyecto.organization_id
    cal = calendario_de_empresa(db, org)
    inicio = cal.siguiente(inicio or proyecto.start_date or timeutil.today())
    if not proyecto.start_date:
        proyecto.start_date = inicio

    # Quién del equipo cubre cada rol: alguien cuyo puesto lo dice, si es uno solo.
    miembros = db.query(User.id, User.job_title).join(ProjectMember, ProjectMember.user_id == User.id).filter(
        ProjectMember.project_id == project_id, ProjectMember.is_active.is_(True)).all()

    def persona_para(rol: Optional[str]) -> Optional[str]:
        if not rol:
            return None
        candidatos = [uid for uid, puesto in miembros if puesto and rol.lower() in puesto.lower()]
        return candidatos[0] if len(candidatos) == 1 else None

    tareas_creadas: dict[str, str] = {}
    inicio_fase = inicio
    for f in sorted(t.phases, key=lambda x: x.order or 0):
        semanas = f.estimated_weeks or 1
        fin_fase = cal.anterior(inicio_fase + timedelta(weeks=semanas) - timedelta(days=1))
        fase = ProjectPhase(organization_id=org, project_id=project_id, name=f.name, description=f.description,
                            order=f.order, budget_hours=f.estimated_hours, start_date=inicio_fase, end_date=fin_fase)
        db.add(fase)
        db.flush()
        for k in sorted(f.tasks, key=lambda x: x.order or 0):
            dias = k.duration_days or (max(1, -(-int(k.estimated_hours) // int(cal.horas_por_dia)))
                                       if k.estimated_hours else 1)
            tarea = Task(organization_id=org, project_id=project_id, phase_id=fase.id,
                         code=next_numbered_code(db, "task", prefix="TSK", padding=5),
                         title=k.title, description=k.description, estimated_hours=k.estimated_hours,
                         tags=k.role_name, assignee_id=persona_para(k.role_name),
                         status=TaskStatus.todo, priority=TaskPriority.medium,
                         start_date=inicio_fase, due_date=cal.fin_desde(inicio_fase, dias),
                         created_by=getattr(user, "id", None))
            db.add(tarea)
            db.flush()
            tareas_creadas[k.id] = tarea.id
        inicio_fase = cal.siguiente(fin_fase + timedelta(days=1))

    tipos = {"FS": DependencyType.finish_to_start, "SS": DependencyType.start_to_start,
             "FF": DependencyType.finish_to_finish, "SF": DependencyType.start_to_finish}
    deps = db.query(TemplateTaskDependency).filter(TemplateTaskDependency.template_id == template_id).all()
    for d in deps:
        if d.predecessor_id in tareas_creadas and d.successor_id in tareas_creadas:
            db.add(TaskDependency(organization_id=org, predecessor_id=tareas_creadas[d.predecessor_id],
                                  successor_id=tareas_creadas[d.successor_id],
                                  dependency_type=tipos.get(d.dependency_type, DependencyType.finish_to_start),
                                  lag_days=d.lag_days or 0, link_type="schedule",
                                  created_by=getattr(user, "id", None)))

    for r in t.risks:
        db.add(Risk(organization_id=org, project_id=project_id,
                    code=next_numbered_code(db, "risk", prefix="RSK", padding=4),
                    title=r.title, category=r.category, probability=r.probability, impact=r.impact,
                    mitigation_plan=r.mitigation_plan, identified_by=getattr(user, "id", None)))
    entregables = [(e.name, e.format, e.billing_pct, e.week_offset) for e in t.deliverables]
    entregables += [(d.name, d.document_type, None, d.due_week_offset)
                    for d in db.query(TemplateDocument).filter(TemplateDocument.template_id == template_id).all()]
    for nombre, formato, pct, semanas in entregables:
        db.add(Deliverable(organization_id=org, project_id=project_id,
                           code=next_numbered_code(db, "deliverable", prefix="DEL", padding=4),
                           name=nombre, format=formato, billing_pct=pct,
                           planned_date=(inicio + timedelta(weeks=semanas)) if semanas is not None else None))
    audit_log(db, user, "APPLY_TEMPLATE", "projects", project_id, proyecto.name,
              new_values={"template_id": template_id, "tasks": len(tareas_creadas), "dependencies": len(deps)})
    db.commit()
    # Las fechas finales las pone el planificador: dependencias + calendario.
    aplicar_plan(db, user, project_id)
    return {"ok": True, "project_id": project_id, "phases_created": len(t.phases),
            "tasks_created": len(tareas_creadas), "dependencies_created": len(deps),
            "risks_created": len(t.risks), "deliverables_created": len(entregables)}


def instanciar(db: Session, user, template_id: str, datos: dict) -> dict:
    """Proyecto nuevo desde una plantilla (lo que hacía «instantiate»)."""
    from app.core.config import settings
    from app.models.project import Project
    from app.services.numbering import next_numbered_code
    from app.services.settings_service import get_runtime_str

    t = propia(db, user, template_id)
    org = _org(user)
    inicio = date.fromisoformat(datos["start_date"]) if datos.get("start_date") else timeutil.today()
    proyecto = Project(
        organization_id=org,
        code=datos.get("code") or next_numbered_code(db, "project", prefix="PRJ", padding=4),
        name=datos.get("name") or f"{t.name} — {inicio.isoformat()}",
        description=datos.get("description", t.description),
        project_type=t.project_type or get_runtime_str(db, "DEFAULT_PROJECT_TYPE", org) or settings.DEFAULT_PROJECT_TYPE,
        client_name=datos.get("client_name"), client_id=datos.get("client_id"), pm_id=datos.get("pm_id"),
        start_date=inicio,
        end_date_planned=(inicio + timedelta(weeks=t.estimated_weeks)) if t.estimated_weeks else None,
        budget_hours=t.estimated_hours, budget_amount=datos.get("budget_amount"),
        billing_type=datos.get("billing_type") or get_runtime_str(db, "DEFAULT_BILLING_TYPE", org)
        or settings.DEFAULT_BILLING_TYPE,
        is_billable=datos.get("is_billable", True), created_by=getattr(user, "id", None),
    )
    db.add(proyecto)
    db.commit()
    resultado = aplicar(db, user, template_id, proyecto.id, inicio)
    return {**resultado, "project_code": proyecto.code, "project_name": proyecto.name}


# ── Desde un proyecto ────────────────────────────────────────────────────────

def crear_desde_proyecto(db: Session, user, project_id: str, nombre: Optional[str],
                         descripcion: Optional[str]) -> dict:
    """Plantilla a partir de un proyecto: fases, tareas (rol y duración), dependencias,
    riesgos, entregables, documentos y los roles del equipo."""
    from app.models.bookings import TaskDependency
    from app.models.documents import Document
    from app.models.pipeline import Risk
    from app.models.project import ProjectMember, ProjectPhase
    from app.models.resources import Deliverable
    from app.models.task import Task, TaskStatus
    from app.models.user import User
    from app.services.planificador.calendario import calendario_de_empresa
    from app.services.planificador.servicio import proyecto_visible

    proyecto = proyecto_visible(db, user, project_id)
    cal = calendario_de_empresa(db, proyecto.organization_id)
    inicio = proyecto.start_date or timeutil.today()
    puestos = dict(db.query(User.id, User.job_title).join(ProjectMember, ProjectMember.user_id == User.id)
                   .filter(ProjectMember.project_id == project_id).all())
    fases = db.query(ProjectPhase).filter(ProjectPhase.project_id == project_id,
                                          ProjectPhase.is_active.is_(True)).order_by(ProjectPhase.order).all()
    tareas = db.query(Task).filter(Task.project_id == project_id, Task.is_active.is_(True),
                                   Task.status != TaskStatus.cancelled).all()

    def tarea_dict(t: Task) -> dict:
        return {"key": t.id, "title": t.title, "description": t.description, "estimated_hours": t.estimated_hours,
                "role_name": puestos.get(t.assignee_id),
                "duration_days": cal.duracion(t.start_date, t.due_date) if (t.start_date and t.due_date) else None}

    def semanas(a: Optional[date], b: Optional[date]) -> Optional[int]:
        return max(1, -(-((b - a).days + 1) // 7)) if (a and b and b >= a) else None

    datos_fases = [{"name": f.name, "description": f.description, "order": f.order,
                    "estimated_weeks": semanas(f.start_date, f.end_date), "estimated_hours": f.budget_hours,
                    "tasks": [tarea_dict(t) for t in tareas if t.phase_id == f.id]} for f in fases]
    sueltas = [tarea_dict(t) for t in tareas if t.phase_id not in {f.id for f in fases}]
    if sueltas:
        datos_fases.append({"name": proyecto.name, "order": len(datos_fases), "tasks": sueltas})
    ids = {t.id for t in tareas}
    deps = [{"predecessor": d.predecessor_id, "successor": d.successor_id,
             "dependency_type": getattr(d.dependency_type, "value", d.dependency_type), "lag_days": d.lag_days or 0}
            for d in db.query(TaskDependency).filter(TaskDependency.predecessor_id.in_(ids),
                                                     TaskDependency.successor_id.in_(ids),
                                                     TaskDependency.is_active.is_(True),
                                                     TaskDependency.link_type == "schedule").all()] if ids else []
    horas_por_rol: dict[str, float] = {}
    for t in tareas:
        rol = puestos.get(t.assignee_id)
        if rol:
            horas_por_rol[rol] = horas_por_rol.get(rol, 0.0) + (t.estimated_hours or 0)
    riesgos = [{"title": r.title, "category": r.category, "probability": _enum(r.probability, "medium"),
                "impact": _enum(r.impact, "moderate"), "mitigation_plan": r.mitigation_plan}
               for r in db.query(Risk).filter(Risk.project_id == project_id).all()]
    plantilla = crear(db, user, {
        "name": nombre or proyecto.name, "description": descripcion or proyecto.description,
        "project_type": _enum(proyecto.project_type, ""),
        "estimated_weeks": semanas(proyecto.start_date, proyecto.end_date_planned),
        "estimated_hours": proyecto.budget_hours,
        "phases": datos_fases, "dependencies": deps,
        "risks": riesgos,
        "deliverables": [{"name": d.name, "format": d.format, "billing_pct": d.billing_pct,
                          "week_offset": ((d.planned_date - inicio).days // 7) if d.planned_date else None}
                         for d in db.query(Deliverable).filter(Deliverable.project_id == project_id).all()],
        "documents": [{"name": d.title, "document_type": "other", "is_required": False}
                      for d in db.query(Document).filter(Document.project_id == project_id).all()],
        "roles": [{"role_name": rol, "estimated_hours": round(h, 1)} for rol, h in sorted(horas_por_rol.items())],
    })
    return {"template_id": plantilla.id, "name": plantilla.name, "tasks_exported": len(tareas),
            "dependencies_exported": len(deps),
            # El contrato de `export_project_as_template` (antes de la rev. 173) lo traia.
            "risks_exported": len(riesgos), "created": True}
