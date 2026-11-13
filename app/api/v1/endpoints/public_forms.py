"""
Public intake forms — anonymous form submissions that auto-create tickets.
Endpoints:
  Authenticated (admin/pm):
    GET    /forms                  — list own forms
    POST   /forms                  — create form
    GET    /forms/{id}             — get form detail
    PATCH  /forms/{id}             — update form
    DELETE /forms/{id}             — delete form
    GET    /forms/{id}/submissions — list submissions for a form

  Public (no auth required):
    GET    /forms/public/{token}   — get form metadata for rendering
    POST   /forms/public/{token}/submit — submit form (creates ticket)
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.core.ratelimit import limiter
from app.models.user import User, UserRole
from app.services import public_forms_service
from app.services.widget_de_formulario import TEXTOS
from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.services.public_forms_service import serialize_form as _form_out
from app.core.responses import APIListResponse, APIResponse

router = APIRouter(prefix="/forms", tags=["Public Forms"])
log = logging.getLogger(__name__)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class FormCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    form_type: str = "ticket"          # ticket | task
    is_active: bool = True
    target_project_id: Optional[str] = None
    target_group_id: Optional[str] = None
    default_priority: str = "medium"
    default_category: Optional[str] = None
    success_message: Optional[str] = None
    notify_emails: list[str] = []


class FormUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    target_project_id: Optional[str] = None
    target_group_id: Optional[str] = None
    default_priority: Optional[str] = None
    default_category: Optional[str] = None
    success_message: Optional[str] = None
    notify_emails: Optional[list[str]] = None


class SubmitFormIn(BaseModel):
    submitter_name: Optional[str] = None
    submitter_email: Optional[EmailStr] = None
    subject: str
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    extra_fields: dict = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

# _form_out delegated to public_forms_service.serialize_form (see imports above)


# ── Authenticated endpoints ────────────────────────────────────────────────────

@router.get("", summary="Listar formularios públicos")
def list_forms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    forms = public_forms_service.list_forms(db, current_user.id)
    items = [_form_out(f) for f in forms]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("", summary="Crear formulario público", status_code=201)
def create_form(
    payload: FormCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: un formulario publico abre una puerta sin autenticar, pero la audiencia prevista es PM segun test_public_forms
):
    try:
        public_forms_service.validar_destino(payload.form_type, payload.target_project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    form = public_forms_service.create_form(
        db,
        name=payload.name,
        description=payload.description,
        form_type=payload.form_type,
        is_active=payload.is_active,
        target_project_id=payload.target_project_id,
        target_group_id=payload.target_group_id,
        default_priority=payload.default_priority,
        default_category=payload.default_category,
        success_message=payload.success_message,
        notify_emails=payload.notify_emails,
        created_by=current_user.id,
    )
    return APIResponse.ok(data=_form_out(form))


@router.get("/{form_id}", summary="Detalle de formulario")
def get_form(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = public_forms_service.get_form_by_id(db, form_id)
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    return APIResponse.ok(data=_form_out(form))


@router.patch("/{form_id}", summary="Actualizar formulario")
def update_form(
    form_id: str,
    payload: FormUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: idem que crear el formulario
):
    form = public_forms_service.get_form_by_id(db, form_id)
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    cambios = payload.model_dump(exclude_none=True)
    try:
        public_forms_service.validar_destino(form.form_type, cambios.get("target_project_id", form.target_project_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    form = public_forms_service.update_form(db, form, cambios)
    return APIResponse.ok(data=_form_out(form))


@router.delete("/{form_id}", summary="Eliminar formulario")
def delete_form(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: excepcion revisada: idem que crear el formulario
):
    form = public_forms_service.get_form_by_id(db, form_id)
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    enforce_abac(db, current_user, "public_form", form_id, action="delete")
    public_forms_service.delete_form(db, form)
    return APIResponse.ok(data={"ok": True, "message": "Formulario eliminado correctamente"})


@router.get("/{form_id}/submissions", summary="Envíos de un formulario")
def list_submissions(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = public_forms_service.get_form_by_id(db, form_id)
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    subs = public_forms_service.list_submissions(db, form_id)
    items = [
        {
            "id": s.id,
            "submitter_name": s.submitter_name,
            "submitter_email": s.submitter_email,
            "subject": s.subject,
            "description": s.description,
            "priority": s.priority,
            "category": s.category,
            "created_entity_id": s.created_entity_id,
            "created_entity_type": s.created_entity_type,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        }
        for s in subs
    ]
    return APIListResponse.ok(items=items, total=len(items))


# ── Public (unauthenticated) endpoints ────────────────────────────────────────

def _abierto(response: Response) -> None:
    """Público y sin credenciales: lo usa el widget desde la web del cliente (revisión 2026-11)."""
    response.headers["Access-Control-Allow-Origin"] = "*"


def _idioma(db: Session, form) -> str:
    from app.services.service_desk.pagina_de_estado_publica import idioma_de
    idioma = idioma_de(db, getattr(form, "organization_id", None))
    return idioma if idioma in TEXTOS else IDIOMA_DE_RESPALDO




@router.get("/public/{token}", summary="Obtener metadatos de formulario público")
def get_public_form(token: str, response: Response, db: Session = Depends(get_db)):
    _abierto(response)
    form = public_forms_service.get_active_form_by_token(db, token)
    if not form:
        raise HTTPException(404, "Formulario no encontrado o inactivo")
    idioma = _idioma(db, form)
    return {
        "idioma": idioma,
        "id": form.id,
        "name": form.name,
        "description": form.description,
        "form_type": form.form_type,
        "default_priority": form.default_priority,
        "default_category": form.default_category,
        "success_message": form.success_message or TEXTOS[idioma]["gracias"],
    }


@router.post("/public/{token}/submit", summary="Enviar formulario público", status_code=201)
@limiter.limit("10/minute")
def submit_public_form(
    token: str,
    payload: SubmitFormIn,
    request: Request,
    response: Response,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _abierto(response)
    form = public_forms_service.get_active_form_by_token(db, token)
    if not form:
        raise HTTPException(404, "Formulario no encontrado o inactivo")

    priority = payload.priority or form.default_priority
    category = payload.category or form.default_category
    # La IP real tras un proxy de confianza, no la del proxy (revisión 2026-11).
    from app.core.network import extract_client_ip
    ip = extract_client_ip(request)

    sub, created_entity_id = public_forms_service.submit_form(
        db,
        form=form,
        submitter_name=payload.submitter_name,
        submitter_email=payload.submitter_email,
        subject=payload.subject,
        description=payload.description,
        priority=priority,
        category=category,
        extra_fields=payload.extra_fields,
        ip_address=ip,
    )

    destinatarios = json.loads(form.notify_emails or "[]") if isinstance(form.notify_emails, str) else (form.notify_emails or [])
    if destinatarios:
        tareas.add_task(public_forms_service.avisar_por_correo, form.name, destinatarios, payload.subject,
                        payload.description, payload.submitter_email or payload.submitter_name, created_entity_id)
    return {
        "ok": True,
        "message": form.success_message or TEXTOS[_idioma(db, form)]["gracias"],
        "submission_id": sub.id,
        "ticket_id": created_entity_id,
    }



