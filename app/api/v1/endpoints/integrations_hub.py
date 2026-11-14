"""
integrations_hub.py — Endpoints para Slack, Teams y Jira.
"""
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Body, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.entorno import en_pruebas
from pydantic import BaseModel

from app.core.config import settings
from app.core.responses import APIResponse
from app.core.secret_utils import decrypt_config_secrets
from app.db.session import get_db
from app.core.deps import require_any_manager, require_admin
from app.models.user import User
from app.core.errores import ErrorDeDominio
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations-hub"])


# ── Schemas ────────────────────────────────────────────────────────────────────
class SlackTestIn(BaseModel):
    webhook_url: str
    message:     str = f"✅ {NOMBRE_DEL_PRODUCTO} conectado correctamente con Slack"

class TeamsTestIn(BaseModel):
    webhook_url: str
    message:     str = f"✅ {NOMBRE_DEL_PRODUCTO} conectado correctamente con Teams"

class JiraTestIn(BaseModel):
    # Segunda auditoria 2026-11 (#23): sin datos se prueba la conexion guardada
    # de la organizacion; sin token, el guardado con la URL/email del cuerpo.
    base_url:  Optional[str] = None
    email:     Optional[str] = None
    api_token: Optional[str] = None

class JiraConfigHubIn(BaseModel):
    name:        Optional[str] = None
    base_url:    str
    email:       str
    api_token:   Optional[str] = None   # vacio = conservar el guardado
    project_key: Optional[str] = None

class JiraIssueIn(BaseModel):
    integration_id: Optional[str] = None  # obsoleto (#23): se usa la conexion de la organizacion
    project_key:    str
    summary:        str
    description:    str = ""
    issue_type:     str = "Task"
    priority:       str = "Medium"
    labels:         Optional[list] = None
    nexus_task_id:  Optional[str] = None  # vincular con tarea Contecflow


# ── Slack endpoints ────────────────────────────────────────────────────────────
@router.post("/slack/test", summary="Probar conexión Slack")
def test_slack(
    payload: SlackTestIn,
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_slack_message, build_slack_blocks
    blocks = build_slack_blocks(
        f"🔗 {NOMBRE_DEL_PRODUCTO} — Conexión verificada",
        [("Usuario", current_user.full_name), ("Hora", datetime.now().strftime("%H:%M"))],
    )
    result = send_slack_message(payload.webhook_url, payload.message, blocks=blocks)
    if not result["ok"]:
        raise HTTPException(400, f"Error Slack: {result.get('error')}")
    return APIResponse.ok(data={"ok": True, "message": "Mensaje enviado a Slack correctamente"})


@router.post("/slack/notify", summary="Enviar notificación manual a Slack")
def notify_slack(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_slack_message, get_active_integration
    import json
    cfg = get_active_integration(db, payload.get("integration_id"))
    if not cfg: raise HTTPException(404, "Integración no encontrada")
    cfg_dict     = decrypt_config_secrets(json.loads(cfg.config or "{}"))
    webhook_url  = cfg_dict.get("webhook_url", "")
    if not webhook_url: raise HTTPException(400, "Webhook URL no configurada")

    result = send_slack_message(webhook_url, payload.get("text", f"Notificación de {NOMBRE_DEL_PRODUCTO}"))
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    return APIResponse.ok(data={"ok": True})


# ── Teams endpoints ────────────────────────────────────────────────────────────
@router.post("/teams/test", summary="Probar conexión Microsoft Teams")
def test_teams(
    payload: TeamsTestIn,
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_teams_message
    result = send_teams_message(
        payload.webhook_url,
        title=f"🔗 {NOMBRE_DEL_PRODUCTO} — Conexión verificada",
        text=payload.message,
        facts=[("Usuario", current_user.full_name), ("Hora", datetime.now().strftime("%H:%M"))],
    )
    if not result["ok"]:
        raise HTTPException(400, f"Error Teams: {result.get('error')}")
    return APIResponse.ok(data={"ok": True, "message": "Mensaje enviado a Teams correctamente"})


# ── Jira endpoints ─────────────────────────────────────────────────────────────
# Segunda auditoria 2026-11 (#23): todo el hub usa la `JiraConfig` de tareas de
# la organizacion (`jira_service`), no filas `integration_configs` de tipo jira.

@router.get("/jira/config", summary="Conexión de Jira de la organización (sin token)")
def get_jira_hub_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services import jira_service
    return APIResponse.ok(data=jira_service.config_del_hub(
        jira_service.configuracion_de_tareas(db, current_user.organization_id)))


@router.put("/jira/config", summary="Guardar la conexión de Jira de la organización")
def put_jira_hub_config(
    payload: JiraConfigHubIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import jira_service
    from app.services.audit import auditar_y_confirmar
    try:
        config = jira_service.guardar_desde_hub(
            db, current_user.organization_id, base_url=payload.base_url, email=payload.email,
            api_token=payload.api_token or None, project_key=payload.project_key,
            name=payload.name, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    auditar_y_confirmar(db, current_user, "UPDATE", "jira_config", config.id, config.name,
                        new_values={"base_url": config.jira_base_url, "email": config.jira_email,
                                    "token_changed": bool(payload.api_token)})
    return APIResponse.ok(data=jira_service.config_del_hub(config))


@router.delete("/jira/config", summary="Desactivar la conexión de Jira (borra el token)")
def delete_jira_hub_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import jira_service
    if not jira_service.desactivar_desde_hub(db, current_user.organization_id):
        raise HTTPException(404, "Jira no está configurado en esta organización")
    return APIResponse.ok(data={"ok": True, "deactivated": True})


@router.post("/jira/sync", summary="Jira → tareas: trae el estado de las incidencias enlazadas")
def sync_jira_hub(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import jira_service
    from app.services.cab_service.integraciones import sincronizar_tareas_con_jira
    cfg = jira_service.credenciales_del_hub(db, current_user.organization_id)
    synced, errors = sincronizar_tareas_con_jira(db, cfg)
    jira_service.marcar_sincronizacion_completa(db, current_user.organization_id)
    if errors and not synced:
        raise HTTPException(400, errors[0])
    return APIResponse.ok(data={"ok": True, "synced": synced, "errors": errors[:5]})


@router.post("/jira/test", summary="Verificar conexión con Jira")
def test_jira(
    payload: JiraTestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import get_jira_projects
    from app.services import jira_service
    if payload.base_url and payload.email and payload.api_token:
        cfg = {"base_url": payload.base_url, "email": payload.email, "api_token": payload.api_token}
    else:
        cfg = jira_service.credenciales_del_hub(db, current_user.organization_id)
        if payload.base_url:
            cfg["base_url"] = payload.base_url
        if payload.email:
            cfg["email"] = payload.email
    result = get_jira_projects(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error Jira: {result.get('error')}")
    projects = result["data"].get("values", [])
    return APIResponse.ok(data={
        "ok": True,
        "projects": [{"key": p["key"], "name": p["name"]} for p in projects[:20]],
        "total": len(projects),
    })


@router.post("/jira/issues", summary=f"Crear issue en Jira desde {NOMBRE_DEL_PRODUCTO}")
def create_jira_issue(
    payload: JiraIssueIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import create_jira_issue as _create_issue, link_jira_to_task
    from app.services import jira_service

    cfg_dict = jira_service.credenciales_del_hub(db, current_user.organization_id)
    result = _create_issue(
        cfg_dict,
        project_key=payload.project_key,
        summary=payload.summary,
        description=payload.description,
        issue_type=payload.issue_type,
        priority=payload.priority,
        labels=payload.labels or [],
    )
    if not result["ok"]:
        raise HTTPException(400, f"Error Jira: {result.get('error')}")

    if payload.nexus_task_id and result.get("key"):
        link_jira_to_task(db, payload.nexus_task_id, result["key"])

    return APIResponse.ok(data=result)


@router.get("/jira/search", summary="Buscar issues en Jira via JQL")
def search_jira(
    integration_id: Optional[str] = Query(None, description="Obsoleto (#23): se ignora"),
    jql:            str = Query("project = NEXUS ORDER BY created DESC"),
    max_results:    int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import search_jira_issues
    from app.services import jira_service

    cfg_dict = jira_service.credenciales_del_hub(db, current_user.organization_id)
    result = search_jira_issues(cfg_dict, jql, max_results)
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    issues = result["data"].get("issues", [])
    return APIResponse.ok(data={
        "total": result["data"].get("total", 0),
        "issues": [{
            "key":      i["key"],
            "summary":  i["fields"]["summary"],
            "status":   i["fields"]["status"]["name"],
            "priority": i["fields"].get("priority", {}).get("name", "—"),
            "assignee": (i["fields"].get("assignee") or {}).get("displayName", "—"),
        } for i in issues],
    })


@router.post("/jira/transition", summary="Cambiar estado de issue Jira")
def transition_jira(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import transition_jira_issue
    from app.services import jira_service

    cfg_dict = jira_service.credenciales_del_hub(db, current_user.organization_id)
    result = transition_jira_issue(cfg_dict, payload.get("issue_key"), payload.get("transition"))
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    return APIResponse.ok(data={"ok": True})


# ── Evento manual ──────────────────────────────────────────────────────────────
@router.post("/notify-event", summary="Disparar notificación de evento a Slack/Teams")
def manual_event_notify(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import notify_event
    results = notify_event(
        event_type=payload.get("event_type", ""),
        entity=payload.get("entity", {}),
        db=db,
        organization_id=current_user.organization_id,
    )
    return APIResponse.ok(data={"ok": True, "dispatched": len(results), "results": results})


# ── Inbound bot — la autenticación de cada plataforma ─────────────────────────
async def _verificar_firma_de_slack(request: Request, db=None) -> bytes:
    """Comprueba la firma de Slack y devuelve el cuerpo crudo.

    Auditoría 2026-08 (hallazgo 18). Vivía dentro del manejador, que por esto y
    por la tabla de verbos llegaba a complejidad 12. Devolver el cuerpo es
    obligatorio, no una comodidad: la firma se calcula **sobre los bytes tal
    como llegaron**, así que quien los lee tiene que ser el mismo que los
    verifica — un segundo `await request.body()` no está garantizado.

    Las dos cosas que hace, y que se conservan verbatim:

      · el **antirreplay**: una petición con más de cinco minutos se rechaza,
        porque una firma válida capturada de un log sigue siendo válida para
        siempre si nadie mira la hora;
      · `hmac.compare_digest` y no `==`: comparar firmas con `==` filtra por
        cuánto tarda en fallar.

    Sin `SLACK_SIGNING_SECRET` configurado el receptor devuelve **503 y no 200
    silencioso**: aceptar comandos sin poder verificar quién los manda sería
    peor que no tener el bot. La excepción es `TESTING=1`.
    """
    import hashlib
    import hmac

    body_bytes = await request.body()
    signing_secret = settings.SLACK_SIGNING_SECRET
    if db is not None:
        # Segunda auditoría 2026-11 (#8): si el `team_id` está vinculado a una
        # organización, se verifica con SU secreto (o el global si no tiene).
        # Vinculado a varias: se rechaza, sin caer a la búsqueda global. El
        # `team_id` se lee antes de verificar porque solo elige el secreto: un
        # `team_id` falso lleva a un secreto que el atacante no conoce.
        from urllib.parse import parse_qs
        from app.core.async_db import run_db
        from app.services.integrations import (
            VinculoAmbiguo, organizacion_del_workspace_de_slack, secreto_de_firma_de_slack,
        )
        team_id = (parse_qs(body_bytes.decode(errors="replace")).get("team_id") or [None])[0]
        try:
            org = await run_db(organizacion_del_workspace_de_slack, db, team_id)
        except VinculoAmbiguo:
            raise HTTPException(403, "Slack workspace linked to several organizations")
        signing_secret = await run_db(secreto_de_firma_de_slack, db, org)
    if not signing_secret:
        if not en_pruebas():
            raise HTTPException(503, "Slack inbound commands are not configured")
        return body_bytes

    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")
    try:
        import time as _time
        if abs(_time.time() - float(ts)) > 300:
            raise HTTPException(403, "Request timestamp too old")
    except (ValueError, TypeError):
        raise HTTPException(403, "Missing or invalid X-Slack-Request-Timestamp")

    base = f"v0:{ts}:{body_bytes.decode()}"
    expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(403, "Invalid Slack signature")
    return body_bytes


#: Cliente de claves públicas de Bot Framework, cacheado entre peticiones.
#:
#: `PyJWKClient` guarda las claves que descarga, así que crear uno por petición
#: haría una llamada HTTP a Microsoft en **cada** comando entrante. Se guarda
#: por URL y no en una global suelta porque la URL es configurable: si alguien
#: cambia el ajuste en caliente, el cliente viejo no debe seguir sirviendo.
_JWKS_DE_TEAMS: dict[str, object] = {}


def _claves_de_bot_framework(metadata_url: str):
    """El `PyJWKClient` del emisor, creado una vez por URL.

    Los metadatos OpenID traen el `jwks_uri`; de ahí salen las claves públicas.
    Se valida que ambas URLs sean HTTPS y no apunten a una red interna, con el
    mismo verificador que usa el flujo de SSO: son URLs que vienen de
    configuración, y la configuración de un despliegue también puede estar mal.
    """
    import json as _json
    import urllib.request

    import jwt as _jwt

    from app.services.auth_service import validate_https_discovery_url

    cliente = _JWKS_DE_TEAMS.get(metadata_url)
    if cliente is not None:
        return cliente

    validate_https_discovery_url(metadata_url)
    with urllib.request.urlopen(metadata_url, timeout=outbound_http_timeout(default=5)) as resp:  # noqa: S310
        metadatos = _json.loads(resp.read())
    jwks_uri = metadatos.get("jwks_uri")
    if not jwks_uri:
        raise HTTPException(
            502, "Los metadatos de Bot Framework no declaran `jwks_uri`")
    validate_https_discovery_url(jwks_uri)

    cliente = _jwt.PyJWKClient(jwks_uri)
    _JWKS_DE_TEAMS[metadata_url] = cliente
    return cliente


def _verificar_token_de_teams(request: Request) -> Optional[dict]:
    """Verifica el bearer de Teams: **firma**, emisor y audiencia.

    Auditoría 2026-08/09. Esto empezó dentro del manejador y sólo comprobaba la
    audiencia: decodificaba el cuerpo del JWT sin verificar nada y comparaba
    `aud`/`appid` con `TEAMS_BOT_APP_ID`. Quedó anotado con todas las letras —
    «es una comprobación de destinatario, no de emisor: frena un token de otro
    bot, no uno fabricado»—, y esa nota describía un agujero real: **cualquiera
    que supiera el id de aplicación del bot podía escribir un JWT a mano, sin
    firmar, y el receptor lo aceptaba**. El id de aplicación no es un secreto.

    Ahora se verifica la firma contra las claves públicas de Bot Framework, más
    el emisor, la audiencia y la caducidad. `jwt.decode` hace las cuatro cosas:
    no se comprueba ninguna a mano, que es donde se cuelan los fallos.

    Lo que **no** cubre, dicho para que no haya que adivinarlo: no se comprueba
    el `serviceUrl` del cuerpo de la actividad contra el `serviceurl` del token.
    Bot Framework lo documenta como paso adicional y sirve para que un bot no
    reenvíe respuestas a un servicio que no es el suyo; aquí no se reenvía nada,
    sólo se responde en el mismo ciclo HTTP.

    El `except HTTPException: raise` es a propósito: sin él, el 403 de audiencia
    lo capturaría el `except Exception` de al lado y saldría como «token
    inválido», que es un mensaje distinto y menos cierto.
    """
    import jwt as _jwt

    bot_app_id = settings.TEAMS_BOT_APP_ID
    if not bot_app_id:
        if not en_pruebas():
            raise HTTPException(503, "Teams inbound commands are not configured")
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing Teams bearer token")
    raw_token = auth_header.removeprefix("Bearer ").strip()

    try:
        cliente = _claves_de_bot_framework(settings.TEAMS_BOT_OPENID_METADATA_URL)
        clave = cliente.get_signing_key_from_jwt(raw_token)
        # Revisión 2026-11: se devuelven los claims; `serviceurl` dice a dónde se
        # puede contestar (ver app/services/teams_bot.py).
        return _jwt.decode(
            raw_token,
            clave.key,
            algorithms=["RS256"],
            audience=bot_app_id,
            issuer=settings.TEAMS_BOT_ISSUER,
            options={"verify_exp": True, "verify_signature": True},
        )
    # intentional: chained re-raise preserves context
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception:
        # Un solo mensaje para todos los modos de fallo —firma mala, emisor
        # equivocado, audiencia equivocada, caducado— porque distinguirlos en la
        # respuesta le dice a quien lo intenta por dónde va. El detalle va al
        # registro, que es donde sirve.
        logger.warning(
            "Bearer de Teams rechazado (firma, emisor, audiencia o caducidad)",
            exc_info=True)
        raise HTTPException(403, "Invalid Teams bearer token")


# ── Inbound bot — Slack slash commands ────────────────────────────────────────
@router.post("/slack/commands", summary="Receptor de slash commands desde Slack", include_in_schema=False)
async def slack_inbound_command(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives Slack slash command payloads (application/x-www-form-urlencoded).
    Supported commands:
      /contecflow tarea <título> [#proyecto]  → crear tarea
      /contecflow tiempo <horas> [#proyecto]  → registrar imputación del día de hoy
      /contecflow ticket <asunto>             → crear ticket en Service Desk
      /contecflow estado <code>               → consultar estado de tarea/proyecto
      /contecflow ayuda                       → lista de comandos
    Security: validates X-Slack-Signature (HMAC-SHA256) when SLACK_SIGNING_SECRET is set.
    """
    body_bytes = await _verificar_firma_de_slack(request, db)

    from urllib.parse import parse_qs
    params = {k: v[0] for k, v in parse_qs(body_bytes.decode()).items()}

    # Audit #C7: async webhook (await request.body() for HMAC). DB work via
    # threadpool — the slack_* helpers below are sync internally.
    from app.core.async_db import run_db
    from app.services.integrations import find_user_by_slack_name
    contecflow_user = await run_db(find_user_by_slack_name, db, params.get("user_name", ""),
                                   params.get("team_id"))

    return await _ejecutar_comando_del_bot(
        params.get("text", "").strip(), contecflow_user, db, canal="Slack")


async def _slack_create_task(text: str, user, db):
    """Parse: tarea <título> [#proyecto-code]"""
    from app.core.async_db import run_db
    from app.services.integrations import slack_create_task_from_text
    return await run_db(slack_create_task_from_text, db, text, user)


async def _slack_log_time(text: str, user, db):
    """Parse: tiempo <horas> [#proyecto-code] [descripción]"""
    from app.core.async_db import run_db
    from app.services.integrations import slack_log_time_from_text
    return await run_db(slack_log_time_from_text, db, text, user)


async def _slack_create_ticket(text: str, user, db):
    """Creates a Service Desk incident ticket from Slack."""
    from app.core.async_db import run_db
    from app.services.integrations import slack_create_ticket_from_text
    return await run_db(slack_create_ticket_from_text, db, text, user)


async def _slack_get_status(code: str, user, db):
    # `user` no se usa: consultar el estado de un código no depende de quién
    # pregunta. Está en la firma para que los cinco manejadores tengan la misma
    # y quepan en `_COMANDOS` sin envoltorios.
    from app.core.async_db import run_db
    from app.services.integrations import slack_get_status_by_code
    return await run_db(slack_get_status_by_code, db, code)


from app.services.integrations import slack_help_response as _slack_help


# ── El repertorio de comandos, en un solo sitio ───────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). Esta tabla estaba escrita **dos veces**, en
# forma de `if verb in (...) / elif` dentro de cada receptor: uno para Slack y
# otro para Teams. Y las dos copias **no decían lo mismo**: Slack aceptaba
# `horas` como sinónimo de `tiempo` y Teams no, así que un usuario de Teams que
# escribía «horas 3» recibía la ayuda en lugar de registrar sus tres horas. No
# había ninguna razón para la diferencia; el docstring del receptor de Teams
# decía literalmente «commands identical to the Slack bot».
#
# Con la tabla, añadir un verbo o un sinónimo es una línea y las dos
# plataformas lo tienen a la vez. Un verbo desconocido cae en la ayuda, que es
# lo que hacían las dos ramas `else` — y por eso `ayuda`/`help` no necesitan
# entrada propia.
_COMANDOS = {
    "tarea":  _slack_create_task,
    "task":   _slack_create_task,
    "tiempo": _slack_log_time,
    "time":   _slack_log_time,
    "horas":  _slack_log_time,
    "ticket": _slack_create_ticket,
    "estado": _slack_get_status,
    "status": _slack_get_status,
}


async def _ejecutar_comando_del_bot(texto: str, usuario, db, *, canal: str) -> dict:
    """Parte el texto en verbo y resto, y despacha.

    Devuelve siempre el formato de respuesta de Slack —`{"text": ...}`, con
    `response_type` cuando toca—, y el receptor de Teams se queda con el `text`
    para meterlo en su `Activity`. Es el formato que ya producían los
    manejadores; unificarlo aquí evita que el `try/except` de arriba viva
    duplicado, que era la otra mitad de la copia.

    El `except Exception` es a propósito y es de las veces en que lo es: un
    comando que revienta tiene que volver como un mensaje legible en el chat de
    quien lo escribió. Un 500 en un webhook de Slack se ve como «operación
    fallida» sin más, y el error se pierde. Se registra con `exc_info` y se
    devuelve; `canal` está para que el log diga de qué plataforma venía.
    """
    partes = texto.split(None, 1)
    verbo = (partes[0] if partes else "").lower()
    resto = partes[1] if len(partes) > 1 else ""

    manejador = _COMANDOS.get(verbo)
    if manejador is None:
        return _slack_help()
    if usuario is None:
        # Auditoria 2026-11: sin usuario se creaban tareas y tickets anonimos y
        # se consultaban codigos de cualquier organizacion.
        return {"response_type": "ephemeral",
                "text": f"❌ No encuentro un único usuario de {NOMBRE_DEL_PRODUCTO} para ti en {canal}. "
                        "Tu nombre de usuario o la parte de tu correo antes de la @ (Slack), o tu "
                        f"nombre completo (Teams), tienen que coincidir exactamente con los de {NOMBRE_DEL_PRODUCTO}."}
    # Todo el comando corre en la organizacion de ese usuario.
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, usuario)
    db.info["is_superadmin"] = False
    try:
        return await manejador(resto, usuario, db)
    except Exception as exc:
        logger.warning(
            "Fallo procesando comando entrante de %s: %s", canal, exc, exc_info=True)
        return {"response_type": "ephemeral", "text": f"❌ Error: {exc}"}


# ── Inbound bot — MS Teams adaptive card actions ──────────────────────────────
@router.post("/teams/commands", summary="Receptor de acciones de MS Teams", include_in_schema=False)
async def teams_inbound_command(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Receives Teams Bot Framework activity payloads (JSON).
    Supports conversational commands identical to the Slack bot.
    Validates Bearer token audience against TEAMS_BOT_APP_ID env var.
    """
    # Auditoria 2026-11: verificar el token puede descargar los metadatos y las
    # claves de Bot Framework (urlopen / PyJWKClient, red sincrona): al pool.
    from app.core.async_db import run_db
    claims = await run_db(_verificar_token_de_teams, request)

    body = await request.json()
    original = (body.get("text") or "").strip()
    text = original.lower()
    # Extract user info from Teams payload
    teams_name = body.get("from", {}).get("name", "").strip()

    # Audit #C7: DB lookup offloaded to threadpool.
    from app.core.async_db import run_db
    from app.services.integrations import find_user_by_teams_name
    # El tenant lo pone el Bot Framework de Microsoft (peticion con token verificado).
    tenant_id = ((body.get("channelData") or {}).get("tenant") or {}).get("id")         or (body.get("conversation") or {}).get("tenantId")
    contecflow_user = (await run_db(find_user_by_teams_name, db, teams_name, tenant_id)) if teams_name else None

    # Revisión 2026-11: lo que no es un comando se contesta con la base de
    # conocimiento de la empresa de quien escribe (app/services/teams_bot.py).
    from app.services import teams_bot
    from app.services.settings_service import get_runtime_bool
    verbo = (text.split(None, 1) or [""])[0]
    if (verbo not in _COMANDOS and contecflow_user is not None and original
            and (await run_db(get_runtime_bool, db, "TEAMS_KB_ANSWERS_ENABLED",
                              contecflow_user.organization_id)) is not False):
        from app.db.session import publicar_contexto_de_tenant
        publicar_contexto_de_tenant(db, contecflow_user)
        texto = await run_db(teams_bot.respuesta_de_la_base, db, contecflow_user, original)
    else:
        resultado = await _ejecutar_comando_del_bot(text, contecflow_user, db, canal="Teams")
        texto = resultado.get("text", "✅")

    # Bot Framework no lee este cuerpo para un mensaje: la respuesta se envía al
    # `serviceUrl` de la conversación, si coincide con el del token firmado.
    destino = teams_bot.service_url_valido(body, claims)
    if destino:
        background.add_task(teams_bot.enviar, body, texto, destino)
    return {"type": "message", "text": texto}
