"""Peticiones RGPD: alta, borrado y portabilidad.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from app.models.cab import GDPRRequest
from app.models.cab import GDPRRequestType, GDPRRequestStatus
from app.models.imputation import Imputation as Imp
from app.models.user import User as UserModel
from app.services.audit import audit_log
from app.core import timeutil


# ─── GDPR ─────────────────────────────────────────────────────────────────────

def list_gdpr_requests(db: Session) -> list:
    requests = db.query(GDPRRequest).options(
        joinedload(GDPRRequest.subject_user),
        joinedload(GDPRRequest.processor),
    ).order_by(GDPRRequest.created_at.desc()).all()
    return [{
        "id": r.id, "request_type": r.request_type, "status": r.status,
        "subject_email": r.subject_email or (r.subject_user.email if r.subject_user else None),
        "subject_name": r.subject_user.full_name if r.subject_user else "Usuario eliminado",
        "deadline": str(r.deadline) if r.deadline else None,
        "completed_at": str(r.completed_at)[:10] if r.completed_at else None,
        "processor": r.processor.full_name if r.processor else None,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
        "notes": r.notes,
    } for r in requests]


def create_gdpr_request(payload, current_user, db: Session) -> dict:
    deadline = timeutil.today() + timedelta(days=30)
    req = GDPRRequest(
        request_type=payload.request_type,
        subject_user_id=payload.subject_user_id,
        subject_email=payload.subject_email,
        requestor_id=current_user.id,
        notes=payload.notes,
        deadline=deadline,
    )
    db.add(req)
    audit_log(db, current_user, "GDPR_REQUEST", "users",
              payload.subject_user_id or "unknown",
              payload.subject_email or "",
              new_values={"type": payload.request_type})
    db.commit()
    return {"ok": True, "id": req.id, "deadline": str(deadline)}


def _gdpr_erase_user(db: Session, user) -> dict:
    """Supresión de una persona (el mismo borrado que Gobierno del dato). No guarda su correo original."""
    from app.services.supresion_service import suprimir_persona
    detalle = suprimir_persona(db, user)
    return {"anonymised": True, "tablas": detalle["tablas"], "credenciales": detalle["credenciales"],
            "almacen": detalle["almacen"], "records_kept": ["imputations", "timesheets", "expenses"]}


def _gdpr_portability_export(db: Session, user) -> dict:
    """Build a portability export payload for a user."""
    imputations = db.query(Imp).filter(Imp.user_id == user.id).count()
    return {
        "user": {
            "email": user.email, "full_name": user.full_name,
            "username": user.username, "role": user.role,
            "department": user.department,
            "created_at": str(user.created_at)[:10] if user.created_at else None,
        },
        "data_summary": {"imputations": imputations},
        "export_date": str(timeutil.today()),
        "format": "JSON",
        "note": "Solicite el fichero completo al administrador del sistema.",
    }


def process_gdpr_request(request_id: str, current_user, db: Session) -> dict:
    req = db.query(GDPRRequest).filter(GDPRRequest.id == request_id).first()
    if not req:
        raise ValueError("Solicitud no encontrada")
    if req.status == GDPRRequestStatus.completed:
        raise ValueError("Solicitud ya procesada")

    user = db.query(UserModel).filter(UserModel.id == req.subject_user_id).first() if req.subject_user_id else None
    if req.request_type == GDPRRequestType.erasure and user:
        # Segunda auditoría 2026-11: bajo bloqueo legal, 409 antes de marcarla en curso.
        from app.services.supresion_service import exigir_sin_bloqueo_legal
        exigir_sin_bloqueo_legal(db, user)

    req.status = GDPRRequestStatus.processing
    req.processed_by = current_user.id
    db.commit()
    export_data: dict = {}

    if req.request_type == GDPRRequestType.erasure and user:
        export_data = _gdpr_erase_user(db, user)
    elif req.request_type == GDPRRequestType.portability and user:
        export_data = _gdpr_portability_export(db, user)

    req.status = GDPRRequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.export_data = json.dumps(export_data)
    audit_log(db, current_user, "GDPR_PROCESS", "users",
              req.subject_user_id or "unknown", "",
              new_values={"type": req.request_type, "result": req.status})
    db.commit()
    return {"ok": True, "status": req.status, "data": export_data}
