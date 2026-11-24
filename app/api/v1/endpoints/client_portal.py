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
import jwt
import logging
from app.core.codigos_de_error import error_http
from app.core.network import ip_del_cliente

logger = logging.getLogger("contecflow.client_portal")

from app.db.session import get_db, publicar_contexto_de_tenant, sesion_de_sistema
from app.core.config import settings
from app.core.deps import requiere_capacidad
from app.core.ratelimit import limiter
from app.core.codigos_de_error import desde_valor, error
from app.core.paginacion import Paginacion, lista_paginada, paginacion
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

def get_current_client(
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ClientUser:
    credentials_exception = error(401, "sesion_invalida")
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
    except jwt.PyJWTError:
        raise credentials_exception
    if _svc.token_de_cliente_revocado(payload):  # auditoria 2026-11 #23: cerro sesion
        raise credentials_exception
    # Incidencia 7 de usuarios (23-11-2026): «no se puede entrar en el portal».
    # Con `TENANT_SESION_SIN_CONTEXTO=cerrar` (por defecto desde el 23-11) esta
    # búsqueda por id corría en una sesión sin empresa ni contexto de sistema y
    # lanzaba `TenantIsolationError`: el login daba la cookie, pero `/portal/auth/me`
    # y las 41 rutas que cuelgan de aquí respondían 500. Se declara el contexto de
    # sistema solo para identificar al cliente, como `deps.get_current_client`.
    from app.db.contexto_de_tenant import contexto_de_sistema
    with contexto_de_sistema(db, "portal: identidad del cliente"):
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
    publicar_contexto_de_tenant(db, client, es_cliente=True)
    # 23-11-2026: con la contrasena generada por el sistema, solo el perfil, la
    # marca y la sesion hasta cambiarla (403 `portal_cambio_de_contrasena_obligatorio`).
    _svc.exigir_contrasena_cambiada(client, request.scope.get("path") if request is not None else None)
    return client


# ── Pydantic schemas ──────────────────────────────────────────────────────────


from pydantic import Field, EmailStr, field_validator
from app.schemas._enlaces import EnlaceSeguro  # auditoría 22-11-2026: solo http(s)

class ClientLoginIn(BaseModel):
    email: EmailStr = Field(..., max_length=120)
    password: str = Field(..., min_length=8, max_length=128)

# ClientCreateIn vive en app/schemas/client_portal.py (lo usa también client_service).
from app.schemas.client_portal import ClientCreateIn  # noqa: E402

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
    # 22-11-2026 (docs/FLUJO_DE_DEMANDA.md §1.2): sin `approved`. Ese estado es «lo aprobó
    # el cliente» y solo lo pone el cliente con /decide; el equipo no decide por él.
    status: str = Field("estimated", pattern="^(estimated|rejected|in_development|done)$")

class ClientApprovalIn(BaseModel):
    approved: bool
    reason: Optional[str] = Field(None, max_length=500)

class UATSessionIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    deliverable_id: Optional[str] = None
    test_environment: EnlaceSeguro = Field(None, max_length=200)
    test_credentials: Optional[str] = Field(None, max_length=200)
    test_guide_url: EnlaceSeguro = Field(None, max_length=200)
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
    file_url: EnlaceSeguro = Field(None, max_length=500)
    file_name: Optional[str] = Field(None, max_length=200)
    file_size_kb: Optional[int] = Field(None, ge=0, le=100000)
    requires_signature: bool = False


# ── Client Management (PM side) ───────────────────────────────────────────────

@router.get("/clients", summary="Listar clientes del portal")
def list_clients(
    response: Response,
    project_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    include_archived: bool = Query(False, description="Incluir los usuarios archivados («Ver archivados»)"),
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    """``page``/``page_size`` con el mecanismo comun (total en ``X-Total-Count`` y
    ``meta.total``). Sin ellos, la misma lista entera de antes (hasta LIST_MAX_ROWS).
    Los archivados (23-11-2026) solo con ``include_archived=true``."""
    return lista_paginada(response, _svc.list_clients(project_id, client_org_id, db, pagina,
                                                      incluir_archivados=include_archived))


@router.post("/clients", summary="Crear acceso de cliente al portal")
def create_client(
    payload: ClientCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.create_client(payload, db, actor=current_user))
    except ValueError as e:
        raise desde_valor(400, e)


@router.post("/clients/{client_id}/send-access", summary="Generar y enviar una contraseña nueva al cliente")
def send_client_access(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    """23-11-2026 (M10 del 04b): el equipo no fija ni ve la contraseña del cliente.
    Se genera, se envía a su correo y queda en auditoría (sin la contraseña)."""
    from app.services.client_portal_service.clientes import reenviar_acceso_y_auditar
    try:
        resultado = reenviar_acceso_y_auditar(client_id, db, current_user)
    except ValueError as e:
        raise desde_valor(404, e)
    return APIResponse.ok(data=resultado)


@router.patch("/clients/{client_id}", summary="Actualizar cliente")
def update_client(
    client_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.update_client(client_id, payload, db))
    except ValueError as e:
        raise desde_valor(404, e)


@router.delete("/clients/{client_id}", summary="Eliminar (sin historial) o archivar (con historial) un usuario del portal")
def delete_client(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    """23-11-2026 (portal_usuarios): decide el servidor. Sin historial se borra de
    verdad; con historial se archiva (no entra, sesiones cerradas, fuera de las
    listas por defecto, historial conservado con su nombre). La respuesta dice
    `resultado` (`eliminado`/`archivado`) y el `historial` por tabla. Auditado."""
    from app.services.client_portal_service.usuarios import eliminar_o_archivar
    from app.services.seguridad_de_cuentas.auditoria import Origen
    enforce_abac(db, current_user, "client_portal_client", client_id, action="delete")
    return APIResponse.ok(data=eliminar_o_archivar(db, current_user, client_id, origen=Origen.de(request)))


@router.post("/clients/{client_id}/restore", summary="Restaurar un usuario del portal archivado")
def restore_client(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    """Vuelve a poder entrar con su contraseña (respeta el tope de usuarios del cliente). Auditado."""
    from app.services.client_portal_service.usuarios import restaurar
    from app.services.seguridad_de_cuentas.auditoria import Origen
    return APIResponse.ok(data=restaurar(db, current_user, client_id, origen=Origen.de(request)))


# ── Client Auth ───────────────────────────────────────────────────────────────

@router.post("/auth/login", summary="Login cliente portal")
@limiter.limit("5/minute")
def client_login(request: Request, response: Response, payload: ClientLoginIn, db: Session = Depends(sesion_de_sistema("portal: login de cliente"))):
    try:
        result = _svc.client_login(payload.email, payload.password, db)
    except ValueError as e:
        raise desde_valor(401, e)
    token = result["token"]
    # Auditoría 22-11-2026 (M3): la misma política de cookie que la sesión del
    # personal (`COOKIE_OPTS`: Secure también en staging, no solo en producción)
    # y su testigo CSRF para el doble envío.
    from app.core.csrf import issue_csrf_cookie
    from app.services.auth_service.tokens_y_cookies import COOKIE_OPTS
    response.set_cookie("portal_access_token", token, max_age=CLIENT_TOKEN_EXPIRE_HOURS * 3600, **COOKIE_OPTS)
    issue_csrf_cookie(response)
    return APIResponse.ok(data={"ok": True, "client": result["client"]})


@router.post("/auth/logout", summary="Cerrar sesión del portal de cliente")
def client_logout(
    response: Response,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
):
    # Auditoria 2026-11 (#23): borrar la cookie no invalidaba el token (JWT de
    # 72 h): una copia seguia entrando. Ahora se revoca su `jti`.
    token = authorization.split(" ", 1)[1] if authorization and authorization.startswith("Bearer ") else None
    _svc.revocar_token_de_cliente(token or portal_access_token)
    from app.services.auth_service.tokens_y_cookies import COOKIE_OPTS
    response.delete_cookie("portal_access_token", path="/", **COOKIE_OPTS)
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
        raise desde_valor(status_code, e)


@router.post("/share-link/{project_id}", summary="Generar enlace público de estado de proyecto")
def create_public_share_link(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.create_public_share_link(project_id, db))
    except ValueError as e:
        raise desde_valor(404, e)


@router.get("/view/{token}", summary="Vista pública de estado de proyecto por token")
def view_public_project_status(
    token: str,
    db: Session = Depends(sesion_de_sistema("portal: enlace de estado firmado")),
):
    try:
        return APIResponse.ok(data=_svc.view_public_project_status(token, db))
    except ValueError as e:
        status_code = 401 if "Token" in str(e) else 404
        raise desde_valor(status_code, e)


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
        raise desde_valor(status_code, e)


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
        raise desde_valor(403, e)


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
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_svc.list_all_feature_requests(project_id, client_id, client_org_id, status, current_user, db))


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
        raise desde_valor(status_code, e)


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
        raise desde_valor(status_code, e)


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
        raise desde_valor(status_code, e)


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
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.respond_to_fr(fr_id, payload, current_user, db))
    except ValueError as e:
        status_code = 422 if "pm_response" in str(e) else 404
        raise desde_valor(status_code, e)


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
        raise desde_valor(status_code, e)


# ── UAT ───────────────────────────────────────────────────────────────────────

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
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_svc.list_uat_team(project_id, db))


@router.post("/uat", summary="Crear sesión UAT (equipo interno)")
def create_uat(
    payload: UATSessionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    raise error_http(400, "usar_post_uat")


@router.post("/uat/{project_id}", summary="Crear sesión UAT para un proyecto")
def create_uat_for_project(
    project_id: str,
    payload: UATSessionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_svc.create_uat_for_project(project_id, payload, db))


@router.post("/uat/{uat_id}/test-cases", summary="Añadir caso de prueba")
def add_test_case(
    uat_id: str,
    payload: UATTestCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
        raise desde_valor(404, e)


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
        raise desde_valor(403, e)


@router.patch("/uat/issues/{issue_id}", summary="Actualizar estado de incidencia (equipo)")
def update_issue(
    issue_id: str,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.update_uat_issue(issue_id, status, current_user, db))
    except ValueError as e:
        raise desde_valor(404, e)


# ── Messaging ─────────────────────────────────────────────────────────────────

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
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
        raise desde_valor(403, e)


@router.post("/messages/team", summary="Enviar mensaje del equipo al cliente")
def send_team_message(
    payload: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
        raise desde_valor(status_code, e)


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
        raise desde_valor(403, e)


@router.get("/documents/team", summary="Todos los documentos (equipo)")
def get_all_documents(
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_svc.get_all_documents(project_id, db))


@router.post("/documents", summary="Subir documento al portal")
def upload_document(
    payload: DocumentIn,
    project_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
    ip = (ip_del_cliente(request) or "") if request else ""  # 01 B9: IP real tras el proxy
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
            raise desde_valor(400, e)
        elif "acceso" in msg or "asignados" in msg:
            raise desde_valor(403, e)
        raise desde_valor(404, e)


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
        raise desde_valor(403 if "acceso" in msg or "asignados" in msg else 404, e)
    safe_title = title.replace(" ", "_")[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Firmado_{safe_title}.pdf"'}
    )


# ── Wiki (portal cliente — solo páginas con visibility=portal) ──────────────
# 16-11-2026: titulo y contenido en el idioma de la pantalla del portal (`lang`)
# o de la ficha del cliente, si la empresa traduce (`traduccion.contenido_del_portal`).
@router.get("/wiki/pages", summary="Páginas wiki visibles al cliente")
def portal_wiki_pages(lang: Optional[str] = Query(None, max_length=16),
                      db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    from app.services.traduccion import contenido_del_portal as _contenido
    items = _svc.portal_wiki_pages(current_client, db)
    _contenido.localizar(db, current_client.organization_id, items, ("title",),
                         _contenido.idioma_del_lector(current_client, lang))
    return APIListResponse.ok(items=items)

@router.get("/wiki/pages/{page_id}", summary="Contenido de página wiki (portal)")
def portal_wiki_page_detail(page_id: str, lang: Optional[str] = Query(None, max_length=16),
                            db: Session = Depends(get_db), current_client=Depends(get_current_client)):
    from app.services.traduccion import contenido_del_portal as _contenido
    try:
        pagina = _svc.portal_wiki_page_detail(page_id, current_client, db)
    except ValueError as e:
        raise desde_valor(404, e)
    idioma = _contenido.idioma_del_lector(current_client, lang)
    _contenido.localizar(db, current_client.organization_id, [pagina], ("title", "content"), idioma)
    # Contenido en bloques (lo normal en la wiki): cada bloque por separado, para
    # no mandar el JSON al proveedor; cada bloque traducido lleva su original.
    # Los bloques de codigo no se traducen.
    if isinstance(pagina.get("content"), list):
        _contenido.localizar(db, current_client.organization_id,
                             [b for b in pagina["content"] if isinstance(b, dict) and b.get("type") != "code"],
                             ("content",), idioma)
    return APIResponse.ok(data=pagina)


# ── Surveys ───────────────────────────────────────────────────────────────────

@router.get("/surveys", summary="Encuestas pendientes (cliente)")
def get_surveys(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(items=_svc.get_surveys(current_client, db))


@router.post("/surveys", summary="Crear encuesta de satisfacción (equipo)")
def create_survey(
    project_id: str = Query(...),
    client_id: str = Query(...),
    title: str = Query(default="Encuesta de satisfacción"),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
        raise desde_valor(400 if "respondida" in msg else 404, e)


# ── Stats for PM ──────────────────────────────────────────────────────────────

@router.get("/stats/{project_id}", summary="Estadísticas del portal para un proyecto (equipo)")
def get_portal_stats(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
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
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=traducciones_del_portal(
        db, _org_key(current_user)))


@router.post("/translations", summary="Guardar traducciones personalizadas del portal")
def save_portal_translations(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    guardar_traducciones_del_portal(
        db, current_user, _org_key(current_user), data)
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
        # 16-11-2026: con codigo (`err_srv.*` en el portal); `detail` como antes.
        from app.core.errores import ErrorDeDominio
        if "missing_fields" in err:
            raise ErrorDeDominio(400, "message required", code="mensaje_obligatorio", params={})
        if "invalid_token" in err:
            raise ErrorDeDominio(401, "Token inválido", code="sesion_invalida", params={})
        raise desde_valor(400, e)


class _ValoracionIn(BaseModel):
    helpful: bool
    comment: Optional[str] = None


@router.post("/ai-chat/messages/{message_id}/feedback", summary="Valorar una respuesta del chat del portal (👍/👎)")
def valorar_respuesta_del_portal(message_id: str, payload: _ValoracionIn,
                                 current_client: ClientUser = Depends(get_current_client),
                                 db: Session = Depends(get_db)):
    from app.services.valoracion_de_respuestas import valorar_del_portal
    try:
        return APIResponse.ok(data=valorar_del_portal(db, current_client, message_id, payload.helpful, payload.comment))
    except LookupError:
        raise error(404, "respuesta_no_encontrada")


@router.get("/ai-chat/{session_id}/messages", summary="Histórico de la sesión IA del portal")
def portal_ai_chat_history(
    session_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    import app.services.ai_modules_service as _ai_svc
    return APIListResponse.ok(items=_ai_svc.list_client_chat_messages(db, current_client, session_id))
