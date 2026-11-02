"""Service Desk — textos de los avisos (correo y campana) por organizacion."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import notification_template_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter()


class PlantillaIn(BaseModel):
    subject: str = Field(..., max_length=500)
    body_html: str = Field(..., max_length=20000)
    is_active: bool = True


class VistaPreviaIn(BaseModel):
    subject: str = Field(..., max_length=500)
    body_html: str = Field(..., max_length=20000)


@router.get("/notification-templates", summary="Avisos del Service Desk y sus textos")
def listar(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return APIListResponse.ok(items=svc.listar(db, user.organization_id))


@router.put("/notification-templates/{code}/{language}", summary="Personalizar o apagar un aviso")
def guardar(code: str, language: str, payload: PlantillaIn,
            db: Session = Depends(get_db), user: User = Depends(require_admin)):
    data = svc.guardar(db, user.organization_id, user.id, code, language,
                       payload.subject, payload.body_html, payload.is_active)
    _commit_or_rollback(db)
    return APIResponse.ok(data=data)


@router.delete("/notification-templates/{code}/{language}", summary="Volver al texto por defecto")
def restaurar(code: str, language: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    data = svc.restaurar(db, user.organization_id, code, language)
    _commit_or_rollback(db)
    return APIResponse.ok(data=data)


@router.post("/notification-templates/preview", summary="Vista previa con datos de ejemplo")
def vista_previa(payload: VistaPreviaIn, _: User = Depends(require_admin)):
    return APIResponse.ok(data=svc.vista_previa(payload.subject, payload.body_html))
