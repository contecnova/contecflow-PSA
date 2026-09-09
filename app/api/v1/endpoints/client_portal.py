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
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from pydantic import BaseModel
from jose import jwt, JWTError
import logging

logger = logging.getLogger("contecflow.client_portal")

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import require_any_manager
from app.core.ratelimit import limiter
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.models.client_portal import (
    ClientUser
)

router = APIRouter()
import app.services.client_portal_service as _svc

CLIENT_TOKEN_EXPIRE_HOURS = _svc.CLIENT_TOKEN_EXPIRE_HOURS
CLIENT_TOKEN_SECRET = _svc.CLIENT_TOKEN_SECRET
ALGORITHM = _svc.ALGORITHM
PORTAL_SHARE_LINK_EXPIRE_HOURS = _svc.PORTAL_SHARE_LINK_EXPIRE_HOURS


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash_password(p: str) -> str:
    return _svc.hash_password(p)

def _verify_password(plain: str, hashed: str) -> bool:
    return _svc.verify_password(plain, hashed)

def _create_client_token(client_id: str) -> str:
    return _svc.create_client_token(client_id)


def _create_portal_share_token(project_id: str) -> str:
    return _svc.create_portal_share_token(project_id)


def _decode_portal_share_token(token: str) -> Optional[str]:
    return _svc.decode_portal_share_token(token)

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
    client = _svc.get_active_client_by_id(db, client_id)
    if not client:
        raise credentials_exception

    # Contexto de tenant en la sesion, igual que hace `get_current_user`.
    #
    # Auditoria 2026-08. Esto no estaba, y `TenantSession` se salta el filtro
    # cuando `info` no trae `is_superadmin` («sesion no inicializada: job de
    # fondo o test»). Con **41 dependencias** de endpoints del portal colgando
    # de aqui, eso significaba que toda consulta del portal sin filtro explicito
    # devolvia filas de todos los clientes. Comprobado con la sesion real: sin
    # contexto un `db.query(Client)` devolvia los de DOS organizaciones; con el,
    # solo los de la suya.
    #
    # Va DESPUES de resolver al cliente, y no antes: `get_active_client_by_id`
    # busca por id sin saber todavia de que organizacion es, asi que esa
    # consulta tiene que correr sin filtrar.
    db.info["organization_id"] = getattr(client, "organization_id", None)
    db.info["is_superadmin"] = False
    db.info["current_client"] = client
    return client


# ── Pydantic schemas ──────────────────────────────────────────────────────────


from pydantic import Field, EmailStr, field_validator

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

    @field_validator('full_name')
    @classmethod
    def name_must_have_alpha(cls, v: str) -> str:
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
    return APIListResponse.ok(items=_svc.list_clients(project_id, client_org_id, db))


@router.post("/clients", summary="Crear acceso de cliente al portal")
def create_client(
    payload: ClientCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.create_client(payload, db))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/clients/{client_id}", summary="Actualizar cliente")
def update_client(
    client_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_client(client_id, payload, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/clients/{client_id}", summary="Eliminar cliente")
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "client_portal_client", client_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_client(client_id, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Client Auth ───────────────────────────────────────────────────────────────

@router.post("/auth/login", summary="Login cliente portal")
@limiter.limit("5/minute")
def client_login(request: Request, response: Response, payload: ClientLoginIn, db: Session = Depends(get_db)):
    try:
        result = _svc.client_login(payload.email, payload.password, db)
    except ValueError as e:
        raise HTTPException(401, str(e))
    token = result["token"]
    response.set_cookie(
        "portal_access_token", token,
        httponly=True, samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=CLIENT_TOKEN_EXPIRE_HOURS * 3600,
    )
    return APIResponse.ok(data={"ok": True, "client": result["client"]})


@router.post("/auth/logout", summary="Cerrar sesión del portal de cliente")
def client_logout(response: Response):
    response.delete_cookie(
        "portal_access_token",
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        path="/",
    )
    return APIResponse.ok(data={"detail": "Sesión cerrada correctamente"})


@router.get("/auth/me", summary="Datos del cliente autenticado")
def get_me(current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    return APIResponse.ok(data=_svc.get_me(current_client, db))


@router.get("/auth/session-config", summary="Configuración de duración de sesión para portal")
def get_portal_session_config(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    _ = current_client
    return APIResponse.ok(data=_svc.get_portal_session_config(db))


@router.get("/branding", summary="Branding del portal para el cliente autenticado")
def get_portal_branding(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=_svc.get_portal_branding(current_client, db))


@router.get("/invoices", summary="Facturas visibles para el cliente")
def list_client_invoices(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.list_client_invoices(status, current_client, db))


@router.post("/invoices/{invoice_id}/approve", summary="Aprobación de factura por cliente")
def approve_client_invoice(
    invoice_id: str,
    payload: dict = Body(default={}),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    approved = bool(payload.get("approved", True))
    reason = (payload.get("reason") or "").strip()
    try:
        return APIResponse.ok(data=_svc.approve_client_invoice(invoice_id, approved, reason, current_client, db))
    except ValueError as e:
        status_code = 403 if "proyectos" in str(e) else 404
        raise HTTPException(status_code, str(e))


@router.post("/share-link/{project_id}", summary="Generar enlace público de estado de proyecto")
def create_public_share_link(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.create_public_share_link(project_id, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/view/{token}", summary="Vista pública de estado de proyecto por token")
def view_public_project_status(
    token: str,
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.view_public_project_status(token, db))
    except ValueError as e:
        status_code = 401 if "Token" in str(e) else 404
        raise HTTPException(status_code, str(e))


@router.patch("/auth/me", summary="El cliente actualiza su propio perfil")
def update_my_profile(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIResponse.ok(data=_svc.update_my_profile(payload, current_client, db, settings.MIN_PASSWORD_LENGTH))
    except ValueError as e:
        status_code = 403 if "deshabilitad" in str(e) or "desactivado" in str(e) else 400
        raise HTTPException(status_code, str(e))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", summary="Dashboard del cliente")
def get_client_dashboard(
    project_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.get_client_dashboard(project_id, current_client, db))
    except ValueError as e:
        raise HTTPException(403, str(e))


def _get_recent_activity(project_id: str, db: Session) -> list:
    return _svc.get_recent_activity(project_id, db)


# ── Feature Requests ──────────────────────────────────────────────────────────

@router.get("/feature-requests", summary="Mis solicitudes de funcionalidad")
def list_feature_requests(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.list_feature_requests(status, current_client, db))


@router.get("/feature-requests/team", summary="Todas las FRs (equipo interno)")
def list_all_feature_requests(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.list_all_feature_requests(project_id, client_id, client_org_id, status, current_user, db))


def _fr_out(fr) -> dict:
    return _svc.fr_out(fr)


@router.post("/feature-requests", summary="Nueva solicitud de funcionalidad (cliente)")
def create_feature_request(
    payload: FeatureRequestIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.create_feature_request(payload, current_client, db))
    except ValueError as e:
        status_code = 403 if "permisos" in str(e) or "acceso" in str(e) else 400
        raise HTTPException(status_code, str(e))


@router.patch("/feature-requests/{fr_id}", summary="Editar solicitud de funcionalidad propia")
def update_feature_request(
    fr_id: str,
    payload: FeatureRequestUpdateIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.update_feature_request(fr_id, payload, current_client, db))
    except ValueError as e:
        status_code = 403 if "acceso" in str(e) else (404 if "encontrada" in str(e) else 400)
        raise HTTPException(status_code, str(e))


@router.post("/feature-requests/{fr_id}/withdraw", summary="Retirar solicitud de funcionalidad propia")
def withdraw_feature_request(
    fr_id: str,
    payload: FeatureRequestWithdrawIn = Body(default=FeatureRequestWithdrawIn()),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.withdraw_feature_request(fr_id, payload.reason, current_client, db))
    except ValueError as e:
        status_code = 404 if "encontrada" in str(e) else 400
        raise HTTPException(status_code, str(e))


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
    try:
        return APIResponse.ok(data=_svc.respond_to_fr(fr_id, payload, current_user, db))
    except ValueError as e:
        status_code = 422 if "pm_response" in str(e) else 404
        raise HTTPException(status_code, str(e))


@router.post("/feature-requests/{fr_id}/decide", summary="Cliente aprueba o rechaza FR")
def client_decide_fr(
    fr_id: str,
    payload: ClientApprovalIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.client_decide_fr(fr_id, payload, current_client, db))
    except ValueError as e:
        status_code = 404 if "encontrada" in str(e) else 400
        raise HTTPException(status_code, str(e))


# ── UAT ───────────────────────────────────────────────────────────────────────

def _uat_out(s) -> dict:
    return _svc.uat_out(s)


@router.get("/uat", summary="Mis UATs (cliente)")
def list_uat_client(
    status: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.list_uat_client(status, current_client, db))


@router.get("/uat/team", summary="Todas las UATs (equipo interno)")
def list_uat_team(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.list_uat_team(project_id, db))


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
    return APIResponse.ok(data=_svc.create_uat_for_project(project_id, payload, db))


@router.post("/uat/{uat_id}/test-cases", summary="Añadir caso de prueba")
def add_test_case(
    uat_id: str,
    payload: UATTestCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.add_test_case(uat_id, payload, db))


@router.post("/uat/{uat_id}/submit-result", summary="Cliente envía resultado del UAT")
def submit_uat_result(
    uat_id: str,
    payload: UATResultIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.submit_uat_result(uat_id, payload, current_client, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/uat/{uat_id}/issues", summary="Reportar incidencia en UAT")
def report_uat_issue(
    uat_id: str,
    payload: UATIssueIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.report_uat_issue(uat_id, payload, current_client, db))
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.patch("/uat/issues/{issue_id}", summary="Actualizar estado de incidencia (equipo)")
def update_issue(
    issue_id: str,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_uat_issue(issue_id, status, current_user, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Messaging ─────────────────────────────────────────────────────────────────

def _msg_out(m) -> dict:
    return _svc.msg_out(m)


@router.get("/messages", summary="Mensajes del proyecto (cliente)")
def get_client_messages(
    thread_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.get_client_messages(thread_id, current_client, db))


@router.get("/messages/team", summary="Mensajes del proyecto (equipo interno)")
def get_team_messages(
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_team_messages(project_id, db))


@router.post("/messages", summary="Enviar mensaje (cliente)")
def send_client_message(
    payload: MessageIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.send_client_message(payload, current_client, db))
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.post("/messages/team", summary="Enviar mensaje del equipo al cliente")
def send_team_message(
    payload: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.send_team_message(payload, current_user, db))


# ── Project info (client-safe view) ──────────────────────────────────────────

@router.get("/project", summary="Info del proyecto (cliente)")
def get_project_info(
    project_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.get_project_info(project_id, current_client, db))
    except ValueError as e:
        status_code = 403 if "acceso" in str(e) or "asignados" in str(e) else 404
        raise HTTPException(status_code, str(e))


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/documents", summary="Documentos compartidos (cliente)")
def get_client_documents(
    project_id: Optional[str] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIListResponse.ok(items=_svc.get_client_documents(project_id, current_client, db))
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.get("/documents/team", summary="Todos los documentos (equipo)")
def get_all_documents(
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_all_documents(project_id, db))


def _doc_out(d) -> dict:
    return _svc.doc_out(d)


@router.post("/documents", summary="Subir documento al portal")
def upload_document(
    payload: DocumentIn,
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.upload_document(payload, project_id, current_user, db))


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
    ip = ""
    if request:
        try:
            ip = request.client.host or ""
        except Exception as e:
            logging.getLogger(__name__).warning(f"No se pudo obtener IP del cliente: {e}")
    try:
        return APIResponse.ok(data=_svc.sign_document(
            doc_id,
            current_client.full_name,
            current_client.email,
            payload.job_title or getattr(current_client, "job_title", None),
            ip,
            settings.PDF_STORAGE_PATH,
            current_client,
            db,
        ))
    except ValueError as e:
        msg = str(e)
        if "ya fue firmado" in msg:
            raise HTTPException(400, msg)
        elif "acceso" in msg or "asignados" in msg:
            raise HTTPException(403, msg)
        raise HTTPException(404, msg)


@router.get("/documents/{doc_id}/signed-pdf", summary="Descargar PDF certificado de firma")
def download_signed_pdf(
    doc_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response
    try:
        pdf_bytes, title = _svc.download_signed_pdf(doc_id, current_client, db)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(403 if "acceso" in msg or "asignados" in msg else 404, msg)
    safe_title = title.replace(" ", "_")[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Firmado_{safe_title}.pdf"'}
    )


# ── Wiki (portal cliente — solo páginas con visibility=portal) ──────────────
@router.get("/wiki/pages", summary="Páginas wiki visibles al cliente")
def portal_wiki_pages(db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    return APIListResponse.ok(items=_svc.portal_wiki_pages(current_client, db))

@router.get("/wiki/pages/{page_id}", summary="Contenido de página wiki (portal)")
def portal_wiki_page_detail(page_id: str, db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    try:
        return APIResponse.ok(data=_svc.portal_wiki_page_detail(page_id, current_client, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Surveys ───────────────────────────────────────────────────────────────────

@router.get("/surveys", summary="Encuestas pendientes (cliente)")
def get_surveys(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.get_surveys(current_client, db))


def _survey_out(s) -> dict:
    return _svc.survey_out(s)


@router.post("/surveys", summary="Crear encuesta de satisfacción (equipo)")
def create_survey(
    project_id: str = Query(...),
    client_id: str = Query(...),
    title: str = Query(default="Encuesta de satisfacción"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_survey(project_id, client_id, title, db))


@router.post("/surveys/{survey_id}/respond", summary="Responder encuesta (cliente)")
def respond_survey(
    survey_id: str,
    payload: SurveyResponseIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse.ok(data=_svc.respond_survey(survey_id, payload, current_client, db))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(400 if "respondida" in msg else 404, msg)


# ── Stats for PM ──────────────────────────────────────────────────────────────

@router.get("/stats/{project_id}", summary="Estadísticas del portal para un proyecto (equipo)")
def get_portal_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_portal_stats(project_id, db))

# ── Traducciones personalizadas del portal ───────────────────────────────────

# Custom portal translations, persistidas por organización en
# OrgBranding.portal_translations (JSON). Antes vivían en un dict en memoria
# per-proceso: se perdían al reiniciar y no se compartían entre workers.
# Shape: { <lang>: { <module>: { <key>: <value> } } }.
#
# Auditoría 2026-08 (hallazgo 22): las dos consultas y el manejo del JSON
# estaban aquí; viven en `services/branding_service.py`, junto al resto de
# `OrgBranding`. El filtro por organización ya estaba bien puesto, así que esto
# es un movimiento y no un arreglo.
from app.services.branding_service import (  # noqa: E402
    guardar_traducciones_del_portal,
    traducciones_del_portal,
)


def _org_key(current_user: User) -> str:
    """Resolve the tenant bucket key for the current manager."""
    return str(getattr(current_user, "organization_id", None) or "_global")


@router.get("/translations", summary="Obtener traducciones personalizadas del portal")
def get_portal_translations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=traducciones_del_portal(
        db, _org_key(current_user)))


@router.post("/translations", summary="Guardar traducciones personalizadas del portal")
def save_portal_translations(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    guardar_traducciones_del_portal(
        db, current_user, _org_key(current_user), data)
    db.commit()
    return APIResponse.ok(data={"ok": True})


# ── AI Chat (I26) — cookie-auth para el widget flotante del portal ───────────

class _PortalAIChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None


@router.post("/ai-chat", summary="Chat IA del portal (auth por cookie)")
def portal_ai_chat(
    payload: _PortalAIChatIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Variante cookie-auth de ``/ai-modules/portal-ai/chat``.

    El portal cliente se autentica por cookie httponly (``portal_access_token``)
    que no es legible desde JavaScript, así que no podemos pasar el JWT como
    ``client_token`` en el body. Este endpoint usa ``get_current_client`` como
    dependencia y delega la lógica al servicio compartido.
    """
    import app.services.ai_modules_service as _ai_svc
    try:
        return APIResponse.ok(data=_ai_svc.client_portal_chat_authenticated(
            db, current_client, payload.message, payload.session_id
        ))
    except ValueError as e:
        err = str(e)
        if "missing_fields" in err:
            raise HTTPException(400, "message required")
        if "invalid_token" in err:
            raise HTTPException(401, "Token inválido")
        raise HTTPException(400, err)


@router.get("/ai-chat/{session_id}/messages", summary="Histórico de la sesión IA del portal")
def portal_ai_chat_history(
    session_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    import app.services.ai_modules_service as _ai_svc
    return APIListResponse.ok(items=_ai_svc.list_client_chat_messages(db, current_client, session_id))
