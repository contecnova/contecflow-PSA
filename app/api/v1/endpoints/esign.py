"""
E-firma endpoint — create, list, track and receive webhook callbacks for
DocuSign and Adobe Sign envelopes linked to documents.

Since DocuSign/Adobe Sign OAuth flows require user-specific tokens that live
outside NexusPM's server, this module uses the "service account" / JWT
grant flow (DocuSign) or the refresh-token approach (Adobe Sign).

For a minimal integration (common for internal PM tools), the flow is:
  1. Admin configures keys in Settings → E-firma
  2. A user clicks "Request signatures" on a document
  3. NexusPM calls the provider API to create an envelope
  4. The provider sends a webhook back when status changes
  5. NexusPM updates the envelope status and notifies the document owner

When NO provider keys are configured:
  - Envelopes are created in "manual" mode — NexusPM manages state only.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.responses import APIListResponse
from app.models.esign import ESignEnvelope, ESignProvider, ESignStatus
from app.models.user import User
from app.models.settings import AppSetting
from app.core.abac_enforce import enforce_abac
from app.services import esign_service

router = APIRouter()
_logger = logging.getLogger(__name__)

# ── E-sign config keys stored in AppSetting KV store ──────────────────────────
_ESIGN_KEYS = [
    "esign.docusign_integration_key",
    "esign.docusign_secret_key",
    "esign.docusign_account_id",
    "esign.docusign_base_url",
    "esign.adobe_sign_client_id",
    "esign.adobe_sign_client_secret",
    "esign.adobe_sign_base_url",
]
_SECRET_KEYS = {"esign.docusign_secret_key", "esign.adobe_sign_client_secret"}


def _get_esign_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else None


def _set_esign_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=f"E-firma config: {key}"))
    db.commit()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SignerIn(BaseModel):
    name:          str
    email:         str
    routing_order: int = 1
    user_id:       Optional[int] = None


class EnvelopeCreate(BaseModel):
    document_id:  int
    subject:      str
    message:      Optional[str] = None
    provider:     ESignProvider = ESignProvider.manual
    signers:      List[SignerIn]
    expires_days: int = 7


class SignerOut(BaseModel):
    id:            int
    name:          str
    email:         str
    routing_order: int
    signed:        bool
    signed_at:     Optional[datetime]
    signing_url:   Optional[str]

    class Config:
        from_attributes = True


class EnvelopeOut(BaseModel):
    id:               int
    document_id:      int
    provider:         str
    subject:          Optional[str]
    message:          Optional[str]
    status:           str
    signing_url:      Optional[str]
    completed_pdf_path: Optional[str]
    sent_at:          Optional[datetime]
    completed_at:     Optional[datetime]
    expires_at:       Optional[datetime]
    created_at:       datetime
    signers:          List[SignerOut]

    class Config:
        from_attributes = True


# ── Provider helpers (stub-based — real OAuth requires external setup) ─────────

from app.services.esign_service import (
    docusign_configured as _docusign_configured,
    adobe_configured as _adobe_configured,
    create_provider_envelope as _create_provider_envelope,
    _get_db_setting,
    _set_db_setting,
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[EnvelopeOut], summary="Listar solicitudes de firma")
def list_envelopes(
    document_id: Optional[int] = Query(None),
    status:      Optional[str] = Query(None),
    limit:       int           = Query(50, le=200),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(50, ge=1, le=200),
    db:          Session       = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    created_by_id = None if current_user.is_superadmin else current_user.id
    items = esign_service.list_envelopes(
        db,
        created_by_id=created_by_id,
        document_id=document_id,
        status=status,
        limit=limit,
    )
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("", response_model=EnvelopeOut, summary="Crear solicitud de firma")
def create_envelope(
    body:         EnvelopeCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    if not body.signers:
        raise HTTPException(400, "Al menos un firmante es obligatorio")

    doc = esign_service.get_document(db, body.document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    # Build a temporary envelope object for provider helper (no db write yet)
    _tmp = ESignEnvelope(
        document_id=body.document_id,
        provider=body.provider,
        subject=body.subject,
        message=body.message,
    )
    # Attach signers to temp envelope so provider can use them
    from app.models.esign import ESignSigner as _ESignSigner  # noqa: PLC0415
    _tmp.signers = [
        _ESignSigner(name=s.name, email=s.email, routing_order=s.routing_order)
        for s in body.signers
    ]
    try:
        provider_result = _create_provider_envelope(_tmp, doc, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return esign_service.create_envelope(
        db,
        document_id=body.document_id,
        created_by_id=current_user.id,
        provider=body.provider,
        subject=body.subject,
        message=body.message,
        expires_days=body.expires_days,
        signers=body.signers,
        provider_result=provider_result,
    )


# ── Static sub-routes (must come BEFORE /{envelope_id} to avoid capture) ─────

# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary/stats", summary="Resumen de firma electrónica")
def esign_stats(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user),
):
    stats = esign_service.get_stats(db)
    # Check DB config override first, then fall back to env vars
    ds_key = _get_esign_setting(db, "esign.docusign_integration_key")
    ds_acc = _get_esign_setting(db, "esign.docusign_account_id")
    ab_key = _get_esign_setting(db, "esign.adobe_sign_client_id")
    docusign_ok = bool(ds_key and ds_acc) or _docusign_configured()
    adobe_ok    = bool(ab_key) or _adobe_configured()
    return {
        **stats,
        "providers": {
            "docusign_configured": docusign_ok,
            "adobe_configured":    adobe_ok,
        },
    }


# ── E-firma provider configuration ───────────────────────────────────────────

class ESignConfigIn(BaseModel):
    docusign_integration_key: Optional[str] = None
    docusign_secret_key:      Optional[str] = None
    docusign_account_id:      Optional[str] = None
    docusign_base_url:        Optional[str] = None
    adobe_sign_client_id:     Optional[str] = None
    adobe_sign_client_secret: Optional[str] = None
    adobe_sign_base_url:      Optional[str] = None


@router.get("/config", summary="Leer configuración de proveedores de firma")
def get_esign_config(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    result = {}
    for key in _ESIGN_KEYS:
        short = key.replace("esign.", "")
        val = _get_esign_setting(db, key)
        if key in _SECRET_KEYS:
            result[short] = "***" if val else ""
        else:
            result[short] = val or ""
    ds_key = _get_esign_setting(db, "esign.docusign_integration_key")
    ds_acc = _get_esign_setting(db, "esign.docusign_account_id")
    ab_key = _get_esign_setting(db, "esign.adobe_sign_client_id")
    result["docusign_configured"] = bool(ds_key and ds_acc) or _docusign_configured()
    result["adobe_configured"]    = bool(ab_key) or _adobe_configured()
    return result


@router.patch("/config", summary="Guardar configuración de proveedores de firma")
def update_esign_config(
    payload: ESignConfigIn,
    db:  Session = Depends(get_db),
    _:   User    = Depends(require_admin),
):
    field_key_map = {
        "docusign_integration_key": "esign.docusign_integration_key",
        "docusign_secret_key":      "esign.docusign_secret_key",
        "docusign_account_id":      "esign.docusign_account_id",
        "docusign_base_url":        "esign.docusign_base_url",
        "adobe_sign_client_id":     "esign.adobe_sign_client_id",
        "adobe_sign_client_secret": "esign.adobe_sign_client_secret",
        "adobe_sign_base_url":      "esign.adobe_sign_base_url",
    }
    data = payload.model_dump(exclude_none=True)
    for field, db_key in field_key_map.items():
        val = data.get(field)
        if val is not None and val != "***":
            _set_esign_setting(db, db_key, val)
    return {"ok": True}


# ── Per-envelope endpoints ────────────────────────────────────────────────────

@router.get("/{envelope_id}", response_model=EnvelopeOut, summary="Detalle de solicitud")
def get_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    env = esign_service.get_envelope(db, envelope_id)
    if not env:
        raise HTTPException(404, "Solicitud no encontrada")
    return env


@router.patch("/{envelope_id}/status", summary="Actualizar estado (manual o desde proveedor)")
def update_status(
    envelope_id: int,
    status:      str,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    try:
        new_status = ESignStatus(status)
    except ValueError:
        raise HTTPException(400, f"Estado inválido: {status}")

    env = esign_service.get_envelope(db, envelope_id)
    if not env:
        raise HTTPException(404)

    env = esign_service.update_envelope_status(db, env, new_status)
    return {"id": envelope_id, "status": env.status}


@router.patch("/{envelope_id}/signers/{signer_id}/signed", summary="Marcar firmante como firmado")
def mark_signer_signed(
    envelope_id: int,
    signer_id:   int,
    db:          Session = Depends(get_db),
    _:           User    = Depends(get_current_user),
):
    signer = esign_service.get_signer(db, signer_id, envelope_id)
    if not signer:
        raise HTTPException(404, "Firmante no encontrado")

    envelope = esign_service.get_envelope(db, envelope_id)
    esign_service.mark_signer_signed(db, signer, envelope)
    return {"signer_id": signer_id, "signed": True}


@router.delete("/{envelope_id}", summary="Anular solicitud de firma")
def void_envelope(
    envelope_id: int,
    db:          Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "esign_envelope", str(envelope_id), action="delete")
    env = esign_service.get_envelope(db, envelope_id)
    if not env:
        raise HTTPException(404)
    if env.status == ESignStatus.completed:
        raise HTTPException(400, "No se puede anular una solicitud ya completada")
    esign_service.void_envelope(db, env)
    return {"id": envelope_id, "status": "voided"}


# ── Provider webhooks (DocuSign Connect / Adobe Sign Webhooks) ────────────────

@router.post("/webhooks/docusign", summary="Webhook de DocuSign Connect")
async def docusign_webhook(
    request: Request,
    db:      Session = Depends(get_db),
):
    """
    DocuSign sends XML connect events. We parse the minimal subset needed
    to update envelope status. Signature validation requires Basic Auth or
    HMAC (DocuSign HMAC-SHA256) configured via DocuSign Connect console.
    """
    import re
    try:
        body = await request.body()
        payload_str = body.decode("utf-8", errors="replace")
    except Exception as e:
        _logger.warning(f"[eSign] DocuSign webhook body read failed: {e}")
        raise HTTPException(400, "Cuerpo del webhook ilegible")

    m_id = re.search(r'<EnvelopeID[^>]*>([^<]+)<', payload_str)
    m_st = re.search(r'<Status[^>]*>([^<]+)<', payload_str)

    if not (m_id and m_st):
        _logger.warning("[eSign] DocuSign webhook missing EnvelopeID/Status")
        raise HTTPException(400, "Payload DocuSign sin EnvelopeID/Status")

    provider_id = m_id.group(1).strip()
    raw_status  = m_st.group(1).strip().lower()
    status_map  = {
        "sent":      ESignStatus.sent.value,
        "delivered": ESignStatus.delivered.value,
        "completed": ESignStatus.completed.value,
        "declined":  ESignStatus.declined.value,
        "voided":    ESignStatus.voided.value,
    }
    new_status = status_map.get(raw_status)
    if not new_status:
        _logger.info(f"[eSign] DocuSign webhook: estado '{raw_status}' ignorado (no mapeado)")
        return {"status": "ignored", "reason": "status_not_mapped"}

    # Audit #C7: webhook is legitimately async (await request.body() for HMAC
    # verification context). DB ops offloaded to threadpool via run_db so they
    # never block the event loop.
    from app.core.async_db import run_db
    try:
        env = await run_db(esign_service.get_envelope_by_provider_id, db, provider_id)
        if not env:
            _logger.warning(f"[eSign] DocuSign webhook: envelope {provider_id} no encontrado")
            raise HTTPException(404, f"Envelope {provider_id} no encontrado")
        await run_db(esign_service.update_envelope_from_webhook, db, env, new_status)
        _logger.info(f"[eSign] DocuSign webhook: envelope {provider_id} → {new_status}")
    # intentional: chained re-raise preserves context
    except HTTPException:
        raise
    except Exception:
        _logger.exception(f"[eSign] DocuSign webhook processing failed for {provider_id}")
        # 500 hace que DocuSign reintente — preferible a 200 OK silencioso.
        raise HTTPException(500, "Error procesando webhook DocuSign")

    return {"status": "ok"}


@router.post("/webhooks/adobe", summary="Webhook de Adobe Sign")
async def adobe_webhook(
    request: Request,
    db:      Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception as e:
        _logger.warning(f"[eSign] Adobe webhook JSON inválido: {e}")
        raise HTTPException(400, "JSON inválido")

    agreement   = payload.get("agreement", {}) if isinstance(payload, dict) else {}
    provider_id = agreement.get("id")
    raw_status  = (agreement.get("status") or "").lower()

    if not provider_id:
        _logger.warning("[eSign] Adobe webhook sin agreement.id")
        raise HTTPException(400, "Payload Adobe sin agreement.id")

    status_map = {
        "out_for_signature": ESignStatus.sent.value,
        "signed":            ESignStatus.completed.value,
        "completed":         ESignStatus.completed.value,
        "declined":          ESignStatus.declined.value,
        "cancelled":         ESignStatus.voided.value,
    }
    new_status = status_map.get(raw_status)
    if not new_status:
        _logger.info(f"[eSign] Adobe webhook: estado '{raw_status}' ignorado (no mapeado)")
        return {"status": "ignored", "reason": "status_not_mapped"}

    # Audit #C7: same pattern as DocuSign webhook above — offload DB to threadpool.
    from app.core.async_db import run_db
    try:
        env = await run_db(esign_service.get_envelope_by_provider_id, db, provider_id)
        if not env:
            _logger.warning(f"[eSign] Adobe webhook: agreement {provider_id} no encontrado")
            raise HTTPException(404, f"Agreement {provider_id} no encontrado")
        await run_db(esign_service.update_envelope_from_webhook, db, env, new_status)
        _logger.info(f"[eSign] Adobe Sign webhook: agreement {provider_id} → {new_status}")
    # intentional: chained re-raise preserves context
    except HTTPException:
        raise
    except Exception:
        _logger.exception(f"[eSign] Adobe webhook processing failed for {provider_id}")
        raise HTTPException(500, "Error procesando webhook Adobe")

    return {"status": "ok"}


# ── OAuth 2.0 flows for DocuSign and Adobe Sign ───────────────────────────────

@router.get("/auth/docusign/authorize", summary="Iniciar OAuth con DocuSign")
def docusign_oauth_authorize(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Return the DocuSign OAuth authorization URL. Admin opens this URL to grant access.
    After consent DocuSign redirects to /esign/auth/docusign/callback with ?code=...
    """
    from app.services.esign_providers import docusign_auth_url  # noqa: PLC0415
    from app.core.config import settings as _s  # noqa: PLC0415

    integration_key = _get_esign_setting(db, "esign.docusign_integration_key") or _s.DOCUSIGN_INTEGRATION_KEY
    if not integration_key:
        raise HTTPException(400, "DocuSign integration_key no configurado. Guárdalo en /esign/config primero.")

    is_demo = (_get_esign_setting(db, "esign.docusign_is_demo") or "true").lower() == "true"
    if not _s.FRONTEND_URL:
        raise HTTPException(500, "FRONTEND_URL no configurado: imposible construir redirect_uri OAuth seguro")
    redirect_uri = f"{_s.FRONTEND_URL}/api/v1/esign/auth/docusign/callback"

    url = docusign_auth_url(integration_key, redirect_uri, is_demo=is_demo)
    return {"authorization_url": url, "redirect_uri": redirect_uri}


@router.get("/auth/docusign/callback", summary="Callback OAuth DocuSign — intercambio de código")
def docusign_oauth_callback(
    code: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Exchange authorization code for DocuSign access + refresh tokens and store them."""
    from app.services.esign_providers import docusign_exchange_code  # noqa: PLC0415
    from app.core.config import settings as _s  # noqa: PLC0415

    integration_key = _get_esign_setting(db, "esign.docusign_integration_key") or _s.DOCUSIGN_INTEGRATION_KEY
    secret_key = _get_esign_setting(db, "esign.docusign_secret_key") or _s.DOCUSIGN_SECRET_KEY
    is_demo = (_get_esign_setting(db, "esign.docusign_is_demo") or "true").lower() == "true"
    if not _s.FRONTEND_URL:
        raise HTTPException(500, "FRONTEND_URL no configurado: imposible construir redirect_uri OAuth seguro")
    redirect_uri = f"{_s.FRONTEND_URL}/api/v1/esign/auth/docusign/callback"

    if not integration_key or not secret_key:
        raise HTTPException(400, "DocuSign integration_key o secret_key no configurados.")

    result = docusign_exchange_code(integration_key, secret_key, code, redirect_uri, is_demo=is_demo)
    if not result["ok"]:
        raise HTTPException(400, f"Error en intercambio de código DocuSign: {result.get('error')}")

    _set_esign_setting(db, "esign.docusign_access_token", result["access_token"])
    if result.get("refresh_token"):
        _set_esign_setting(db, "esign.docusign_refresh_token", result["refresh_token"])

    _logger.info("[eSign] DocuSign OAuth completed; tokens stored")
    return {"ok": True, "message": "DocuSign autorizado correctamente. Tokens almacenados."}


@router.get("/auth/adobe/authorize", summary="Iniciar OAuth con Adobe Sign")
def adobe_oauth_authorize(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Return the Adobe Sign OAuth authorization URL."""
    from app.services.esign_providers import adobe_sign_auth_url  # noqa: PLC0415
    from app.core.config import settings as _s  # noqa: PLC0415

    client_id = _get_esign_setting(db, "esign.adobe_sign_client_id") or _s.ADOBE_SIGN_CLIENT_ID
    if not client_id:
        raise HTTPException(400, "Adobe Sign client_id no configurado. Guárdalo en /esign/config primero.")

    base_url = _get_esign_setting(db, "esign.adobe_sign_base_url") or _s.ADOBE_SIGN_BASE_URL
    if not _s.FRONTEND_URL:
        raise HTTPException(500, "FRONTEND_URL no configurado: imposible construir redirect_uri OAuth seguro")
    redirect_uri = f"{_s.FRONTEND_URL}/api/v1/esign/auth/adobe/callback"

    url = adobe_sign_auth_url(client_id, redirect_uri, base_url=base_url)
    return {"authorization_url": url, "redirect_uri": redirect_uri}


@router.get("/auth/adobe/callback", summary="Callback OAuth Adobe Sign — intercambio de código")
def adobe_oauth_callback(
    code: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Exchange authorization code for Adobe Sign access + refresh tokens and store them."""
    from app.services.esign_providers import adobe_sign_exchange_code  # noqa: PLC0415
    from app.core.config import settings as _s  # noqa: PLC0415

    client_id = _get_esign_setting(db, "esign.adobe_sign_client_id") or _s.ADOBE_SIGN_CLIENT_ID
    client_secret = _get_esign_setting(db, "esign.adobe_sign_client_secret") or _s.ADOBE_SIGN_CLIENT_SECRET
    base_url = _get_esign_setting(db, "esign.adobe_sign_base_url") or _s.ADOBE_SIGN_BASE_URL
    if not _s.FRONTEND_URL:
        raise HTTPException(500, "FRONTEND_URL no configurado: imposible construir redirect_uri OAuth seguro")
    redirect_uri = f"{_s.FRONTEND_URL}/api/v1/esign/auth/adobe/callback"

    if not client_id or not client_secret:
        raise HTTPException(400, "Adobe Sign client_id o client_secret no configurados.")

    result = adobe_sign_exchange_code(client_id, client_secret, code, redirect_uri, base_url=base_url)
    if not result["ok"]:
        raise HTTPException(400, f"Error en intercambio de código Adobe Sign: {result.get('error')}")

    _set_esign_setting(db, "esign.adobe_sign_access_token", result["access_token"])
    if result.get("refresh_token"):
        _set_esign_setting(db, "esign.adobe_sign_refresh_token", result["refresh_token"])
    if result.get("api_access_point"):
        _set_esign_setting(db, "esign.adobe_sign_base_url", result["api_access_point"])

    _logger.info("[eSign] Adobe Sign OAuth completed; tokens stored")
    return {"ok": True, "message": "Adobe Sign autorizado correctamente. Tokens almacenados."}


@router.post("/auth/docusign/store-token", summary="Almacenar token DocuSign manualmente")
def store_docusign_token(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Allow admin to paste an access_token (and optionally refresh_token) obtained externally."""
    access_token = payload.get("access_token", "").strip()
    refresh_token = payload.get("refresh_token", "").strip()
    if not access_token:
        raise HTTPException(400, "access_token requerido")
    _set_esign_setting(db, "esign.docusign_access_token", access_token)
    if refresh_token:
        _set_esign_setting(db, "esign.docusign_refresh_token", refresh_token)
    return {"ok": True, "message": "Token DocuSign almacenado."}


@router.post("/auth/adobe/store-token", summary="Almacenar token Adobe Sign manualmente")
def store_adobe_token(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Allow admin to paste an access_token (and optionally refresh_token) obtained externally."""
    access_token = payload.get("access_token", "").strip()
    refresh_token = payload.get("refresh_token", "").strip()
    if not access_token:
        raise HTTPException(400, "access_token requerido")
    _set_esign_setting(db, "esign.adobe_sign_access_token", access_token)
    if refresh_token:
        _set_esign_setting(db, "esign.adobe_sign_refresh_token", refresh_token)
    return {"ok": True, "message": "Token Adobe Sign almacenado."}
