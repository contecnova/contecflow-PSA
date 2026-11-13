"""Integracion con Slack.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import require_any_manager, require_admin
from app.models.user import User
from app.core.responses import APIListResponse, APIResponse
import app.services.slack_service as _slack
from app.schemas.auth_payloads import (
    SlackTestIn, SlackNotifyIn,
)

router = APIRouter()


@router.get("/slack/config", summary="Configuración Slack/Teams")
def get_slack_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIListResponse.ok(items=_slack.get_slack_config(db))


class SlackConfigCreate(BaseModel):
    platform: str = "slack"
    workspace_name: Optional[str] = None
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    default_channel: str = "#contecflow-alerts"
    subscriptions: Optional[List[str]] = None


@router.post("/slack/config", summary="Crear/actualizar configuración Slack")
def create_slack_config(
    payload: SlackConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_slack.create_or_update_slack_config(
        payload.model_dump(), db, organization_id=getattr(current_user, "organization_id", None),
    ))


@router.post("/slack/test", summary="Enviar mensaje de prueba a Slack/Teams")
def test_slack(
    payload: SlackTestIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        config_id = payload.config_id
        message = payload.message or "🔔 Mensaje de prueba desde Contecflow v15"
        channel = payload.channel or "#contecflow-alerts"
        return APIResponse.ok(data=_slack.test_slack_config(config_id, message, channel, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/slack/notify", summary="Enviar notificación de evento Slack")
def slack_notify(
    payload: SlackNotifyIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_slack.notify_slack(
            payload.event_type or "manual",
            payload.message or "Notificación de Contecflow",
            payload.channel,
            payload.source_id,
            db,
        ))
    except ValueError as e:
        raise HTTPException(400, str(e))

