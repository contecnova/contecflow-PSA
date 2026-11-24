"""Grabación con consentimiento de las llamadas con clientes del portal (24-11-2026, migración 214).

Docs: docs/portal/CHAT_DEL_PORTAL.md §11. Servicio:
`app/services/portal_conversation_service/grabacion.py`. `{canal}` es
`colaboracion` (pestaña «Chat»), `conversacion` (conversaciones formales) o
`en_vivo` (chat en vivo de Soporte).

Operador (`clientes.llamar`; la descarga de la transcripción y la evidencia,
`clientes.gestionar`), siempre de la empresa de la llamada y participando en
su conversación:

- `GET  /portal-call-recording/{canal}/{call_id}`            estado
- `POST /portal-call-recording/{canal}/{call_id}/propose`    proponer grabar
- `POST /portal-call-recording/{canal}/{call_id}/stop`       parar / retirar la propuesta
- `GET  /portal-call-recording/{canal}/{call_id}/evidence`   consentimientos (evidencia)
- `GET  /portal-call-recording/{canal}/{call_id}/transcript` transcripción (.txt)

Cliente del portal (solo si es cliente de esa llamada y de esa empresa):

- `GET  /portal-call-recording/portal/{canal}/{call_id}`          estado
- `POST /portal-call-recording/portal/{canal}/{call_id}/consent`  `{accept, lang}`
- `POST /portal-call-recording/portal/{canal}/{call_id}/withdraw` retirar
"""
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_client, requiere_capacidad
from app.core.network import ip_del_cliente
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.models.user import User
from app.services.portal_conversation_service import grabacion as svc

router = APIRouter(prefix="/portal-call-recording", tags=["Portal - Grabación de llamadas"])


class PropuestaIn(BaseModel):
    transcribe: bool = False


class RespuestaIn(BaseModel):
    accept: bool
    lang: Optional[str] = Field(None, max_length=10)


def _del_operador(db: Session, usuario, canal: str, call_id: str):
    llamada = svc.cargar(db, canal, call_id, usuario.organization_id)
    svc.exigir_acceso_del_operador(db, usuario, llamada)
    return llamada


def _del_cliente(db: Session, cliente, canal: str, call_id: str):
    llamada = svc.cargar(db, canal, call_id, cliente.organization_id)
    svc.exigir_acceso_del_cliente(cliente, llamada)
    return llamada


# ── Cliente del portal (antes que las rutas con {canal}: «portal» no es un canal) ──

@router.get("/portal/{canal}/{call_id}", summary="Estado de la grabación (cliente)")
def client_state(canal: str, call_id: str, db: Session = Depends(get_db),
                 current_client: ClientUser = Depends(get_current_client)):
    llamada = _del_cliente(db, current_client, canal, call_id)
    return APIResponse.ok(data=svc.estado(db, llamada, cliente=current_client))


@router.post("/portal/{canal}/{call_id}/consent", summary="Dar o negar el consentimiento a grabar (cliente)")
def client_consent(canal: str, call_id: str, payload: RespuestaIn, request: Request, db: Session = Depends(get_db),
                   current_client: ClientUser = Depends(get_current_client)):
    llamada = _del_cliente(db, current_client, canal, call_id)
    return APIResponse.ok(data=svc.responder(db, current_client, llamada, payload.accept,
                                             ip=ip_del_cliente(request), ua=request.headers.get("user-agent"),
                                             idioma=payload.lang))


@router.post("/portal/{canal}/{call_id}/withdraw", summary="Retirar el consentimiento (cliente): se para la grabación")
def client_withdraw(canal: str, call_id: str, request: Request, db: Session = Depends(get_db),
                    current_client: ClientUser = Depends(get_current_client)):
    llamada = _del_cliente(db, current_client, canal, call_id)
    return APIResponse.ok(data=svc.retirar(db, current_client, llamada, ip=ip_del_cliente(request),
                                           ua=request.headers.get("user-agent")))


# ── Operador ─────────────────────────────────────────────────────────────────

@router.get("/{canal}/{call_id}", summary="Estado de la grabación (operador)")
def team_state(canal: str, call_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("clientes.llamar"))):
    return APIResponse.ok(data=svc.estado(db, _del_operador(db, current_user, canal, call_id)))


@router.post("/{canal}/{call_id}/propose", summary="Proponer grabar la llamada (solo el operador)")
def team_propose(canal: str, call_id: str, payload: Optional[PropuestaIn] = None, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("clientes.llamar"))):
    llamada = _del_operador(db, current_user, canal, call_id)
    return APIResponse.ok(data=svc.proponer(db, current_user, llamada, bool(payload and payload.transcribe)))


@router.post("/{canal}/{call_id}/stop", summary="Parar la grabación o retirar la propuesta (operador)")
def team_stop(canal: str, call_id: str, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("clientes.llamar"))):
    return APIResponse.ok(data=svc.detener(db, current_user, _del_operador(db, current_user, canal, call_id)))


@router.get("/{canal}/{call_id}/evidence", summary="Consentimientos de la llamada (evidencia)")
def team_evidence(canal: str, call_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("clientes.gestionar"))):
    return APIListResponse.ok(items=svc.evidencia(db, current_user, _del_operador(db, current_user, canal, call_id)))


@router.get("/{canal}/{call_id}/transcript", summary="Descargar la transcripción de la llamada grabada")
def team_transcript(canal: str, call_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("clientes.gestionar"))):
    datos, nombre = svc.descargar_transcripcion(db, current_user, _del_operador(db, current_user, canal, call_id))
    return Response(content=datos, media_type="text/plain; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
