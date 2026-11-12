"""Plantillas de proyecto: listado, alta, documentos y roles, aplicacion y exportacion desde un proyecto.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from sqlalchemy.orm import Session, joinedload
from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.advanced_config import ProjectTemplate, TemplatePhase
from app.models.advanced_config import TemplateTask, TemplateRisk, TemplateDeliverable
from app.models.marketplace import TemplateDocument
from app.models.marketplace import TemplateRole
from app.models.pipeline import Risk as RiskModel
from app.models.project import Project, ProjectPhase
from app.models.resources import Deliverable
from app.models.task import Task, TaskStatus, TaskPriority

from app.services.advanced_config_service._comun import NotFoundError, logger


# ── Project template application ──────────────────────────────────────────────

def apply_template_to_project(
    template_id: str, project_id: str,
    start_date: Optional[str], user_id: str, user_role: str, db: Session,
) -> dict:

    if user_role not in ("admin", "pm"):
        raise ErrorDeDominio(403, "Acceso denegado")

    template = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not template:
        raise ErrorDeDominio(404, "Plantilla no encontrada")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorDeDominio(404, "Proyecto no encontrado")

    base_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else timeutil.today()
    created_phases = 0
    created_tasks = 0
    created_risks = 0
    created_deliverables = 0

    try:
        for ph in sorted(template.phases, key=lambda x: x.order):
            phase = ProjectPhase(
                project_id=project_id, name=ph.name, description=ph.description,
                order=ph.order, budget_hours=ph.estimated_hours,
            )
            db.add(phase)
            db.flush()
            created_phases += 1
            for tk in sorted(ph.tasks, key=lambda x: x.order):
                db.add(Task(
                    project_id=project_id, phase_id=phase.id,
                    title=tk.title, description=tk.description,
                    estimated_hours=tk.estimated_hours,
                    status=TaskStatus.todo, priority=TaskPriority.medium,
                ))
                created_tasks += 1

        for i, r in enumerate(template.risks):
            from app.models.pipeline import Risk as RiskModel
            db.add(RiskModel(
                project_id=project_id, code=f"RSK-{i+1:03d}",
                title=r.title, category=r.category,
                probability=r.probability, impact=r.impact,
                mitigation_plan=r.mitigation_plan, identified_by=user_id,
            ))
            created_risks += 1

        for i, d in enumerate(template.deliverables):
            planned = None
            if d.week_offset is not None:
                planned = base_date + timedelta(weeks=d.week_offset)
            db.add(Deliverable(
                project_id=project_id, code=f"DEL-{i+1:03d}",
                name=d.name, format=d.format,
                billing_pct=d.billing_pct, planned_date=planned,
            ))
            created_deliverables += 1

        db.commit()
        return {
            "message": (
                f"Plantilla aplicada: {created_phases} fases, "
                f"{created_tasks} tareas, {created_risks} riesgos, "
                f"{created_deliverables} entregables"
            )
        }
    except Exception:
        logger.exception("Failed to apply project template; rolling back")
        db.rollback()
        raise


# ── Templates ─────────────────────────────────────────────────────────────────

def list_templates(db: Session) -> list:
    templates = (
        db.query(ProjectTemplate)
        .options(
            joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
            joinedload(ProjectTemplate.risks),
            joinedload(ProjectTemplate.deliverables),
        )
        .filter(ProjectTemplate.is_active == True)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "project_type": t.project_type, "estimated_weeks": t.estimated_weeks,
            "estimated_hours": t.estimated_hours,
            "phase_count": len(t.phases),
            "task_count": sum(len(p.tasks) for p in t.phases),
            "risk_count": len(t.risks),
            "deliverable_count": len(t.deliverables),
            "phases": [
                {
                    "id": p.id, "name": p.name, "order": p.order,
                    "estimated_weeks": p.estimated_weeks, "estimated_hours": p.estimated_hours,
                    "tasks": [
                        {"id": tk.id, "title": tk.title, "estimated_hours": tk.estimated_hours,
                         "skill_required": tk.skill_required}
                        for tk in p.tasks
                    ],
                }
                for p in sorted(t.phases, key=lambda x: x.order)
            ],
            "risks": [
                {"id": r.id, "title": r.title, "category": r.category,
                 "probability": r.probability, "impact": r.impact}
                for r in t.risks
            ],
            "deliverables": [
                {"id": d.id, "name": d.name, "format": d.format,
                 "week_offset": d.week_offset, "billing_pct": d.billing_pct}
                for d in t.deliverables
            ],
        }
        for t in templates
    ]


def create_template(data: dict, user_id: str, user_role: str, db: Session) -> dict:
    if user_role not in ("admin", "pm"):
        raise ErrorDeDominio(403, "Acceso denegado")
    try:
        t = ProjectTemplate(
            name=data["name"],
            description=data.get("description"),
            project_type=data.get("project_type"),
            estimated_weeks=data.get("estimated_weeks"),
            estimated_hours=data.get("estimated_hours"),
            created_by=user_id,
        )
        db.add(t)
        db.flush()
        for i, ph in enumerate(data.get("phases") or []):
            phase = TemplatePhase(
                template_id=t.id,
                name=ph["name"],
                description=ph.get("description"),
                order=ph.get("order") or i,
                estimated_weeks=ph.get("estimated_weeks"),
                estimated_hours=ph.get("estimated_hours"),
            )
            db.add(phase)
            db.flush()
            for j, tk in enumerate(ph.get("tasks") or []):
                db.add(TemplateTask(
                    phase_id=phase.id,
                    title=tk.get("title", ""),
                    estimated_hours=tk.get("estimated_hours"),
                    skill_required=tk.get("skill_required"),
                    order=j,
                ))
        for r in data.get("risks") or []:
            db.add(TemplateRisk(
                template_id=t.id,
                title=r.get("title", ""),
                category=r.get("category"),
                probability=r.get("probability", "medium"),
                impact=r.get("impact", "moderate"),
                mitigation_plan=r.get("mitigation_plan"),
            ))
        for d in data.get("deliverables") or []:
            db.add(TemplateDeliverable(
                template_id=t.id,
                name=d.get("name", ""),
                format=d.get("format"),
                billing_pct=d.get("billing_pct"),
                week_offset=d.get("week_offset"),
            ))
        db.commit()
        return {"id": t.id, "name": t.name}
    except Exception:
        logger.exception("Failed to persist project template")
        db.rollback()
        raise


def delete_template(template_id: str, db: Session) -> dict:
    t = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATE DOCUMENTS + ROLES (v23.9.0)
# ──────────────────────────────────────────────────────────────────────────────

#: Los valores por defecto de `template_risks`, tal como los declara la tabla.
#: Se usan cuando el riesgo de origen no trae probabilidad o impacto.
PROBABILIDAD_POR_DEFECTO = "medium"
IMPACTO_POR_DEFECTO = "moderate"


def _valor_de_enum(valor, por_defecto: str) -> str:
    """El texto que hay que guardar para un enum de SQLAlchemy.

    Auditoria 2026-08 (hallazgo 22). `export_project_as_template` hacia
    `str(getattr(r, "probability", "medium"))`, y `Risk.probability` es un
    `Enum(RiskProbability)` **NOT NULL**, asi que `str()` no da `"medium"`: da
    `"RiskProbability.medium"`. Medido sobre los diez valores de los dos enums:

        str(RiskProbability.very_low)  -> 'RiskProbability.very_low'   24 chars
        str(RiskProbability.medium)    -> 'RiskProbability.medium'     22 chars
        str(RiskProbability.very_high) -> 'RiskProbability.very_high'  25 chars
        str(RiskImpact.negligible)     -> 'RiskImpact.negligible'      21 chars

    Y `template_risks.probability` es **VARCHAR(20)**. O sea dos defectos, no
    uno:

    1. **Siempre** se guardaba un texto que ningun lector puede volver a
       comparar contra el enum —`"RiskProbability.medium"` no es `"medium"`—,
       asi que la plantilla exportada salia con la probabilidad ilegible;
    2. y en **cuatro de los diez valores**, entre ellos `medium`, que es el
       valor por defecto y el mas frecuente, el texto **no cabe en la
       columna**: en PostgreSQL eso es `value too long for type character
       varying(20)` y la exportacion entera revienta con un 500. En SQLite se
       guarda truncado y en silencio, que es por lo que la suite no lo veia.

    El `getattr(..., por_defecto)` del original tampoco hacia nada: la columna
    es NOT NULL, asi que el atributo esta siempre. El respaldo que si hace
    falta es para `None`, que es lo que se comprueba aqui.
    """
    if valor is None:
        return por_defecto
    return getattr(valor, "value", None) or str(valor)


def plantilla_propia(db: Session, current_user, template_id: str) -> ProjectTemplate:
    """La plantilla, si es de la organizacion del sujeto. 404 si no.

    Auditoria 2026-08 (hallazgo 22): `endpoints/templates.py` tenia su propio
    `_get_template_or_404` que buscaba por id **sin ningun filtro**, y de el
    colgaban las dos altas. Anadir un documento o un rol a la plantilla de otro
    cliente era una escritura cruzada.
    """
    from app.core.tenancy import assert_same_org

    tmpl = (
        db.query(ProjectTemplate)
        .filter(ProjectTemplate.id == template_id)
        .first()
    )
    if not tmpl:
        raise ErrorDeDominio(404, "Template not found")
    assert_same_org(
        current_user, getattr(tmpl, "organization_id", None),
        detail="Template not found")
    return tmpl


def agregar_documento_a_plantilla(
    db: Session, current_user, template_id: str, datos: dict
) -> TemplateDocument:
    """Un documento nuevo en una plantilla propia. No confirma.

    Sustituye a `add_template_document`, que estaba aqui, **no la llamaba
    nadie** —comprobado en `app/` y en `tests/`— y tampoco filtraba por
    organizacion: el endpoint habia reimplementado lo mismo a mano en vez de
    usarla. Dos implementaciones muertas de la misma cosa es exactamente como
    aparecen las dos puertas de §3.septies, asi que se deja una.
    """
    plantilla_propia(db, current_user, template_id)
    doc = TemplateDocument(
        id=str(uuid4()),
        template_id=template_id,
        name=datos.get("name", "Document"),
        document_type=datos.get("document_type", "spec"),
        description=datos.get("description"),
        url=datos.get("url"),
        is_required=bool(datos.get("is_required", False)),
        due_week_offset=datos.get("due_week_offset"),
        organization_id=getattr(current_user, "organization_id", None),
    )
    db.add(doc)
    return doc


def agregar_rol_a_plantilla(
    db: Session, current_user, template_id: str, datos: dict
) -> TemplateRole:
    """Un rol nuevo en una plantilla propia. No confirma.

    Sustituye a `add_template_role`, en las mismas condiciones que el de
    documentos.
    """
    plantilla_propia(db, current_user, template_id)
    rol = TemplateRole(
        id=str(uuid4()),
        template_id=template_id,
        role_name=datos.get("role_name") or datos.get("name", "Role"),
        skill_required=datos.get("skill_required"),
        min_seniority=datos.get("min_seniority"),
        estimated_hours=datos.get("estimated_hours"),
        is_mandatory=bool(datos.get("is_mandatory", True)),
        notes=datos.get("notes"),
        organization_id=getattr(current_user, "organization_id", None),
    )
    db.add(rol)
    return rol


def anadir_documento_a_plantilla(db: Session, user, template_id: str, datos: dict):
    """`agregar_documento_a_plantilla` y confirma (el alta desde la API)."""
    doc = agregar_documento_a_plantilla(db, user, template_id, datos)
    db.commit()
    db.refresh(doc)
    return doc


def anadir_rol_a_plantilla(db: Session, user, template_id: str, datos: dict):
    """`agregar_rol_a_plantilla` y confirma (el alta desde la API)."""
    rol = agregar_rol_a_plantilla(db, user, template_id, datos)
    db.commit()
    db.refresh(rol)
    return rol


def get_full_template(template_id: str, db: Session, current_user=None) -> dict:
    """La plantilla entera con sus fases, tareas, riesgos y entregables.

    Auditoria 2026-08: esta funcion **no recibia al sujeto**, asi que no podia
    comprobar nada aunque quisiera — la misma forma que el endpoint de coste
    activo, que si lo recibia y lo descartaba. Ahora lo recibe, y el
    parametro es opcional por una razon acotada: los llamadores internos que no
    tienen sujeto (scripts, siembra) siguen funcionando. Todo endpoint tiene
    sujeto y **debe** pasarlo.

    El resto de las consultas van por `template_id` de una plantilla ya
    comprobada, asi que el ambito llega por la clave padre.
    """
    if current_user is not None:
        tmpl = plantilla_propia(db, current_user, template_id)
    else:
        tmpl = db.query(ProjectTemplate).filter(
            ProjectTemplate.id == template_id).first()
        if not tmpl:
            raise ErrorDeDominio(404, "Template not found")

    phases = db.query(TemplatePhase).filter(
        TemplatePhase.template_id == template_id
    ).order_by(TemplatePhase.order).all()
    phase_out = []
    for ph in phases:
        tasks = db.query(TemplateTask).filter(
            TemplateTask.phase_id == ph.id
        ).order_by(TemplateTask.order).all()
        phase_out.append({
            "id": ph.id, "name": ph.name, "description": ph.description,
            "order": ph.order, "estimated_weeks": ph.estimated_weeks,
            "estimated_hours": ph.estimated_hours,
            "tasks": [{"id": t.id, "title": t.title, "description": t.description,
                        "estimated_hours": t.estimated_hours, "skill_required": t.skill_required,
                        "order": t.order} for t in tasks],
        })

    risks = db.query(TemplateRisk).filter(TemplateRisk.template_id == template_id).all()
    deliverables = db.query(TemplateDeliverable).filter(
        TemplateDeliverable.template_id == template_id
    ).all()
    documents = db.query(TemplateDocument).filter(
        TemplateDocument.template_id == template_id
    ).all()
    roles = db.query(TemplateRole).filter(TemplateRole.template_id == template_id).all()

    return {
        "id": tmpl.id, "name": tmpl.name, "description": tmpl.description,
        "project_type": tmpl.project_type, "estimated_weeks": tmpl.estimated_weeks,
        "estimated_hours": tmpl.estimated_hours, "is_active": tmpl.is_active,
        "phases": phase_out,
        "risks": [{"id": r.id, "title": r.title, "category": r.category,
                   "probability": r.probability, "impact": r.impact,
                   "mitigation_plan": r.mitigation_plan} for r in risks],
        "deliverables": [{"id": d.id, "name": d.name, "format": d.format,
                           "acceptance_criteria": d.acceptance_criteria,
                           "week_offset": d.week_offset, "billing_pct": d.billing_pct}
                          for d in deliverables],
        "documents": [{"id": d.id, "name": d.name, "document_type": d.document_type,
                        "description": d.description, "url": d.url,
                        "is_required": d.is_required, "due_week_offset": d.due_week_offset}
                       for d in documents],
        "roles": [{"id": r.id, "role_name": r.role_name, "skill_required": r.skill_required,
                   "min_seniority": r.min_seniority, "estimated_hours": r.estimated_hours,
                   "is_mandatory": r.is_mandatory, "notes": r.notes} for r in roles],
    }


def export_project_as_template(
    project_id: str, name, description, user_id: str, db: Session,
    current_user=None,
) -> dict:
    """Convierte un proyecto en plantilla: sus tareas y sus riesgos.

    Auditoria 2026-08 (hallazgo 22). Aqui habia tres cosas:

    1. **Sin comprobar de quien es el proyecto.** Recibia `user_id`, una cadena,
       que no sirve para verificar nada. Cualquiera podia exportar el proyecto de
       otro cliente y quedarse con los titulos de sus tareas y sus riesgos.
    2. **Cinco `hasattr` muertos.** `Project.project_type`, `Task.description`,
       `Task.estimated_hours`, `Risk.category` y `Risk.mitigation_plan` existen
       todos, comprobado. Lo que hacian no era proteger: si alguna columna se
       renombrara, escribirian NULL en silencio en vez de fallar. Fuera.
    3. **El `str()` sobre los enums**, que es el defecto de verdad. Ver el
       docstring de `_valor_de_enum`.

    `current_user` es opcional por lo mismo que en `get_full_template`, y todo
    endpoint debe pasarlo.
    """
    from app.core.tenancy import assert_same_org

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise ErrorDeDominio(404, "Project not found")
    if current_user is not None:
        assert_same_org(
            current_user, getattr(proj, "organization_id", None),
            detail="Project not found")

    org_id = (
        getattr(current_user, "organization_id", None)
        if current_user is not None
        else getattr(proj, "organization_id", None)
    )

    tmpl_name = name or f"Template from {proj.name}"
    tmpl = ProjectTemplate(
        name=tmpl_name,
        description=description or proj.description,
        project_type=proj.project_type,
        created_by=user_id,
        organization_id=org_id,
    )
    db.add(tmpl); db.flush()

    phase = TemplatePhase(template_id=tmpl.id, name="Fase Principal", order=0,
                          organization_id=org_id)
    db.add(phase); db.flush()

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    for i, t in enumerate(tasks):
        db.add(TemplateTask(
            phase_id=phase.id, title=t.title,
            description=t.description,
            estimated_hours=t.estimated_hours,
            order=i,
            organization_id=org_id,
        ))

    risks = db.query(RiskModel).filter(RiskModel.project_id == project_id).all()
    for r in risks:
        db.add(TemplateRisk(
            template_id=tmpl.id, title=r.title,
            category=r.category,
            probability=_valor_de_enum(r.probability, PROBABILIDAD_POR_DEFECTO),
            impact=_valor_de_enum(r.impact, IMPACTO_POR_DEFECTO),
            mitigation_plan=r.mitigation_plan,
            organization_id=org_id,
        ))

    db.commit(); db.refresh(tmpl)
    return {
        "template_id": tmpl.id, "name": tmpl.name,
        "tasks_exported": len(tasks),
        "risks_exported": len(risks),
        "created": True,
    }
