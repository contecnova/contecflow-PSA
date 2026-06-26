"""Admin + OAuth + Push + Digest endpoints para collaboration."""
from datetime import datetime
from app.core.timeutil import utcnow
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.models.collaboration import (
    CollaborationIntegration, CollaborationPushSubscription,
)
from app.services.collaboration import _push as push_svc
from app.services.collaboration._integrations import (
    PROVIDERS, auth_url_for, configured_providers, encrypt, handle_callback,
)

router = APIRouter()


# ── Web push subscription ───────────────────────────────────────────────────
@router.get("/push/public-key", summary="Clave pública VAPID")
def push_public_key():
    return {
        "configured": push_svc.is_configured(),
        "public_key": push_svc.public_key(),
    }


@router.post("/push/subscribe", summary="Registrar suscripción Web Push")
def push_subscribe(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = payload.get("subscription") or payload
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not (endpoint and p256dh and auth):
        raise HTTPException(400, "subscription.endpoint + keys.p256dh + keys.auth requeridos")
    existing = db.query(CollaborationPushSubscription).filter(
        CollaborationPushSubscription.endpoint == endpoint
    ).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh_key = p256dh
        existing.auth_key = auth
        existing.is_active = True
    else:
        db.add(CollaborationPushSubscription(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            endpoint=endpoint, p256dh_key=p256dh, auth_key=auth,
            user_agent=(payload.get("user_agent") or "")[:255],
        ))
    db.commit()
    return {"ok": True}


@router.post("/push/test", summary="Disparar push de prueba a mí")
def push_test(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = push_svc.push_to_user(db, current_user.id, {
        "title": "Contecflow Chat",
        "body": "Web Push funcionando ✓",
        "url": "/chat",
    })
    return {"delivered": n, "configured": push_svc.is_configured()}


@router.delete("/push/unsubscribe", summary="Borrar suscripción por endpoint")
def push_unsubscribe(endpoint: str = Body(..., embed=True), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_push_subscription", str(current_user.id), action="delete")
    n = db.query(CollaborationPushSubscription).filter(
        CollaborationPushSubscription.endpoint == endpoint,
        CollaborationPushSubscription.user_id == current_user.id,
    ).delete()
    db.commit()
    return {"deleted": n}


# ── Email digest ────────────────────────────────────────────────────────────
@router.post("/admin/email-digest/run", summary="Ejecutar digest (admin)",
             dependencies=[Depends(require_admin)])
def run_digest(
    dry_run: bool = Query(False),
    frequency: Optional[str] = Query(None, pattern="^(daily|weekly)$"),
    db: Session = Depends(get_db),
):
    from app.services.collaboration._email_digest import run as run_digest_svc
    return run_digest_svc(db, dry_run=dry_run, frequency=frequency)


# ── OAuth integraciones ─────────────────────────────────────────────────────
@router.get("/integrations/providers", summary="Estado de OAuth por proveedor")
def list_providers(current_user: User = Depends(get_current_user)):
    return {"providers": configured_providers()}


@router.get("/integrations/{integration_id}/oauth/start", summary="Iniciar OAuth")
def oauth_start(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(CollaborationIntegration).filter(
        CollaborationIntegration.id == integration_id,
        CollaborationIntegration.organization_id == current_user.organization_id,
    ).first()
    if not row:
        raise HTTPException(404, "Integración no encontrada")
    if row.kind not in PROVIDERS:
        raise HTTPException(400, "Proveedor sin OAuth")
    url = auth_url_for(row.kind, row.id)
    if not url:
        raise HTTPException(503, f"Faltan credenciales OAuth para {row.kind}")
    return RedirectResponse(url=url, status_code=302)


@router.get("/calendar/events", summary="Eventos próximos (Google + M365 agregados)")
async def calendar_events(
    days: int = Query(7, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve eventos próximos de cualquier integracion calendario activa."""
    rows = db.query(CollaborationIntegration).filter(
        CollaborationIntegration.organization_id == current_user.organization_id,
        CollaborationIntegration.is_enabled == True,  # noqa: E712
        CollaborationIntegration.kind.in_(["google_calendar", "microsoft_365"]),
    ).all()
    out = []
    for it in rows:
        try:
            if it.kind == "google_calendar":
                from app.services.collaboration._integrations_clients import google_calendar_list
                r = await google_calendar_list(it, max_results=20)
                items = (r.get("body") or {}).get("items") or []
                for ev in items:
                    out.append({
                        "id": ev.get("id"),
                        "title": ev.get("summary"),
                        "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
                        "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
                        "source": "google",
                        "link": ev.get("htmlLink"),
                    })
            elif it.kind == "microsoft_365":
                from app.services.collaboration._integrations_clients import m365_calendar_list
                r = await m365_calendar_list(it, top=20)
                items = (r.get("body") or {}).get("value") or []
                for ev in items:
                    out.append({
                        "id": ev.get("id"),
                        "title": ev.get("subject"),
                        "start": (ev.get("start") or {}).get("dateTime"),
                        "end": (ev.get("end") or {}).get("dateTime"),
                        "source": "m365",
                        "link": ev.get("webLink"),
                    })
        except Exception:
            continue
    out.sort(key=lambda e: e.get("start") or "")
    return {"events": out, "providers_connected": [it.kind for it in rows]}


@router.get("/integrations/oauth/callback", summary="Callback OAuth (cualquier proveedor)")
async def oauth_callback(
    state: str = Query(...),
    code: str = Query(...),
    db: Session = Depends(get_db),
):
    integration_id, token_data, err = await handle_callback(state, code)
    if err or not integration_id:
        return HTMLResponse(f"<h2>OAuth error</h2><pre>{err}</pre>", status_code=400)
    row = db.query(CollaborationIntegration).filter(CollaborationIntegration.id == integration_id).first()
    if not row:
        return HTMLResponse("<h2>Integración inexistente</h2>", status_code=404)
    row.access_token_enc = encrypt(token_data.get("access_token"))
    row.refresh_token_enc = encrypt(token_data.get("refresh_token"))
    expires_in = token_data.get("expires_in")
    if expires_in:
        from datetime import timedelta
        row.token_expires_at = utcnow() + timedelta(seconds=int(expires_in))
    cfg = dict(row.config or {})
    # Persist additional provider-specific data (cloud_id Jira, etc.)
    for k in ("cloud_id", "scope", "token_type", "id_token"):
        if k in token_data:
            cfg[k] = token_data[k]
    row.config = cfg
    row.is_enabled = True
    db.commit()
    return HTMLResponse(f"<h2>OAuth completado para {row.kind} ✓</h2><p>Puedes cerrar esta ventana.</p>")
