"""Bots, slash commands, integrations, webhooks."""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationBotApp, CollaborationIntegration, CollaborationWebhook,
)
from app.schemas.collaboration import (
    BotMessageIn, BotOut,
    IntegrationCreate, IntegrationOut,
    SlashCommandIn, SlashCommandOut,
    WebhookCreate, WebhookOut,
)
from app.services.collaboration import bots as bot_svc
from app.services.collaboration._permissions import (
    _org, assert_conversation_access,
)

router = APIRouter()


# ── Bots ─────────────────────────────────────────────────────────────────────
@router.get("/bots", response_model=List[BotOut], summary="Listar bots disponibles")
def list_bots(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationBotApp).filter(CollaborationBotApp.organization_id == _org(current_user)).all()
    return [BotOut(id=b.id, kind=b.kind, handle=b.handle, display_name=b.display_name,
                   description=b.description, avatar_url=b.avatar_url, is_enabled=b.is_enabled) for b in rows]


@router.post("/bots/invoke", summary="Invocar bot directamente (no slash)")
def invoke_bot(payload: BotMessageIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, payload.conversation_id)
    # Map handles to slash command for unified pipeline
    handle = payload.bot_handle.lower()
    cmd_map = {"nexus": "ask", "watcher": "risk", "compliance": "decision", "pulse": "standup", "bridge": "findfile"}
    command = cmd_map.get(handle, "ask")
    return bot_svc.handle_slash(db, current_user, conversation_id=payload.conversation_id, command=command, args=payload.args)


# ── Slash commands ───────────────────────────────────────────────────────────
@router.post("/slash", response_model=SlashCommandOut, summary="Ejecutar slash command")
def slash(payload: SlashCommandIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, payload.conversation_id)
    res = bot_svc.handle_slash(
        db, current_user,
        conversation_id=payload.conversation_id,
        command=payload.command,
        args=payload.args,
    )
    return SlashCommandOut(**res)


@router.get("/slash/help", summary="Listado de slash commands")
def slash_help():
    return {
        "commands": [
            {"name": "/ask", "desc": "Pregunta a Nexus IA. Si no resuelve, abre ticket auto-asignado."},
            {"name": "/task", "desc": "Crea tarea PSA en el proyecto del canal."},
            {"name": "/ticket", "desc": "Abre ticket de soporte (auto-asignado)."},
            {"name": "/imputar", "desc": "Imputa horas al proyecto del canal. Ej: /imputar 30m"},
            {"name": "/risk", "desc": "Registra un riesgo en el proyecto."},
            {"name": "/decision", "desc": "Registra decisión gobernada con auditoría."},
            {"name": "/poll", "desc": "/poll Pregunta? | A | B | C"},
            {"name": "/standup", "desc": "Lanza standup async."},
            {"name": "/findfile", "desc": "Busca documentos del proyecto."},
            {"name": "/onboard", "desc": "Mensaje de bienvenida con pasos."},
            {"name": "/meet", "desc": "Inicia llamada inmediata en este canal."},
            {"name": "/recap", "desc": "Resumen IA de los últimos mensajes."},
            {"name": "/escalate", "desc": "Escala a soporte con prioridad alta."},
        ]
    }


# ── Integrations ─────────────────────────────────────────────────────────────
@router.get("/integrations", response_model=List[IntegrationOut], summary="Listar integraciones")
def list_integrations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationIntegration).filter(CollaborationIntegration.organization_id == _org(current_user)).all()
    return [IntegrationOut(id=r.id, kind=r.kind, name=r.name, is_enabled=r.is_enabled, config=r.config or {}, created_at=r.created_at) for r in rows]


@router.post("/integrations", response_model=IntegrationOut, summary="Crear integración")
def create_integration(payload: IntegrationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    from app.services.collaboration.workspaces import get_or_create_workspace
    ws = get_or_create_workspace(db, current_user)
    row = CollaborationIntegration(
        organization_id=org, workspace_id=ws.id,
        kind=payload.kind, name=payload.name, config=payload.config or {}, created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    return IntegrationOut(id=row.id, kind=row.kind, name=row.name, is_enabled=row.is_enabled, config=row.config or {}, created_at=row.created_at)


@router.delete("/integrations/{integration_id}", summary="Eliminar integración")
def delete_integration(integration_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(CollaborationIntegration).filter(
        CollaborationIntegration.id == integration_id, CollaborationIntegration.organization_id == _org(current_user)
    ).first()
    if not row:
        raise HTTPException(404, "Integración no encontrada")
    db.delete(row); db.commit()
    return {"ok": True}


# ── Webhooks ────────────────────────────────────────────────────────────────
@router.get("/webhooks", response_model=List[WebhookOut], summary="Listar webhooks")
def list_webhooks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationWebhook).filter(CollaborationWebhook.organization_id == _org(current_user)).all()
    return [WebhookOut(
        id=w.id, direction=w.direction, name=w.name, url=w.url, secret_token=w.secret_token,
        target_channel_id=w.target_channel_id, events=w.events or [], is_active=w.is_active,
        last_called_at=w.last_called_at, failure_count=w.failure_count,
    ) for w in rows]


@router.post("/webhooks", response_model=WebhookOut, summary="Crear webhook")
def create_webhook(payload: WebhookCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.workspaces import get_or_create_workspace
    import secrets
    ws = get_or_create_workspace(db, current_user)
    row = CollaborationWebhook(
        organization_id=_org(current_user), workspace_id=ws.id,
        direction=payload.direction, name=payload.name, url=payload.url,
        secret_token=secrets.token_urlsafe(32),
        target_channel_id=payload.target_channel_id,
        events=payload.events or [],
    )
    db.add(row); db.commit()
    return WebhookOut(
        id=row.id, direction=row.direction, name=row.name, url=row.url, secret_token=row.secret_token,
        target_channel_id=row.target_channel_id, events=row.events or [], is_active=row.is_active,
        last_called_at=row.last_called_at, failure_count=row.failure_count,
    )


@router.post("/webhooks/incoming/{token}", summary="Hook entrante (push externo a canal)")
async def incoming_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    """External services post here to deliver a message into a channel."""
    from app.services.collaboration.messages import send_message
    from app.models.user import User as U
    row = db.query(CollaborationWebhook).filter(CollaborationWebhook.secret_token == token, CollaborationWebhook.is_active == True).first()
    if not row or row.direction != "incoming" or not row.target_channel_id:
        raise HTTPException(404, "Webhook inválido")
    payload = await request.json()
    text = (payload or {}).get("text") or "(sin contenido)"
    # Find a system bot author (Bridge)
    from app.models.collaboration import CollaborationBotApp, CollaborationChannel
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == row.target_channel_id).first()
    if not ch:
        raise HTTPException(404, "Canal del webhook no encontrado")
    bot = db.query(CollaborationBotApp).filter(
        CollaborationBotApp.organization_id == row.organization_id,
        CollaborationBotApp.handle == "bridge",
    ).first()
    # Use a dummy user with org for permissions; we cheat and skip access check by using the bot path.
    fake = U(id="webhook", organization_id=row.organization_id)
    send_message(
        db, fake, body=text, channel_id=ch.id, type="bot",
        metadata_json={"card": "webhook", "source": row.name, "raw": payload},
        bot_id=bot.id if bot else None,
    )
    row.last_called_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
