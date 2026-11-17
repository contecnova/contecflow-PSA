"""Asistente del portal que actua, con confirmacion (mejoras de mercado 16-11-2026).

Va con la sesion del cliente del portal. Ver
`app/services/service_desk/asistente_del_portal.py`.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_portal_client
from app.core.responses import APIResponse
from app.db.session import get_db
from app.services.service_desk import asistente_del_portal as asistente

router = APIRouter(prefix="/portal-assistant", tags=["Service Desk - Asistente del portal"])


class TurnoIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class MensajeIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    # 17-11-2026: idioma del portal en que se contesta y turnos anteriores (contexto de la IA).
    language: Optional[str] = Field(None, max_length=16)
    history: list[TurnoIn] = Field(default_factory=list, max_length=12)


@router.post("/intent", summary="Portal: qué quiere el cliente (contesta o propone una acción)")
def intent(payload: MensajeIn, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=asistente.interpretar(db, client, payload.message, payload.language,
                                                     [t.model_dump() for t in payload.history]))


@router.post("/actions/{action_id}/confirm", summary="Portal: confirmar la acción propuesta")
def confirm(action_id: str, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=asistente.confirmar(db, client, action_id))


@router.post("/actions/{action_id}/cancel", summary="Portal: descartar la acción propuesta")
def cancel(action_id: str, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=asistente.cancelar(db, client, action_id))
