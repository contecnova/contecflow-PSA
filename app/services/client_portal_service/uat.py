"""Pruebas de aceptacion (UAT): campanas, casos, resultados e incidencias.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.client_portal import UATSession, UATStatus
from app.models.client_portal import UATTestCase
from app.models.client_portal import UATIssue
from app.models.project import Project as ProjectModel
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.services.client_portal_service.serializacion import uat_out


# ── UAT ───────────────────────────────────────────────────────────────────────

def list_uat_client(status: Optional[str], current_client, db: Session) -> list:

    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases), joinedload(UATSession.issues)
    ).filter(
        UATSession.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else UATSession.project_id == None
    )
    if status:
        q = q.filter(UATSession.status == status)
    return [uat_out(s) for s in q.order_by(UATSession.created_at.desc()).all()]


def list_uat_team(project_id: Optional[str], db: Session) -> list:

    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases),
        joinedload(UATSession.issues),
        joinedload(UATSession.project)
    )
    if project_id:
        q = q.filter(UATSession.project_id == project_id)
    result = []
    for s in q.order_by(UATSession.created_at.desc()).all():
        d = uat_out(s)
        d["project_name"] = s.project.name if s.project else "—"
        result.append(d)
    return result


def create_uat_for_project(project_id: str, payload, db: Session) -> dict:
    import re as _re

    max_uat = db.query(func.max(UATSession.code)).filter(UATSession.project_id == project_id).scalar()
    if max_uat:
        _m = _re.search(r"(\d+)$", max_uat)
        next_uat_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_uat_num = 1
    session = UATSession(project_id=project_id, code=f"UAT-{next_uat_num:03d}", **payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return uat_out(session)


def add_test_case(uat_id: str, payload, db: Session) -> dict:

    tc = UATTestCase(session_id=uat_id, **payload.model_dump())
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return {"id": tc.id, "title": tc.title}


def submit_uat_result(uat_id: str, payload, current_client, db: Session) -> dict:

    session = db.query(UATSession).options(
        joinedload(UATSession.test_cases)
    ).filter(
        UATSession.id == uat_id,
        UATSession.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else UATSession.project_id == None
    ).first()
    if not session:
        raise ValueError("UAT no encontrada")
    session.client_result = payload.result
    session.client_notes = payload.notes
    session.status = UATStatus(payload.result) if payload.result in [s.value for s in UATStatus] else UATStatus.passed
    session.completed_at = datetime.now(timezone.utc)
    session.client_signed_by = current_client.id
    session.client_signed_at = datetime.now(timezone.utc)
    if payload.test_cases:
        for tc_data in payload.test_cases:
            tc = next((t for t in session.test_cases if t.id == tc_data.get("id")), None)
            if tc:
                tc.status = tc_data.get("status", tc.status)
                tc.actual_result = tc_data.get("actual_result", tc.actual_result)
                tc.notes = tc_data.get("notes", tc.notes)
                tc.tested_at = datetime.now(timezone.utc)
    db.commit()
    return uat_out(session)


def report_uat_issue(uat_id: str, payload, current_client, db: Session) -> dict:
    import sqlalchemy as sa

    accessible = current_client.get_project_ids()
    session = db.query(UATSession).filter(
        UATSession.id == uat_id,
        UATSession.project_id.in_(accessible) if accessible else sa.false(),
    ).first()
    if not session:
        raise ValueError("No tienes acceso a esta sesión UAT")
    issue = UATIssue(session_id=uat_id, reported_by=current_client.id, **payload.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return {"id": issue.id, "title": issue.title}


def update_uat_issue(issue_id: str, status: str, current_user, db: Session) -> dict:
    """Actualiza el estado de una incidencia de UAT (equipo interno).

    current_user es OBLIGATORIO: sin acotar por organización, un manager de la
    organización A podía cambiar el estado de una incidencia de la organización B
    conociendo su id (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §7).

    El scoping va por session -> project -> organization, no por
    UATIssue.organization_id: esa columna existe pero NO se rellena al crear la
    incidencia, así que filtrar por ella dejaría fuera todas las filas.
    Mismo criterio que `respond_to_fr`.
    """
    issue = db.query(UATIssue).filter(UATIssue.id == issue_id).first()
    if not issue:
        raise ValueError("Incidencia no encontrada")

    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        owner_org = (
            db.query(ProjectModel.organization_id)
            .join(UATSession, UATSession.project_id == ProjectModel.id)
            .filter(UATSession.id == issue.session_id)
            .scalar()
        )
        if owner_org and owner_org != current_user.organization_id:
            raise ValueError("Incidencia no encontrada")
    issue.status = status
    if status == "fixed":
        issue.fixed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
