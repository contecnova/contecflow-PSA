"""
bi_gdpr.py — GDPR BI compliance endpoints.

Routes:
  POST /bi/gdpr/consent                 — record user consent
  GET  /bi/gdpr/consent/{user_id}       — get consent for a user
  GET  /bi/gdpr/consents                — list all consents (admin)
  POST /bi/gdpr/dsr                     — create a DSR
  PATCH /bi/gdpr/dsr/{dsr_id}/resolve   — resolve a DSR
  GET  /bi/gdpr/dsr                     — list DSRs
  POST /bi/gdpr/field-masks             — register a field mask
  GET  /bi/gdpr/field-masks             — list field masks
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services import bi_gdpr_service as svc

router = APIRouter()


class ConsentIn(BaseModel):
    user_id: str
    consented: bool


class DSRIn(BaseModel):
    subject_id: str
    request_type: str = Field(..., pattern="^(erasure|portability|rectification|restriction)$")
    notes: Optional[str] = None


class DSRResolveIn(BaseModel):
    resolution_notes: Optional[str] = None


class FieldMaskIn(BaseModel):
    dataset: str = Field(..., min_length=1, max_length=100)
    field: str = Field(..., min_length=1, max_length=100)
    mask_type: str = Field("pseudonymize", pattern="^(pseudonymize|suppress|hash|redact)$")


@router.post("/bi/gdpr/consent", summary="Registrar consentimiento de usuario para BI analytics")
@limiter.limit("30/minute")
def record_consent(
    request: Request,
    body: ConsentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.record_consent(db, user_id=body.user_id, consented=body.consented, org_id=org_id)


@router.get("/bi/gdpr/consent/{user_id}", summary="Obtener estado de consentimiento de un usuario")
@limiter.limit("60/minute")
def get_consent(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    result = svc.get_consent(db, user_id=user_id, org_id=org_id)
    if result is None:
        return {"user_id": user_id, "consented": None, "updated_at": None}
    return result


@router.get("/bi/gdpr/consents", summary="Listar todos los consentimientos (admin)")
@limiter.limit("30/minute")
def list_consents(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_consents(db, org_id=org_id)
    return {"items": items, "count": len(items)}


@router.post("/bi/gdpr/dsr", summary="Crear solicitud de derechos GDPR (DSR)", status_code=201)
@limiter.limit("20/minute")
def create_dsr(
    request: Request,
    body: DSRIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.create_dsr(
        db,
        subject_id=body.subject_id,
        request_type=body.request_type,
        org_id=org_id,
        requester_user_id=current_user.id,
        notes=body.notes,
    )


@router.patch("/bi/gdpr/dsr/{dsr_id}/resolve", summary="Resolver una DSR")
@limiter.limit("20/minute")
def resolve_dsr(
    request: Request,
    dsr_id: str,
    body: DSRResolveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.resolve_dsr(db, dsr_id=dsr_id, org_id=org_id, resolution_notes=body.resolution_notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/bi/gdpr/dsr/{dsr_id}/resolve", summary="Resolver una DSR")
@limiter.limit("20/minute")
def resolve_dsr(
    request: Request,
    dsr_id: str,
    body: DSRResolveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.resolve_dsr(db, dsr_id=dsr_id, org_id=org_id, resolution_notes=body.resolution_notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/bi/gdpr/dsr/{dsr_id}/erasure-execute", summary="Ejecutar pipeline de borrado/anonimización GDPR real")
@limiter.limit("5/minute")
def execute_erasure(
    request: Request,
    dsr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Physically anonymise all personal data for the subject referenced in a DSR.
    DSR must exist and be of type 'erasure'. Automatically resolves the DSR after execution.
    Requires admin role.
    """
    if getattr(current_user, "role", None) not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin role required for erasure execution")
    org_id = getattr(current_user, "organization_id", None)
    try:
        dsr_list = svc.list_dsrs(db, org_id=org_id)
        dsr = next((d for d in dsr_list if d["id"] == dsr_id), None)
        if not dsr:
            raise HTTPException(status_code=404, detail="DSR not found")
        if dsr["request_type"] != "erasure":
            raise HTTPException(status_code=422, detail="DSR is not an erasure request")
        report = svc.execute_erasure(db, subject_id=dsr["subject_id"], org_id=org_id)
        # Auto-resolve the DSR
        svc.resolve_dsr(db, dsr_id=dsr_id, org_id=org_id, resolution_notes="Erasure pipeline executed automatically")
        return {"ok": True, "dsr_id": dsr_id, "erasure_report": report}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/bi/gdpr/dsr", summary="Listar solicitudes DSR")
@limiter.limit("30/minute")
def list_dsrs(
    request: Request,
    status: Optional[str] = Query(None, description="pending | resolved"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_dsrs(db, org_id=org_id, status=status)
    return {"items": items, "count": len(items)}


@router.post("/bi/gdpr/field-masks", summary="Registrar máscara de campo GDPR en BI", status_code=201)
@limiter.limit("20/minute")
def set_field_mask(
    request: Request,
    body: FieldMaskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.set_field_mask(db, dataset=body.dataset, field=body.field, mask_type=body.mask_type, org_id=org_id)


@router.get("/bi/gdpr/field-masks", summary="Listar máscaras de campos GDPR")
@limiter.limit("60/minute")
def list_field_masks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_field_masks(db, org_id=org_id)
    return {"items": items, "count": len(items)}
