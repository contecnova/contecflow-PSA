# ---
# Sincronización bidireccional FR <-> ChangeRequest
# Cuando una FeatureRequest (FR) o ChangeRequest (CR) cambia de estado relevante,
# se sincroniza el estado en la entidad asociada.
# - Al aprobar una FR, se crea (si no existe) y vincula un CR en estado 'submitted'.
# - Al pasar la FR a in_development/done/rejected, se actualiza el CR asociado.
# - Al cambiar el CR a approved/implemented/rejected, se actualiza la FR asociada.
# ---
"""
Client Portal API – external-facing endpoints for client users.
Authentication uses separate JWT tokens for ClientUser entities.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Body, Request, Response, Cookie
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import sqlalchemy as sa
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel
from jose import jwt, JWTError
import bcrypt
import uuid
import logging

logger = logging.getLogger("clarive.client_portal")

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import require_any_manager
from app.core.ratelimit import limiter
from app.models.user import User
from app.models.project import Project
from app.models.imputation import Imputation
from app.models.financial import ProjectMilestone
from app.models.billing_reports import Invoice, InvoiceStatus
from app.models.resources import Deliverable, DeliverableStatus
from app.models.client_portal import (
    ClientUser, FeatureRequest, FeatureRequestStatus, UATSession, UATTestCase, UATIssue, UATStatus,
    ClientMessage, ClientSurvey, ClientDocument, client_user_projects
)

router = APIRouter()

CLIENT_TOKEN_EXPIRE_HOURS = 72
CLIENT_TOKEN_SECRET = settings.CLIENT_PORTAL_SECRET
ALGORITHM = "HS256"
PORTAL_SHARE_LINK_EXPIRE_HOURS = 72


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _create_client_token(client_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=CLIENT_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": client_id, "exp": expire, "type": "client"}, CLIENT_TOKEN_SECRET, algorithm=ALGORITHM)


def _create_portal_share_token(project_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=PORTAL_SHARE_LINK_EXPIRE_HOURS)
    return jwt.encode(
        {"project_id": project_id, "exp": expire, "type": "portal_share"},
        CLIENT_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )


def _decode_portal_share_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, CLIENT_TOKEN_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "portal_share":
            return None
        return payload.get("project_id")
    except JWTError:
        return None

def get_current_client(
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> ClientUser:
    credentials_exception = HTTPException(401, "Token de cliente inválido o expirado")
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif portal_access_token:
        token = portal_access_token
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, CLIENT_TOKEN_SECRET, algorithms=[ALGORITHM])
        client_id = payload.get("sub")
        if not client_id or payload.get("type") != "client":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    client = db.query(ClientUser).filter(ClientUser.id == client_id, ClientUser.is_active == True).first()
    if not client:
        raise credentials_exception
    return client


# ── Pydantic schemas ──────────────────────────────────────────────────────────


from pydantic import BaseModel, Field, EmailStr, validator

class ClientLoginIn(BaseModel):
    email: EmailStr = Field(..., max_length=120)
    password: str = Field(..., min_length=8, max_length=128)

class ClientCreateIn(BaseModel):
    project_id: Optional[str] = None        # Legacy single-project (also added to M2M)
    project_ids: Optional[List[str]] = None # Multi-project access list
    client_org_id: Optional[str] = None     # Empresa cliente (entidad Client)
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(..., max_length=120)
    job_title: Optional[str] = Field(None, max_length=80)
    company: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    can_approve_deliverables: bool = True
    can_request_changes: bool = True
    can_view_budget: bool = True
    can_view_team: bool = False
    language: str = Field(settings.DEFAULT_LANGUAGE, min_length=2, max_length=10)

    @validator('full_name')
    def name_must_have_alpha(cls, v):
        if not any(c.isalpha() for c in v):
            raise ValueError('El nombre debe contener letras')
        return v

class FeatureRequestIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    description: str = Field(..., min_length=8, max_length=2000)
    business_justification: Optional[str] = Field(None, max_length=2000)
    affected_area: Optional[str] = Field(None, max_length=120)
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")
    project_id: Optional[str] = None  # For multi-project clients: which project this FR belongs to

class FeatureRequestUpdateIn(BaseModel):
    title: Optional[str] = Field(None, min_length=4, max_length=120)
    description: Optional[str] = Field(None, min_length=8, max_length=2000)
    business_justification: Optional[str] = Field(None, max_length=2000)
    affected_area: Optional[str] = Field(None, max_length=120)
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    project_id: Optional[str] = None

class FeatureRequestWithdrawIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)

class FeatureResponseIn(BaseModel):
    pm_response: Optional[str] = Field(None, min_length=4, max_length=2000)
    estimated_hours: Optional[float] = Field(None, gt=0, lt=10000)
    estimated_cost: Optional[float] = Field(None, ge=0)
    estimated_delivery_weeks: Optional[int] = Field(None, ge=0, le=104)
    status: str = Field("estimated", pattern="^(estimated|approved|rejected|in_development|done)$")

class ClientApprovalIn(BaseModel):
    approved: bool
    reason: Optional[str] = Field(None, max_length=500)

class UATSessionIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    deliverable_id: Optional[str] = None
    test_environment: Optional[str] = Field(None, max_length=200)
    test_credentials: Optional[str] = Field(None, max_length=200)
    test_guide_url: Optional[str] = Field(None, max_length=200)
    available_from: Optional[date] = None
    deadline: Optional[date] = None

class UATTestCaseIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    steps: Optional[str] = Field(None, max_length=2000)
    expected_result: Optional[str] = Field(None, max_length=2000)
    order: int = Field(0, ge=0, le=1000)

class UATResultIn(BaseModel):
    result: str = Field(..., pattern="^(passed|failed|conditional)$")
    notes: Optional[str] = Field(None, max_length=2000)
    test_cases: Optional[List[dict]] = None  # [{id, status, actual_result, notes}]

class UATIssueIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    description: str = Field(..., min_length=8, max_length=2000)
    severity: str = Field("medium", pattern="^(low|medium|high|critical)$")
    steps_to_reproduce: Optional[str] = Field(None, max_length=2000)

class MessageIn(BaseModel):
    subject: Optional[str] = Field(None, max_length=120)
    body: str = Field(..., min_length=2, max_length=2000)
    project_id: Optional[str] = None  # For multi-project clients
    feature_request_id: Optional[str] = None
    uat_session_id: Optional[str] = None
    thread_id: Optional[str] = None
    parent_id: Optional[str] = None
    is_internal: bool = False

class SurveyResponseIn(BaseModel):
    overall_satisfaction: int = Field(..., ge=1, le=5)
    communication_score: int = Field(..., ge=1, le=5)
    quality_score: int = Field(..., ge=1, le=5)
    deadline_score: int = Field(..., ge=1, le=5)
    nps_score: int = Field(..., ge=0, le=10)
    comments: Optional[str] = Field(None, max_length=2000)
    would_recommend: bool = True

class DocumentIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    category: str = Field("general", max_length=40)
    file_url: Optional[str] = Field(None, max_length=500)
    file_name: Optional[str] = Field(None, max_length=200)
    file_size_kb: Optional[int] = Field(None, ge=0, le=100000)
    requires_signature: bool = False


# ── Client Management (PM side) ───────────────────────────────────────────────

@router.get("/clients", summary="Listar clientes del portal")
def list_clients(
    project_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(ClientUser).options(joinedload(ClientUser.project), joinedload(ClientUser.projects))
    if project_id:
        q = q.outerjoin(
            client_user_projects,
            ClientUser.id == client_user_projects.c.client_user_id,
        ).filter(
            sa.or_(
                ClientUser.project_id == project_id,
                client_user_projects.c.project_id == project_id,
            )
        ).distinct()
    if client_org_id: q = q.filter(ClientUser.client_org_id == client_org_id)
    clients = q.order_by(ClientUser.full_name).all()
    return [{
        "id": c.id,
        "project_id": c.project_id,
        "project_ids": c.get_project_ids(),
        "project_name": c.project.name if c.project else (c.projects[0].name if c.projects else None),
        "client_org_id": c.client_org_id,
        "full_name": c.full_name, "email": c.email,
        "job_title": c.job_title, "company": c.company,
        "phone": c.phone,
        "is_active": c.is_active,
        "can_approve_deliverables": c.can_approve_deliverables,
        "can_request_changes": c.can_request_changes,
        "can_view_budget": c.can_view_budget,
        "can_view_team": c.can_view_team,
        "last_login": str(c.last_login)[:16] if c.last_login else None,
        "created_at": str(c.created_at)[:10],
        "portal_url": "/portal",
    } for c in clients]


@router.post("/clients", summary="Crear acceso de cliente al portal")
def create_client(
    payload: ClientCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    all_project_ids = list(dict.fromkeys([*(payload.project_ids or []), *(([payload.project_id]) if payload.project_id else [])]))
    if not all_project_ids and not payload.client_org_id:
        raise HTTPException(400, "Debe especificar al menos un proyecto o una empresa cliente")
    if db.query(ClientUser).filter(ClientUser.email == payload.email).first():
        raise HTTPException(400, "Ya existe un usuario de portal con ese email")
    company = payload.company
    if payload.client_org_id and not company:
        from app.models.clients import Client as ClientOrg
        org = db.query(ClientOrg).filter(ClientOrg.id == payload.client_org_id).first()
        if org: company = org.name
    create_data = {k: v for k, v in payload.model_dump().items()
                   if k not in ("password", "company", "project_ids", "project_id")}
    client = ClientUser(
        **create_data,
        project_id=payload.project_id or (all_project_ids[0] if all_project_ids else None),
        company=company,
        hashed_password=_hash_password(payload.password),
        avatar_initials=payload.full_name[:2].upper(),
    )
    db.add(client); db.flush()  # get id before inserting M2M
    # Populate multi-project junction table
    if all_project_ids:
        from app.models.project import Project
        for pid in all_project_ids:
            proj = db.query(Project).filter(Project.id == pid).first()
            if proj and proj not in client.projects:
                client.projects.append(proj)
    db.commit(); db.refresh(client)
    return {
        "id": client.id,
        "email": client.email,
        "project_ids": client.get_project_ids(),
        "portal_url": "/portal",
        "message": f"Usuario creado. Puede acceder en /portal con {client.email} y la contraseña indicada."
    }


@router.patch("/clients/{client_id}", summary="Actualizar cliente")
def update_client(
    client_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client: raise HTTPException(404, "Cliente no encontrado")
    allowed = ["full_name","email","job_title","company","phone","is_active","project_id",
               "can_approve_deliverables","can_request_changes","can_view_budget","can_view_team","language"]
    project_ids_payload = None
    if "project_ids" in payload:
        project_ids_payload = [pid for pid in (payload.get("project_ids") or []) if pid]
    elif "project_id" in payload:
        project_ids_payload = [payload["project_id"]] if payload.get("project_id") else []
    for k, v in payload.items():
        if k in allowed and k != "project_id":
            setattr(client, k, v)
    if "password" in payload:
        client.hashed_password = _hash_password(payload["password"])
    # Update multi-project access list
    if project_ids_payload is not None:
        from app.models.project import Project
        ordered_ids = list(dict.fromkeys(project_ids_payload))
        client.projects.clear()
        valid_ids = []
        for pid in ordered_ids:
            proj = db.query(Project).filter(Project.id == pid).first()
            if proj:
                client.projects.append(proj)
                valid_ids.append(pid)
        # Update legacy column to first project for backward compat
        client.project_id = valid_ids[0] if valid_ids else None
    db.commit()
    return {"ok": True, "project_ids": client.get_project_ids()}


@router.delete("/clients/{client_id}", summary="Eliminar cliente")
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client: raise HTTPException(404, "Cliente no encontrado")
    db.delete(client); db.commit()
    return {"ok": True}


# ── Client Auth ───────────────────────────────────────────────────────────────

@router.post("/auth/login", summary="Login cliente portal")
@limiter.limit("5/minute")
def client_login(request: Request, response: Response, payload: ClientLoginIn, db: Session = Depends(get_db)):
    client = db.query(ClientUser).filter(ClientUser.email == payload.email, ClientUser.is_active == True).first()
    if not client or not client.hashed_password:
        raise HTTPException(401, "Email o contraseña incorrectos")
    if not _verify_password(payload.password, client.hashed_password):
        raise HTTPException(401, "Email o contraseña incorrectos")
    client.last_login = datetime.now(timezone.utc)
    db.commit()
    token = _create_client_token(client.id)
    response.set_cookie(
        "portal_access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=7 * 86400,
    )
    project_ids = client.get_project_ids()
    projects = []
    if project_ids:
        projects = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status}
                    for p in db.query(Project).filter(Project.id.in_(project_ids)).all()]
    return {
        "ok": True,
        "client": {
            "id": client.id, "full_name": client.full_name, "email": client.email,
            "project_id": client.project_id, "can_approve_deliverables": client.can_approve_deliverables,
            "can_request_changes": client.can_request_changes, "can_view_budget": client.can_view_budget,
            "can_view_team": client.can_view_team, "language": client.language,
            "project_ids": project_ids, "projects": projects,
        }
    }


@router.post("/auth/logout", summary="Cerrar sesión del portal de cliente")
def client_logout(response: Response):
    response.delete_cookie(
        "portal_access_token",
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        path="/",
    )
    return {"detail": "Sesión cerrada correctamente"}


@router.get("/auth/me", summary="Datos del cliente autenticado")
def get_me(current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    project_ids = current_client.get_project_ids()
    projects_info = []
    if project_ids:
        projs = db.query(Project).filter(Project.id.in_(project_ids)).all()
        projects_info = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs]
    return {
        "id": current_client.id, "full_name": current_client.full_name,
        "email": current_client.email, "job_title": current_client.job_title,
        "company": current_client.company, "project_id": current_client.project_id,
        "project_ids": project_ids,
        "projects": projects_info,
        "can_approve_deliverables": current_client.can_approve_deliverables,
        "can_request_changes": current_client.can_request_changes,
        "can_view_budget": current_client.can_view_budget,
        "can_view_team": current_client.can_view_team,
        "language": current_client.language,
    }


@router.get("/branding", summary="Branding del portal para el cliente autenticado")
def get_portal_branding(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.models.clients import ClientPortalConfig, Client

    cfg = None
    client_name = current_client.company
    if current_client.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == current_client.client_org_id).first()
        client_org = db.query(Client).filter(Client.id == current_client.client_org_id).first()
        if client_org and client_org.name:
            client_name = client_org.name

    return {
        "brand_name": client_name or "Portal Cliente",
        "logo_url": cfg.logo_url if cfg else None,
        "primary_color": cfg.accent_color if cfg and cfg.accent_color else "#00d4ff",
    }


@router.get("/invoices", summary="Facturas visibles para el cliente")
def list_client_invoices(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    if not accessible:
        return []
    q = db.query(Invoice).filter(Invoice.project_id.in_(accessible))
    if status:
        q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.issue_date.desc()).limit(200).all()
    return [{
        "id": i.id,
        "number": i.number,
        "project_id": i.project_id,
        "client_name": i.client_name,
        "status": i.status.value if hasattr(i.status, "value") else str(i.status),
        "subtotal": i.subtotal,
        "tax_amount": i.tax_amount,
        "total": i.total,
        "currency": i.currency,
        "issue_date": str(i.issue_date) if i.issue_date else None,
        "due_date": str(i.due_date) if i.due_date else None,
        "paid_date": str(i.paid_date) if i.paid_date else None,
        "notes": i.notes,
    } for i in invoices]


@router.post("/invoices/{invoice_id}/approve", summary="Aprobación de factura por cliente")
def approve_client_invoice(
    invoice_id: str,
    payload: dict = Body(default={}),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    if not accessible:
        raise HTTPException(403, "No hay proyectos asignados a este cliente")

    inv = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.project_id.in_(accessible),
    ).first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")

    approved = bool(payload.get("approved", True))
    reason = (payload.get("reason") or "").strip()
    action = "APROBADA" if approved else "RECHAZADA"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    note_line = f"[{stamp}] Cliente {current_client.full_name} ({current_client.email}) {action}."
    if reason:
        note_line += f" Motivo: {reason}"

    existing = (inv.internal_notes or "").strip()
    inv.internal_notes = f"{existing}\n{note_line}".strip() if existing else note_line

    # If approved and still draft, advance to sent (ready for payment flow)
    if approved and inv.status == InvoiceStatus.draft:
        inv.status = InvoiceStatus.sent

    # Leave public trace in client messages for team follow-up
    db.add(ClientMessage(
        project_id=inv.project_id,
        subject=f"Factura {inv.number} {action.lower()}",
        body=note_line,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
    ))

    db.commit()
    return {
        "ok": True,
        "invoice_id": inv.id,
        "approved": approved,
        "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
    }


@router.post("/share-link/{project_id}", summary="Generar enlace público de estado de proyecto")
def create_public_share_link(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    token = _create_portal_share_token(project_id)
    return {
        "ok": True,
        "token": token,
        "url": f"/portal/view/{token}",
        "expires_in_hours": PORTAL_SHARE_LINK_EXPIRE_HOURS,
    }


@router.get("/view/{token}", summary="Vista pública de estado de proyecto por token")
def view_public_project_status(
    token: str,
    db: Session = Depends(get_db),
):
    project_id = _decode_portal_share_token(token)
    if not project_id:
        raise HTTPException(401, "Token inválido o expirado")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    milestones = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == project.id).order_by(Deliverable.sort_order).all()

    return {
        "project": {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
        },
        "milestones": [{
            "id": m.id,
            "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed,
        } for m in milestones],
        "deliverables": [{
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
        } for d in deliverables],
    }


@router.patch("/auth/me", summary="El cliente actualiza su propio perfil")
def update_my_profile(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    """
    El cliente puede editar campos seguros de su perfil.
    Qué puede cambiar depende de allow_profile_edit en ClientPortalConfig.
    Nunca puede cambiar: email, permisos (can_approve_deliverables, etc.), project_id.
    """
    from app.models.clients import ClientPortalConfig

    # Verificar si tiene permiso para editar perfil
    cfg = db.query(ClientPortalConfig).filter(
        ClientPortalConfig.client_id == current_client.client_org_id
    ).first() if current_client.client_org_id else None

    allow_edit = cfg.allow_profile_edit if cfg else True
    allow_pwd  = cfg.allow_pwd_change   if cfg else True

    # Campos editables por el cliente (nunca email, permisos ni IDs)
    SAFE_FIELDS = {"full_name", "phone", "language", "job_title"}
    has_safe_fields = any(k in SAFE_FIELDS for k in payload if k != "password")
    if not allow_edit and has_safe_fields:
        raise HTTPException(403, "Edición de perfil deshabilitada para este portal")
    BLOCKED     = {"email", "hashed_password", "can_approve_deliverables",
                   "can_request_changes", "can_view_budget", "can_view_team",
                   "project_id", "client_org_id", "is_active", "id"}

    for k, v in payload.items():
        if k in BLOCKED:
            continue  # silently ignore
        if k == "password":
            if not allow_pwd:
                raise HTTPException(403, "El cambio de contraseña está desactivado")
            if len(str(v)) < settings.MIN_PASSWORD_LENGTH:
                raise HTTPException(400, f"La contraseña debe tener al menos {settings.MIN_PASSWORD_LENGTH} caracteres")
            current_client.hashed_password = _hash_password(str(v))
        elif k in SAFE_FIELDS:
            setattr(current_client, k, v)

    db.commit(); db.refresh(current_client)
    return {
        "id": current_client.id,
        "full_name": current_client.full_name,
        "email": current_client.email,
        "phone": current_client.phone,
        "job_title": current_client.job_title,
        "language": current_client.language,
        "message": "Perfil actualizado correctamente",
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", summary="Dashboard del cliente")
def get_client_dashboard(
    project_id: Optional[str] = None,  # explicit project selection for multi-project clients
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible_ids = current_client.get_project_ids()

    # If client has multiple projects and no specific one selected, return selection screen
    if len(accessible_ids) > 1 and not project_id:
        projs = db.query(Project).filter(Project.id.in_(accessible_ids)).all()
        return {
            "needs_project_selection": True,
            "projects": [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs],
        }

    # Determine working project
    effective_id = project_id or (accessible_ids[0] if accessible_ids else None)

    # Validate requested project is accessible to this client
    if effective_id and accessible_ids and effective_id not in accessible_ids:
        raise HTTPException(403, "No tienes acceso a este proyecto")

    if not effective_id:
        return {"project": None, "no_project": True,
                "message": "Este usuario del portal no tiene ningún proyecto asignado. Configúralo en Clientes → Portal Config."}
    project = db.query(Project).filter(Project.id == effective_id).first()
    if not project:
        return {"project": None, "no_project": True,
                "message": "El proyecto asignado no existe. Actualiza la configuración del portal en Clientes → Portal Config."}

    # Budget consumption (visible hours/% not internal cost)
    total_hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == project.id).scalar() or 0
    budget_pct = round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None

    # Milestones
    milestones = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.sort_order).all()
    milestones_done = sum(1 for m in milestones if m.is_completed)

    # Deliverables
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == project.id).all()
    del_accepted = sum(1 for d in deliverables if d.status == DeliverableStatus.accepted)
    del_pending_uat = sum(1 for d in deliverables if d.status == DeliverableStatus.delivered)

    # UATs pending
    uat_pending = db.query(UATSession).filter(
        UATSession.project_id == project.id,
        UATSession.status.in_([UATStatus.pending, UATStatus.in_progress])
    ).count()

    # Feature requests
    fr_open = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project.id,
        FeatureRequest.status.in_([FeatureRequestStatus.new, FeatureRequestStatus.reviewing, FeatureRequestStatus.estimated])
    ).count()

    # Unread messages
    unread = db.query(ClientMessage).filter(
        ClientMessage.project_id == project.id,
        ClientMessage.is_read_by_client == False,
        ClientMessage.sender_client_id == None,
        ClientMessage.is_internal == False,
    ).count()

    # Next milestone
    next_milestone = next((m for m in milestones if not m.is_completed and m.due_date), None)

    days_elapsed = (date.today() - project.start_date).days if project.start_date else 0
    days_total = (project.end_date_planned - project.start_date).days if project.end_date_planned and project.start_date else None
    progress_pct = round(days_elapsed / days_total * 100, 1) if days_total and days_total > 0 else 0

    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "status": project.status, "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "progress_pct": min(progress_pct, 100),
        },
        "kpis": {
            "budget_hours": project.budget_hours,
            "hours_consumed": round(total_hours, 1),
            "budget_pct": budget_pct,
            "milestones_total": len(milestones),
            "milestones_done": milestones_done,
            "deliverables_accepted": del_accepted,
            "deliverables_pending_uat": del_pending_uat,
            "uat_pending": uat_pending,
            "feature_requests_open": fr_open,
            "unread_messages": unread,
        },
        "next_milestone": {
            "name": next_milestone.name,
            "due_date": str(next_milestone.due_date),
            "days_remaining": (next_milestone.due_date - date.today()).days,
        } if next_milestone else None,
        "recent_activity": _get_recent_activity(project.id, db),
    }


def _get_recent_activity(project_id: str, db: Session) -> list:
    activity = []
    # Recent messages from team
    msgs = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.is_internal == False,
        ClientMessage.sender_user_id != None,
    ).order_by(ClientMessage.created_at.desc()).limit(3).all()
    for m in msgs:
        name = m.sender_user.full_name if m.sender_user else "Equipo"
        activity.append({"type": "message", "text": f"Mensaje de {name}: {m.body[:60]}...", "date": str(m.created_at)[:10]})

    # Recent deliverable status changes
    dels = db.query(Deliverable).filter(
        Deliverable.project_id == project_id,
        Deliverable.status.in_([DeliverableStatus.delivered, DeliverableStatus.accepted])
    ).order_by(Deliverable.updated_at.desc()).limit(2).all()
    for d in dels:
        activity.append({"type": "deliverable", "text": f"Entregable disponible: {d.name}", "date": str(d.updated_at or d.created_at)[:10]})

    activity.sort(key=lambda x: x["date"], reverse=True)
    return activity[:5]


# ── Feature Requests ──────────────────────────────────────────────────────────

@router.get("/feature-requests", summary="Mis solicitudes de funcionalidad")
def list_feature_requests(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    q = db.query(FeatureRequest).filter(
        FeatureRequest.project_id.in_(accessible) if len(accessible) > 1
        else FeatureRequest.project_id == accessible[0] if accessible
        else FeatureRequest.project_id == None
    )
    if status: q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    result = []
    for fr in frs:
        item = _fr_out(fr)
        item["can_edit_by_client"] = fr.client_id == current_client.id and str(fr.status) in {
            FeatureRequestStatus.new.value,
            FeatureRequestStatus.reviewing.value,
        }
        result.append(item)
    return result


@router.get("/feature-requests/team", summary="Todas las FRs (equipo interno)")
def list_all_feature_requests(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(FeatureRequest).options(joinedload(FeatureRequest.client), joinedload(FeatureRequest.project))
    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        q = q.filter(FeatureRequest.project.has(Project.organization_id == current_user.organization_id))
    if project_id: q = q.filter(FeatureRequest.project_id == project_id)
    if client_id: q = q.filter(FeatureRequest.client_id == client_id)
    if client_org_id: q = q.filter(FeatureRequest.client.has(ClientUser.client_org_id == client_org_id))
    if status: q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    result = []
    for fr in frs:
        d = _fr_out(fr)
        d["project_name"] = fr.project.name if fr.project else "—"
        d["client_name"] = fr.client.full_name if fr.client else "—"
        result.append(d)
    return result


def _fr_out(fr: FeatureRequest) -> dict:
    STATUS_LABELS = {"new":"Nueva","reviewing":"En revisión","estimated":"Presupuestada","approved":"Aprobada","rejected":"Rechazada","in_development":"En desarrollo","done":"Completada"}
    PRIORITY_LABELS = {"low":"Baja","medium":"Media","high":"Alta","critical":"Crítica"}
    PRIORITY_COLORS = {"low":"#00e5a0","medium":"#00d4ff","high":"#ffb800","critical":"#ff4757"}
    STATUS_COLORS = {"new":"#7a8aaa","reviewing":"#00d4ff","estimated":"#ffb800","approved":"#00e5a0","rejected":"#ff4757","in_development":"#7c3aed","done":"#00e5a0"}
    cr_status = cr_status_label = cr_status_color = None
    if getattr(fr, "change_request_id", None):
        from app.models.resources import ChangeRequest, ChangeRequestStatus
        cr = fr.change_request_id and fr.__dict__.get("_sa_instance_state") and fr._sa_instance_state.session.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr:
            CR_STATUS_LABELS = {"draft": "Borrador", "submitted": "Enviado", "under_review": "En revisión", "approved": "Aprobado", "rejected": "Rechazado", "implemented": "Implementado"}
            CR_STATUS_COLORS = {"draft": "#7a8aaa", "submitted": "#00d4ff", "under_review": "#ffb800", "approved": "#00e5a0", "rejected": "#ff4757", "implemented": "#7c3aed"}
            cr_status = cr.status
            cr_status_label = CR_STATUS_LABELS.get(cr.status, cr.status)
            cr_status_color = CR_STATUS_COLORS.get(cr.status, "#7a8aaa")
    return {
        "id": fr.id, "code": fr.code, "project_id": fr.project_id,
        "project_name": fr.project.name if fr.project else "—",
        "client_id": fr.client_id,
        "title": fr.title, "description": fr.description,
        "business_justification": fr.business_justification,
        "affected_area": fr.affected_area,
        "priority": fr.priority,
        "priority_label": PRIORITY_LABELS.get(fr.priority, fr.priority),
        "priority_color": PRIORITY_COLORS.get(fr.priority, "#7a8aaa"),
        "status": fr.status,
        "status_label": STATUS_LABELS.get(fr.status, fr.status),
        "status_color": STATUS_COLORS.get(fr.status, "#7a8aaa"),
        "pm_response": fr.pm_response,
        "estimated_hours": fr.estimated_hours,
        "estimated_cost": fr.estimated_cost,
        "estimated_delivery_weeks": fr.estimated_delivery_weeks,
        "client_approved": fr.client_approved,
        "client_approved_at": str(fr.client_approved_at)[:10] if fr.client_approved_at else None,
        "submitted_at": str(fr.submitted_at)[:10] if fr.submitted_at else None,
        "updated_at": str(fr.updated_at)[:16] if fr.updated_at else None,
        "change_request_id": getattr(fr, "change_request_id", None),
        "cr_status": cr_status,
        "cr_status_label": cr_status_label,
        "cr_status_color": cr_status_color,
    }


@router.post("/feature-requests", summary="Nueva solicitud de funcionalidad (cliente)")
def create_feature_request(
    payload: FeatureRequestIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    if not current_client.can_request_changes:
        raise HTTPException(403, "No tienes permisos para solicitar cambios")
    accessible = current_client.get_project_ids()
    # For multi-project: use payload.project_id if provided, else first accessible
    target_project_id = getattr(payload, 'project_id', None) or (accessible[0] if accessible else None)
    if not target_project_id:
        raise HTTPException(400, "No tienes un proyecto asignado para enviar solicitudes")
    if accessible and target_project_id not in accessible:
        raise HTTPException(403, "No tienes acceso a ese proyecto")
    import re as _re
    max_fr = db.query(func.max(FeatureRequest.code)).filter(FeatureRequest.project_id == target_project_id).scalar()
    if max_fr:
        _m = _re.search(r"(\d+)$", max_fr)
        next_fr_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_fr_num = 1
    fr_data = payload.model_dump()
    fr_data.pop('project_id', None)
    fr = FeatureRequest(
        code=f"FR-{next_fr_num:03d}",
        project_id=target_project_id,
        client_id=current_client.id,
        **fr_data,
    )
    db.add(fr); db.commit(); db.refresh(fr)
    return _fr_out(fr)


@router.patch("/feature-requests/{fr_id}", summary="Editar solicitud de funcionalidad propia")
def update_feature_request(
    fr_id: str,
    payload: FeatureRequestUpdateIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise HTTPException(404, "FR no encontrada")
    if str(fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise HTTPException(400, "Solo puedes editar solicitudes nuevas o en revisión")

    data = payload.model_dump(exclude_unset=True)
    target_project_id = data.pop("project_id", None)
    if target_project_id is not None:
        if accessible and target_project_id not in accessible:
            raise HTTPException(403, "No tienes acceso a ese proyecto")
        fr.project_id = target_project_id
    for key, value in data.items():
        setattr(fr, key, value)
    db.commit()
    db.refresh(fr)
    item = _fr_out(fr)
    item["can_edit_by_client"] = True
    return item


@router.post("/feature-requests/{fr_id}/withdraw", summary="Retirar solicitud de funcionalidad propia")
def withdraw_feature_request(
    fr_id: str,
    payload: FeatureRequestWithdrawIn = Body(default=FeatureRequestWithdrawIn()),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise HTTPException(404, "FR no encontrada")
    if str(fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise HTTPException(400, "Solo puedes retirar solicitudes nuevas o en revisión")

    fr.status = FeatureRequestStatus.rejected
    fr.client_approved = False
    fr.client_rejection_reason = payload.reason or "Retirada por el cliente desde el portal"
    fr.client_approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fr)
    return _fr_out(fr)


@router.post("/feature-requests/{fr_id}/respond", summary="PM responde a una FR con estimación")
# ---
# FLUJO COORDINADO FEATURE REQUESTS Y CONTROL DE CAMBIOS
#
# - El equipo puede iniciar desarrollo de una FR (status: in_development) desde backend/backoffice sin que se cree un ChangeRequest si el cliente no ha aprobado.
# - Solo la aprobación explícita del cliente (endpoint /decide, approved: true) genera el registro en Control de Cambios.
# - El endpoint /respond solo cambia el estado de la FR, nunca crea ni modifica ChangeRequest.
# - Hay tests automáticos que garantizan este comportamiento y evitan regresiones.
#   Ver: tests/test_portal_feature_requests.py y tests/test_portal_feature_requests_cr_control.py
# ---
def respond_to_fr(
    fr_id: str,
    payload: FeatureResponseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    fr = db.query(FeatureRequest).filter(FeatureRequest.id == fr_id).first()
    if not fr: raise HTTPException(404, "FR no encontrada")
    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        project = db.query(Project).filter(Project.id == fr.project_id).first()
        if not project or project.organization_id != current_user.organization_id:
            raise HTTPException(404, "FR no encontrada")

    # "Responder" se usa también para transiciones internas de estado
    # (p.ej. iniciar desarrollo) donde no tiene sentido exigir pm_response.
    if payload.status == "estimated" and not payload.pm_response:
        raise HTTPException(422, "pm_response es obligatorio para presupuestar una solicitud")

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        setattr(fr, k, v)
    # Sincronizar CR si existe
    cr = None
    if fr.change_request_id:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr:
            # Mapear estados relevantes
            if fr.status == FeatureRequestStatus.in_development:
                cr.status = ChangeRequestStatus.approved
            elif fr.status == FeatureRequestStatus.done:
                cr.status = ChangeRequestStatus.implemented
            elif fr.status == FeatureRequestStatus.rejected:
                cr.status = ChangeRequestStatus.rejected
            db.commit()
    db.commit(); db.refresh(fr)

    # Notificación en tiempo real por WebSocket
    try:
        from app.api.v1.endpoints.ws import manager
        user_id = str(fr.client_id)
        notif = {
            "type": "cr_state_changed",
            "feature_request_id": fr.id,
            "change_request_id": getattr(fr, "change_request_id", None),
            "fr_status": fr.status,
            "cr_status": cr.status if cr else None,
            "title": fr.title,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        import asyncio
        asyncio.create_task(manager.publish(user_id, notif))
    except Exception as e:
        logger.warning(f"No se pudo enviar notificación WS: {e}")
    return _fr_out(fr)


@router.post("/feature-requests/{fr_id}/decide", summary="Cliente aprueba o rechaza FR")
def client_decide_fr(
    fr_id: str,
    payload: ClientApprovalIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.models.client_portal import FeatureRequest, FeatureRequestStatus
    from app.models.resources import ChangeRequest, ChangeRequestStatus, ChangeRequestImpact
    from app.models.billing_reports import ApprovalRequest
    from app.api.v1.endpoints.approvals import _find_default_workflow
    import uuid
    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None
    ).first()
    if not fr:
        raise HTTPException(404, "FR no encontrada")
    if fr.status != FeatureRequestStatus.estimated:
        raise HTTPException(400, "Solo se pueden aprobar FRs con estimación del equipo")
    fr.client_approved = payload.approved
    fr.client_approved_at = datetime.now(timezone.utc)
    fr.client_rejection_reason = payload.reason
    if payload.approved:
        fr.status = FeatureRequestStatus.approved
        # Crear CR si no existe
        cr = None
        if not fr.change_request_id:
            max_cr = db.query(func.max(ChangeRequest.code)).filter(ChangeRequest.project_id == fr.project_id).scalar()
            if max_cr:
                import re as _re
                _m = _re.search(r"(\d+)$", max_cr)
                next_cr_num = (int(_m.group(1)) + 1) if _m else 1
            else:
                next_cr_num = 1
            cr = ChangeRequest(
                id=str(uuid.uuid4()),
                code=f"CR-{next_cr_num:03d}",
                project_id=fr.project_id,
                title=fr.title,
                description=fr.description,
                justification=fr.business_justification,
                impact=ChangeRequestImpact[fr.priority] if fr.priority else ChangeRequestImpact.medium,
                cost_impact=fr.estimated_cost,
                schedule_impact_days=fr.estimated_delivery_weeks * 7 if fr.estimated_delivery_weeks else None,
                scope_impact=fr.affected_area,
                status=ChangeRequestStatus.submitted,
                submitted_at=datetime.now(timezone.utc),
            )
            db.add(cr)
            db.flush()
            fr.change_request_id = cr.id
            # Disparar workflow de aprobaciones
            wf = _find_default_workflow("change_request", db)
            if wf:
                req = ApprovalRequest(
                    id=str(uuid.uuid4()),
                    workflow_id=wf.id,
                    entity_type="change_request",
                    entity_id=cr.id,
                    entity_summary=cr.title,
                    requested_by=None,
                    current_step=1,
                    status="pending",
                )
                db.add(req)
        else:
            cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        # Sincronizar CR si existe
        if cr:
            cr.status = ChangeRequestStatus.approved
            db.commit()
    else:
        fr.status = FeatureRequestStatus.rejected
        # Sincronizar CR si existe
        if fr.change_request_id:
            cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
            if cr:
                cr.status = ChangeRequestStatus.rejected
                db.commit()
    db.commit()
    return _fr_out(fr)


# ── UAT ───────────────────────────────────────────────────────────────────────

def _uat_out(s: UATSession) -> dict:
    STATUS_LABELS = {"pending":"Pendiente","in_progress":"En progreso","passed":"Aprobado","failed":"Rechazado","conditional":"Aprobado con reservas"}
    STATUS_COLORS = {"pending":"#7a8aaa","in_progress":"#00d4ff","passed":"#00e5a0","failed":"#ff4757","conditional":"#ffb800"}
    passed = sum(1 for tc in s.test_cases if tc.status == "passed")
    failed = sum(1 for tc in s.test_cases if tc.status == "failed")
    total = len(s.test_cases)
    return {
        "id": s.id, "code": s.code, "project_id": s.project_id,
        "deliverable_id": s.deliverable_id,
        "title": s.title, "description": s.description,
        "test_environment": s.test_environment,
        "test_credentials": s.test_credentials,
        "test_guide_url": s.test_guide_url,
        "status": s.status,
        "status_label": STATUS_LABELS.get(s.status, s.status),
        "status_color": STATUS_COLORS.get(s.status, "#7a8aaa"),
        "available_from": str(s.available_from) if s.available_from else None,
        "deadline": str(s.deadline) if s.deadline else None,
        "completed_at": str(s.completed_at)[:10] if s.completed_at else None,
        "client_result": s.client_result,
        "client_notes": s.client_notes,
        "test_cases": [{"id": tc.id, "title": tc.title, "steps": tc.steps, "expected_result": tc.expected_result, "actual_result": tc.actual_result, "status": tc.status, "notes": tc.notes, "order": tc.order} for tc in sorted(s.test_cases, key=lambda x: x.order)],
        "issues": [{"id": i.id, "title": i.title, "description": i.description, "severity": i.severity, "status": i.status, "steps_to_reproduce": i.steps_to_reproduce} for i in s.issues],
        "stats": {"total": total, "passed": passed, "failed": failed, "pending": total - passed - failed},
        "overdue": s.deadline and date.today() > s.deadline and s.status in ["pending", "in_progress"],
    }


@router.get("/uat", summary="Mis UATs (cliente)")
def list_uat_client(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases), joinedload(UATSession.issues)
    ).filter(UATSession.project_id.in_(current_client.get_project_ids()) if current_client.get_project_ids() else UATSession.project_id == None)
    if status: q = q.filter(UATSession.status == status)
    return [_uat_out(s) for s in q.order_by(UATSession.created_at.desc()).all()]


@router.get("/uat/team", summary="Todas las UATs (equipo interno)")
def list_uat_team(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(UATSession).options(
        joinedload(UATSession.test_cases), joinedload(UATSession.issues), joinedload(UATSession.project)
    )
    if project_id: q = q.filter(UATSession.project_id == project_id)
    sessions = q.order_by(UATSession.created_at.desc()).all()
    result = []
    for s in sessions:
        d = _uat_out(s)
        d["project_name"] = s.project.name if s.project else "—"
        result.append(d)
    return result


@router.post("/uat", summary="Crear sesión UAT (equipo interno)")
def create_uat(
    payload: UATSessionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    raise HTTPException(400, "Usa POST /uat/{project_id}")


@router.post("/uat/{project_id}", summary="Crear sesión UAT para un proyecto")
def create_uat_for_project(
    project_id: str,
    payload: UATSessionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    import re as _re
    max_uat = db.query(func.max(UATSession.code)).filter(UATSession.project_id == project_id).scalar()
    if max_uat:
        _m = _re.search(r"(\d+)$", max_uat)
        next_uat_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_uat_num = 1
    session = UATSession(project_id=project_id, code=f"UAT-{next_uat_num:03d}", **payload.model_dump())
    db.add(session); db.commit(); db.refresh(session)
    return _uat_out(session)


@router.post("/uat/{uat_id}/test-cases", summary="Añadir caso de prueba")
def add_test_case(
    uat_id: str,
    payload: UATTestCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    tc = UATTestCase(session_id=uat_id, **payload.model_dump())
    db.add(tc); db.commit(); db.refresh(tc)
    return {"id": tc.id, "title": tc.title}


@router.post("/uat/{uat_id}/submit-result", summary="Cliente envía resultado del UAT")
def submit_uat_result(
    uat_id: str,
    payload: UATResultIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    session = db.query(UATSession).options(
        joinedload(UATSession.test_cases)
    ).filter(UATSession.id == uat_id, UATSession.project_id.in_(current_client.get_project_ids()) if current_client.get_project_ids() else UATSession.project_id == None).first()
    if not session: raise HTTPException(404, "UAT no encontrada")
    session.client_result = payload.result
    session.client_notes = payload.notes
    session.status = UATStatus(payload.result) if payload.result in [s.value for s in UATStatus] else UATStatus.passed
    session.completed_at = datetime.now(timezone.utc)
    session.client_signed_by = current_client.id
    session.client_signed_at = datetime.now(timezone.utc)

    # Update test cases if provided
    if payload.test_cases:
        for tc_data in payload.test_cases:
            tc = next((t for t in session.test_cases if t.id == tc_data.get("id")), None)
            if tc:
                tc.status = tc_data.get("status", tc.status)
                tc.actual_result = tc_data.get("actual_result", tc.actual_result)
                tc.notes = tc_data.get("notes", tc.notes)
                tc.tested_at = datetime.now(timezone.utc)
    db.commit()
    return _uat_out(session)


@router.post("/uat/{uat_id}/issues", summary="Reportar incidencia en UAT")
def report_uat_issue(
    uat_id: str,
    payload: UATIssueIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    session = db.query(UATSession).filter(
        UATSession.id == uat_id,
        UATSession.project_id.in_(accessible) if accessible else sa.false(),
    ).first()
    if not session:
        raise HTTPException(403, "No tienes acceso a esta sesión UAT")
    issue = UATIssue(session_id=uat_id, reported_by=current_client.id, **payload.model_dump())
    db.add(issue); db.commit(); db.refresh(issue)
    return {"id": issue.id, "title": issue.title}


@router.patch("/uat/issues/{issue_id}", summary="Actualizar estado de incidencia (equipo)")
def update_issue(
    issue_id: str,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    issue = db.query(UATIssue).filter(UATIssue.id == issue_id).first()
    if not issue: raise HTTPException(404, "Incidencia no encontrada")
    issue.status = status
    if status == "fixed": issue.fixed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ── Messaging ─────────────────────────────────────────────────────────────────

def _msg_out(m: ClientMessage) -> dict:
    return {
        "id": m.id, "project_id": m.project_id,
        "thread_id": m.thread_id or m.id,
        "parent_id": m.parent_id,
        "subject": m.subject, "body": m.body,
        "is_internal": m.is_internal,
        "sender_name": m.sender_client.full_name if m.sender_client else (m.sender_user.full_name if m.sender_user else "Sistema"),
        "sender_type": "client" if m.sender_client_id else "team",
        "is_read_by_client": m.is_read_by_client,
        "is_read_by_team": m.is_read_by_team,
        "feature_request_id": m.feature_request_id,
        "uat_session_id": m.uat_session_id,
        "created_at": str(m.created_at)[:16],
        "replies": [],
    }


@router.get("/messages", summary="Mensajes del proyecto (cliente)")
def get_client_messages(
    thread_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    q = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id.in_(current_client.get_project_ids()) if current_client.get_project_ids() else ClientMessage.project_id == None,
        ClientMessage.is_internal == False,
        ClientMessage.parent_id == None,  # Only top-level
    )
    if thread_id: q = q.filter(ClientMessage.thread_id == thread_id)
    msgs = q.order_by(ClientMessage.created_at.desc()).all()

    # Mark as read
    _acc = current_client.get_project_ids()
    db.query(ClientMessage).filter(
        ClientMessage.project_id.in_(_acc) if _acc else ClientMessage.project_id == None,
        ClientMessage.sender_user_id != None,
        ClientMessage.is_read_by_client == False,
    ).update({"is_read_by_client": True})
    db.commit()

    result = []
    for m in msgs:
        d = _msg_out(m)
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id).order_by(ClientMessage.created_at).all()
        d["replies"] = [_msg_out(r) for r in replies]
        result.append(d)
    return result


@router.get("/messages/team", summary="Mensajes del proyecto (equipo interno)")
def get_team_messages(
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    msgs = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.parent_id == None,
    ).order_by(ClientMessage.created_at.desc()).all()

    db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).update({"is_read_by_team": True})
    db.commit()

    result = []
    for m in msgs:
        d = _msg_out(m)
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id).order_by(ClientMessage.created_at).all()
        d["replies"] = [_msg_out(r) for r in replies]
        result.append(d)
    return result


@router.post("/messages", summary="Enviar mensaje (cliente)")
def send_client_message(
    payload: MessageIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    if not accessible:
        raise HTTPException(403, "No hay proyectos asignados a este cliente")
    msg_project_id = payload.project_id if (hasattr(payload, 'project_id') and payload.project_id) else accessible[0]
    if accessible and msg_project_id and msg_project_id not in accessible:
        raise HTTPException(403, "No tienes acceso a ese proyecto")
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data.pop('project_id', None)
    msg = ClientMessage(
        project_id=msg_project_id,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
        **msg_data,
    )
    if not msg.thread_id: msg.thread_id = str(uuid.uuid4())
    db.add(msg); db.commit(); db.refresh(msg)
    return _msg_out(msg)


@router.post("/messages/team", summary="Enviar mensaje del equipo al cliente")
def send_team_message(
    payload: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    msg = ClientMessage(
        sender_user_id=current_user.id,
        is_read_by_team=True,
        is_read_by_client=False,
        **payload.model_dump(exclude_unset=True),
    )
    if not msg.thread_id: msg.thread_id = str(uuid.uuid4())
    db.add(msg); db.commit(); db.refresh(msg)
    return _msg_out(msg)


# ── Project info (client-safe view) ──────────────────────────────────────────

@router.get("/project", summary="Info del proyecto (cliente)")
def get_project_info(
    project_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    if not accessible:
        raise HTTPException(403, "No hay proyectos asignados a este cliente")
    effective_id = project_id or accessible[0]
    if accessible and effective_id and effective_id not in accessible:
        raise HTTPException(403, "No tienes acceso a ese proyecto")
    project = db.query(Project).filter(Project.id == effective_id).first()
    if not project: raise HTTPException(404)

    milestones = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == project.id).order_by(Deliverable.sort_order).all()

    total_hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == project.id).scalar() or 0

    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "description": project.description, "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "client_name": project.client_name,
        },
        "milestones": [{
            "id": m.id, "name": m.name, "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed, "completed_date": str(m.completed_date) if m.completed_date else None,
            "billing_pct": m.billing_pct,
        } for m in milestones],
        "deliverables": [{
            "id": d.id, "code": d.code, "name": d.name, "format": d.format,
            "status": d.status, "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
            "accepted_date": str(d.accepted_date) if d.accepted_date else None,
        } for d in deliverables],
        "budget": {
            "hours_budget": project.budget_hours,
            "hours_consumed": round(total_hours, 1),
            "pct_consumed": round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None,
        } if current_client.can_view_budget else None,
    }


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/documents", summary="Documentos compartidos (cliente)")
def get_client_documents(
    project_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    accessible = current_client.get_project_ids()
    effective_id = project_id or None
    if effective_id:
        if accessible and effective_id not in accessible:
            raise HTTPException(403, "No tienes acceso a ese proyecto")
        q = db.query(ClientDocument).filter(ClientDocument.project_id == effective_id)
    elif accessible:
        q = db.query(ClientDocument).filter(ClientDocument.project_id.in_(accessible))
    else:
        q = db.query(ClientDocument).filter(ClientDocument.project_id == None)
    docs = q.filter(ClientDocument.is_visible_to_client == True).order_by(ClientDocument.created_at.desc()).all()
    return [_doc_out(d) for d in docs]


@router.get("/documents/team", summary="Todos los documentos (equipo)")
def get_all_documents(
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    docs = db.query(ClientDocument).filter(ClientDocument.project_id == project_id).order_by(ClientDocument.created_at.desc()).all()
    return [_doc_out(d) for d in docs]


def _doc_out(d: ClientDocument) -> dict:
    CAT_LABELS = {"contract": "Contrato", "deliverable": "Entregable", "meeting_notes": "Acta reunión", "report": "Informe", "other": "Otro"}
    return {
        "id": d.id, "title": d.title, "description": d.description,
        "category": d.category, "category_label": CAT_LABELS.get(d.category, d.category),
        "file_url": d.file_url, "file_name": d.file_name, "file_size_kb": d.file_size_kb,
        "requires_signature": d.requires_signature, "signed_by_client": d.signed_by_client,
        "is_visible_to_client": d.is_visible_to_client,
        "created_at": str(d.created_at)[:10],
    }


@router.post("/documents", summary="Subir documento al portal")
def upload_document(
    payload: DocumentIn,
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    doc = ClientDocument(project_id=project_id, uploaded_by=current_user.id, **payload.model_dump())
    db.add(doc); db.commit(); db.refresh(doc)
    return _doc_out(doc)


class SignDocumentIn(BaseModel):
    job_title: Optional[str] = None   # confirmación del cargo del firmante


@router.post("/documents/{doc_id}/sign", summary="Cliente firma documento con certificado PDF")
def sign_document(
    doc_id: str,
    payload: SignDocumentIn = Body(default=SignDocumentIn()),
    request: Request = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    _acc = current_client.get_project_ids()
    if not _acc:
        raise HTTPException(403, "No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc)
    ).first()
    if not doc: raise HTTPException(404, "Documento no encontrado")
    if doc.signed_by_client:
        raise HTTPException(400, "El documento ya fue firmado")

    now = datetime.now(timezone.utc)
    ip  = ""
    if request:
        try:
            ip = request.client.host or ""
        except Exception as e:
            logging.getLogger(__name__).warning(f"No se pudo obtener IP del cliente: {e}")

    # Actualizar BD
    doc.signed_by_client    = True
    doc.signed_at           = now
    doc.signed_by_name      = current_client.full_name
    doc.signed_by_job_title = payload.job_title or getattr(current_client, "job_title", None)
    doc.signature_ip        = ip

    # Obtener nombre del proyecto
    project_name = "—"
    try:
        from app.models.project import Project
        proj = db.query(Project).filter(Project.id == doc.project_id).first()
        if proj: project_name = proj.name
    except Exception:
        pass

    # Generar PDF certificado
    try:
        from app.services.signature_pdf import generate_signed_pdf
        pdf_bytes = generate_signed_pdf(
            document_title       = doc.title,
            document_description = doc.description or "",
            signer_name          = current_client.full_name,
            signer_email         = current_client.email,
            signer_job_title     = doc.signed_by_job_title or "",
            project_name         = project_name,
            signed_at            = now,
            signature_ip         = ip,
            original_file_name   = doc.file_name or "",
        )
        # Guardar PDF en directorio configurable (soporte multiplataforma)
        import os
        from pathlib import Path
        import base64
        pdf_dir = Path(settings.PDF_STORAGE_PATH)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = (pdf_dir / f"signed_{doc_id}.pdf").resolve()
        if pdf_dir.resolve() not in pdf_path.parents:
            raise HTTPException(400, "Ruta de PDF inválida")
        with open(str(pdf_path), "wb") as f:
            f.write(pdf_bytes)
        doc.signed_pdf_path = str(pdf_path)
        # Incluir PDF en base64 en la respuesta para descarga directa
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
    except Exception as e:
        logger.error(f"Error generating PDF signature: {e}", exc_info=True)
        pdf_b64 = None

    db.commit()

    return {
        "ok": True,
        "signed_at":    str(now)[:16],
        "signer_name":  doc.signed_by_name,
        "pdf_b64":      pdf_b64,   # PDF certificado en base64 para descarga
    }


@router.get("/documents/{doc_id}/signed-pdf", summary="Descargar PDF certificado de firma")
def download_signed_pdf(
    doc_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response
    _acc = current_client.get_project_ids()
    if not _acc:
        raise HTTPException(403, "No hay proyectos asignados a este cliente")
    doc = db.query(ClientDocument).filter(
        ClientDocument.id == doc_id,
        ClientDocument.project_id.in_(_acc),
        ClientDocument.signed_by_client == True
    ).first()
    if not doc: raise HTTPException(404)
    if not doc.signed_pdf_path:
        raise HTTPException(404, "PDF de firma no disponible")

    import os
    if not os.path.exists(doc.signed_pdf_path):
        raise HTTPException(404, "Archivo de firma no encontrado en el servidor")

    with open(doc.signed_pdf_path, "rb") as f:
        pdf_bytes = f.read()
    safe_title = doc.title.replace(" ", "_")[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Firmado_{safe_title}.pdf"'}
    )


# ── Wiki (portal cliente — solo páginas con visibility=portal) ──────────────
@router.get("/wiki/pages", summary="Páginas wiki visibles al cliente")
async def portal_wiki_pages(db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    from app.models.epics import WikiPage
    pages = db.query(WikiPage).filter(
        WikiPage.visibility == 'portal',
        WikiPage.is_published == True
    ).order_by(WikiPage.title).all()
    return [{"id": p.id, "title": p.title, "slug": p.slug, "space_id": p.space_id,
             "updated_at": str(p.updated_at)} for p in pages]

@router.get("/wiki/pages/{page_id}", summary="Contenido de página wiki (portal)")
async def portal_wiki_page_detail(page_id: str, db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    from app.models.epics import WikiPage
    page = db.query(WikiPage).filter(WikiPage.id == page_id, WikiPage.visibility == 'portal').first()
    if not page:
        raise HTTPException(status_code=404, detail="Página no encontrada o no visible")
    return {"id": page.id, "title": page.title, "content": page.content,
            "updated_at": str(page.updated_at), "space_id": page.space_id}


# ── Surveys ───────────────────────────────────────────────────────────────────

@router.get("/surveys", summary="Encuestas pendientes (cliente)")
def get_surveys(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.client_id == current_client.id,
    ).order_by(ClientSurvey.sent_at.desc()).all()
    return [_survey_out(s) for s in surveys]


def _survey_out(s: ClientSurvey) -> dict:
    return {
        "id": s.id, "title": s.title, "status": s.status,
        "overall_satisfaction": s.overall_satisfaction,
        "communication_score": s.communication_score,
        "quality_score": s.quality_score,
        "deadline_score": s.deadline_score,
        "nps_score": s.nps_score,
        "comments": s.comments,
        "would_recommend": s.would_recommend,
        "sent_at": str(s.sent_at)[:10],
        "completed_at": str(s.completed_at)[:10] if s.completed_at else None,
    }


@router.post("/surveys", summary="Crear encuesta de satisfacción (equipo)")
def create_survey(
    project_id: str = Query(...),
    client_id: str = Query(...),
    title: str = Query(default="Encuesta de satisfacción"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    survey = ClientSurvey(project_id=project_id, client_id=client_id, title=title)
    db.add(survey); db.commit(); db.refresh(survey)
    return _survey_out(survey)


@router.post("/surveys/{survey_id}/respond", summary="Responder encuesta (cliente)")
def respond_survey(
    survey_id: str,
    payload: SurveyResponseIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    survey = db.query(ClientSurvey).filter(ClientSurvey.id == survey_id, ClientSurvey.client_id == current_client.id).first()
    if not survey: raise HTTPException(404)
    if survey.status != "pending": raise HTTPException(400, "Esta encuesta ya ha sido respondida")
    for k, v in payload.model_dump().items(): setattr(survey, k, v)
    survey.status = "completed"
    survey.completed_at = datetime.now(timezone.utc)
    db.commit()
    return _survey_out(survey)


# ── Stats for PM ──────────────────────────────────────────────────────────────

@router.get("/stats/{project_id}", summary="Estadísticas del portal para un proyecto (equipo)")
def get_portal_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Count both legacy FK and M2M assignments for this project
    legacy_ids = {r[0] for r in db.execute(
        sa.select(ClientUser.id).where(ClientUser.project_id == project_id)
    ).fetchall()}
    m2m_ids = {r[0] for r in db.execute(
        sa.select(client_user_projects.c.client_user_id).where(
            client_user_projects.c.project_id == project_id
        )
    ).fetchall()}
    clients = len(legacy_ids | m2m_ids)
    unread_from_client = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).count()
    fr_pending = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project_id,
        FeatureRequest.status.in_(["new", "reviewing"]),
    ).count()
    uat_pending = db.query(UATSession).filter(
        UATSession.project_id == project_id,
        UATSession.status.in_(["pending", "in_progress"]),
    ).count()
    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.project_id == project_id,
        ClientSurvey.status == "completed",
    ).all()
    avg_nps = round(sum(s.nps_score for s in surveys if s.nps_score) / max(len(surveys), 1), 1) if surveys else None
    avg_satisfaction = round(sum(s.overall_satisfaction for s in surveys if s.overall_satisfaction) / max(len(surveys), 1), 1) if surveys else None

    return {
        "client_count": clients,
        "unread_messages": unread_from_client,
        "fr_pending_review": fr_pending,
        "uat_pending": uat_pending,
        "survey_count": len(surveys),
        "avg_nps": avg_nps,
        "avg_satisfaction": avg_satisfaction,
    }

# ── Traducciones personalizadas del portal ───────────────────────────────────

_TRANSLATIONS_STORE: dict = {}  # En producción usar BD o Redis

@router.get("/translations", summary="Obtener traducciones personalizadas del portal")
async def get_portal_translations(
    current_user: User = Depends(require_any_manager),
):
    return _TRANSLATIONS_STORE

@router.post("/translations", summary="Guardar traducciones personalizadas del portal")
async def save_portal_translations(
    data: dict,
    current_user: User = Depends(require_any_manager),
):
    global _TRANSLATIONS_STORE
    _TRANSLATIONS_STORE.update(data)
    return {"ok": True}
