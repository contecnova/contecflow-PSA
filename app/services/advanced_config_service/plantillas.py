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
from app.models.user import UserRole
from app.core.codigos_de_error import error


# ── Project template application ──────────────────────────────────────────────

def apply_template_to_project(
    template_id: str, project_id: str,
    start_date: Optional[str], user_id: str, user_role: str, db: Session,
) -> dict:
    """Rev. 173: delega en `plantillas_de_proyecto.aplicar` (una sola implementación)."""
    from app.models.user import User
    from app.services.plantillas_de_proyecto import aplicar

    if user_role not in (UserRole.admin, UserRole.pm):
        raise error(403, "sin_permiso", detail="Acceso denegado")
    usuario = db.query(User).filter(User.id == user_id).first()
    inicio = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    r = aplicar(db, usuario, template_id, project_id, inicio)
    return {**r, "message": (
        f"Plantilla aplicada: {r['phases_created']} fases, {r['tasks_created']} tareas, "
        f"{r['risks_created']} riesgos, {r['deliverables_created']} entregables")}


# ── Templates ─────────────────────────────────────────────────────────────────

def list_templates(db: Session, user=None) -> list:
    """Rev. 173: delega en `plantillas_de_proyecto.listar`."""
    from app.services.plantillas_de_proyecto import listar
    return listar(db, user)


def create_template(data: dict, user_id: str, user_role: str, db: Session) -> dict:
    """Rev. 173: delega en `plantillas_de_proyecto.crear`."""
    from app.models.user import User
    from app.services.plantillas_de_proyecto import crear

    if user_role not in (UserRole.admin, UserRole.pm):
        raise error(403, "sin_permiso", detail="Acceso denegado")
    usuario = db.query(User).filter(User.id == user_id).first()
    t = crear(db, usuario, data)
    return {"id": t.id, "name": t.name}


def delete_template(template_id: str, db: Session, user=None) -> dict:
    """Rev. 173: delega en `plantillas_de_proyecto.borrar` (404 si no es de la empresa)."""
    from app.services.plantillas_de_proyecto import borrar
    try:
        return borrar(db, user, template_id)
    except ErrorDeDominio as exc:
        raise NotFoundError(exc.detail)


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
        raise error(404, "no_encontrado", detail="Template not found", que="plantilla")
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
            raise error(404, "no_encontrado", detail="Template not found", que="plantilla")

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
    """Plantilla desde un proyecto. Rev. 173: delega en
    `plantillas_de_proyecto.crear_desde_proyecto`, que además lleva fases,
    dependencias, rol y duración de cada tarea, entregables, documentos y roles.
    (La comprobación de empresa la hace `proyecto_visible`.)"""
    from app.models.user import User
    from app.services.plantillas_de_proyecto import crear_desde_proyecto
    usuario = current_user or db.query(User).filter(User.id == user_id).first()
    return crear_desde_proyecto(db, usuario, project_id, name, description)
