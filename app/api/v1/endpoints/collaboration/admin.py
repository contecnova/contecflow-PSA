"""Admin + OAuth + Push + Digest endpoints para collaboration.

Auditoria 2026-08 (hallazgo 22). Los 8 puntos de acceso a base de este fichero
estan en `app/services/collaboration/admin.py`, y con ellos salieron tres cosas
que el endpoint tapaba: `days` del calendario se declaraba y no se usaba (y sin
limite inferior los proveedores devolvian los eventos mas ANTIGUOS como
proximos), un proveedor con el token caducado desaparecia sin log mientras
seguia anunciandose como conectado, y el alta de suscripcion push podia chocar
con la unicidad global de `endpoint` y dar un 500. Ver el modulo de servicio.
"""
from html import escape
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.collaboration import _push as push_svc
from app.services.collaboration import admin as svc
from app.services.collaboration._integrations import configured_providers, handle_callback
from app.core.constantes import NOMBRE_DEL_PRODUCTO

router = APIRouter()


# ── Web push subscription ───────────────────────────────────────────────────
@router.get("/push/public-key", summary="Clave pública VAPID")
def push_public_key():
    return APIResponse.ok(data={
        "configured": push_svc.is_configured(),
        "public_key": push_svc.public_key(),
    })


@router.post("/push/subscribe", summary="Registrar suscripción Web Push")
def push_subscribe(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=svc.guardar_suscripcion_push(db, current_user, payload))


@router.post("/push/test", summary="Disparar push de prueba a mí")
def push_test(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = push_svc.push_to_user(db, current_user.id, {
        "title": f"{NOMBRE_DEL_PRODUCTO} Chat",
        "body": "Web Push funcionando ✓",
        "url": "/chat",
    })
    return APIResponse.ok(data={"delivered": n, "configured": push_svc.is_configured()})


@router.delete("/push/unsubscribe", summary="Borrar suscripción por endpoint")
def push_unsubscribe(
    endpoint: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_abac(db, current_user, "collaboration_push_subscription", str(current_user.id), action="delete")
    return APIResponse.ok(
        data={"deleted": svc.borrar_suscripcion_push(db, current_user, endpoint)})


# ── Email digest ────────────────────────────────────────────────────────────
@router.post("/admin/email-digest/run", summary="Ejecutar digest (admin)",
             dependencies=[Depends(require_admin)])
def run_digest(
    dry_run: bool = Query(False),
    frequency: Optional[str] = Query(None, pattern="^(daily|weekly)$"),
    db: Session = Depends(get_db),
):
    from app.services.collaboration._email_digest import run as run_digest_svc
    if dry_run:  # vista previa: no manda nada, se queda en la peticion
        return APIResponse.ok(data=run_digest_svc(db, dry_run=True, frequency=frequency))
    # Segunda auditoria 2026-11 (n.º 20): un correo por usuario (SMTP) va al
    # worker. Con cola: 202 `{status: "queued"}`. Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    resultado = encolar(run_digest_svc, frequency=frequency, _sesion=db)
    if resultado is EN_COLA:
        return respuesta_en_cola(frequency=frequency)
    return APIResponse.ok(data=resultado)


# ── OAuth integraciones ─────────────────────────────────────────────────────
@router.get("/integrations/providers", summary="Estado de OAuth por proveedor")
def list_providers(current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data={"providers": configured_providers()})


@router.get("/integrations/{integration_id}/oauth/start", summary="Iniciar OAuth")
def oauth_start(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Auditoria 2026-11 (#26): el `state` queda ligado a este usuario y a este
    # navegador (cookie HttpOnly que solo viaja al callback).
    import secrets as _secrets
    from app.core.config import settings as _settings
    from app.services.collaboration._integrations import CALLBACK_PATH, COOKIE_DE_VINCULO

    vinculo = _secrets.token_urlsafe(24)
    respuesta = RedirectResponse(
        url=svc.url_de_oauth(db, current_user, integration_id, vinculo=vinculo), status_code=302)
    respuesta.set_cookie(COOKIE_DE_VINCULO, vinculo, max_age=600, path=CALLBACK_PATH, httponly=True,
                         samesite="lax", secure=_settings.ENVIRONMENT in {"production", "staging"})
    return respuesta


@router.get("/calendar/events", summary="Eventos próximos (Google + M365 agregados)")
async def calendar_events(
    days: int = Query(7, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Eventos de los próximos `days` días de toda integración de calendario activa."""
    return APIResponse.ok(data=await svc.eventos_de_calendario(db, current_user, days))


@router.get("/integrations/oauth/callback", summary="Callback OAuth (cualquier proveedor)")
async def oauth_callback(
    request: Request,
    state: str = Query(...),
    code: str = Query(...),
    db: Session = Depends(get_db),
):
    """El callback llega sin sesión de usuario: lo que autoriza la escritura es
    el `state` firmado que valida `handle_callback`.

    Auditoria 2026-08: los dos valores que se interpolan van escapados. El
    mensaje de error incluye el cuerpo de la respuesta del proveedor
    (`r.text[:200]` en `handle_callback`), que es contenido remoto que no
    controlamos, y se estaba metiendo tal cual en el HTML de nuestro origen.
    `kind` sale de una columna de texto libre, asi que se escapa igual.
    """
    from app.core.async_db import run_db

    from app.services.collaboration._integrations import COOKIE_DE_VINCULO

    integration_id, token_data, err, org_id = await handle_callback(
        state, code, request.cookies.get(COOKIE_DE_VINCULO))
    if err or not integration_id:
        return HTMLResponse(
            f"<h2>OAuth error</h2><pre>{escape(str(err))}</pre>", status_code=400)

    kind = await run_db(svc.guardar_tokens_de_oauth, db, integration_id, token_data, org_id)
    if kind is None:
        return HTMLResponse("<h2>Integración inexistente</h2>", status_code=404)
    return HTMLResponse(
        f"<h2>OAuth completado para {escape(kind)} ✓</h2>"
        "<p>Puedes cerrar esta ventana.</p>")
