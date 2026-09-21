"""Bots, slash commands, integrations, webhooks.

Auditoria 2026-08 (hallazgo 22). Los 11 puntos de acceso a base estan en
`app/services/collaboration/webhooks.py`, y el listado de `/slash/help` ya no
esta escrito a mano aqui: se deriva de la tabla de comandos del servicio de
bots, que es donde estan sus ejecutores. Antes eran dos fuentes que coincidian
por costumbre y nada garantizaba que siguieran coincidiendo.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.schemas.collaboration import (
    BotMessageIn, BotOut,
    IntegrationCreate, IntegrationOut,
    SlashCommandIn, SlashCommandOut,
    WebhookCreate, WebhookOut,
)
from app.services.collaboration import bots as bot_svc
from app.services.collaboration import webhooks as svc
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.key_management import get_integration_rotation_status

router = APIRouter()

#: A qué slash command se traduce cada bot cuando se le habla directamente en
#: vez de por comando. Un handle desconocido cae a `ask`, que es el bot
#: generalista: preguntar es la acción por defecto razonable.
COMANDO_POR_BOT = {
    "nexus": "ask",
    "watcher": "risk",
    "compliance": "decision",
    "pulse": "standup",
    "bridge": "findfile",
}
COMANDO_POR_DEFECTO = "ask"


def _integration_out(r) -> IntegrationOut:
    return IntegrationOut(
        id=r.id, kind=r.kind, name=r.name, is_enabled=r.is_enabled,
        config=r.config or {}, created_at=r.created_at,
    )


def _webhook_out(w) -> WebhookOut:
    return WebhookOut(
        id=w.id, direction=w.direction, name=w.name, url=w.url,
        secret_token=w.secret_token, target_channel_id=w.target_channel_id,
        events=w.events or [], is_active=w.is_active,
        last_called_at=w.last_called_at, failure_count=w.failure_count,
    )


# ── Bots ─────────────────────────────────────────────────────────────────────
@router.get("/bots", response_model=APIListResponse[BotOut], summary="Listar bots disponibles")
def list_bots(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        BotOut(
            id=b.id, kind=b.kind, handle=b.handle, display_name=b.display_name,
            description=b.description, avatar_url=b.avatar_url,
            is_enabled=b.is_enabled,
        )
        for b in svc.list_bots(db, current_user)
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/bots/invoke", summary="Invocar bot directamente (no slash)")
def invoke_bot(payload: BotMessageIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, payload.conversation_id)
    comando = COMANDO_POR_BOT.get(payload.bot_handle.lower(), COMANDO_POR_DEFECTO)
    return APIResponse.ok(data=bot_svc.handle_slash(
        db, current_user, conversation_id=payload.conversation_id,
        command=comando, args=payload.args,
    ))


# ── Slash commands ───────────────────────────────────────────────────────────
@router.post("/slash", response_model=APIResponse[SlashCommandOut], summary="Ejecutar slash command")
def slash(payload: SlashCommandIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, payload.conversation_id)
    res = bot_svc.handle_slash(
        db, current_user,
        conversation_id=payload.conversation_id,
        command=payload.command,
        args=payload.args,
    )
    return APIResponse.ok(data=SlashCommandOut(**res))


@router.get("/slash/help", summary="Listado de slash commands")
def slash_help():
    """Se deriva de la tabla de comandos del servicio: un comando implementado y
    no anunciado, o al contrario, ya no es posible."""
    comandos = bot_svc.slash_help()
    return APIListResponse.ok(items=comandos, total=len(comandos))


# ── Integrations ─────────────────────────────────────────────────────────────
@router.get("/integrations", response_model=APIListResponse[IntegrationOut], summary="Listar integraciones")
def list_integrations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [_integration_out(r) for r in svc.list_integrations(db, current_user)]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/integrations", response_model=APIResponse[IntegrationOut], summary="Crear integración")
def create_integration(payload: IntegrationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    row = svc.create_integration(
        db, current_user,
        kind=payload.kind, name=payload.name, config=payload.config,
    )
    return APIResponse.ok(data=_integration_out(row))


@router.delete("/integrations/{integration_id}", summary="Eliminar integración")
def delete_integration(integration_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    enforce_abac(db, current_user, "collaboration_integration", integration_id, action="delete")
    svc.delete_integration(db, current_user, integration_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/integrations/security/rotation-status", summary="Estado de rotación de secretos de integración",
            dependencies=[Depends(get_current_user)])
def integration_rotation_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # `_org` es la guarda de organización: lanza 403 a un usuario sin tenant.
    _org(current_user)
    return APIResponse.ok(data=get_integration_rotation_status(db))


# ── Webhooks ────────────────────────────────────────────────────────────────
@router.get("/webhooks", response_model=APIListResponse[WebhookOut], summary="Listar webhooks")
def list_webhooks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [_webhook_out(w) for w in svc.list_webhooks(db, current_user)]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/webhooks", response_model=APIResponse[WebhookOut], summary="Crear webhook")
def create_webhook(payload: WebhookCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: configuracion: la forma de la ruta manda sobre el fichero
):
    row = svc.create_webhook(
        db, current_user,
        direction=payload.direction, name=payload.name, url=payload.url,
        target_channel_id=payload.target_channel_id, events=payload.events,
    )
    return APIResponse.ok(data=_webhook_out(row))


@router.post("/webhooks/incoming/{token}", summary="Hook entrante (push externo a canal)")
async def incoming_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    """External services post here to deliver a message into a channel.

    Auditoria #C7: el cuerpo es `async` porque hace falta para `await
    request.json()`, pero toda la parte de base va al pool de hilos con
    `run_db` — ninguna operacion de base puede correr en el bucle de eventos.
    """
    from app.core.async_db import run_db

    payload = await request.json()
    await run_db(svc.deliver_incoming, db, token, payload or {})
    return APIResponse.ok(data={"ok": True})
