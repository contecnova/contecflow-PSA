"""
esign_providers.py — Implementaciones reales de DocuSign y Adobe Sign.

Funciones públicas:
  - docusign_create_envelope(...)  → dict con envelope_id, signing_url, status
  - adobe_sign_create_agreement(...) → dict con agreement_id, signing_url, status
  - docusign_get_signing_url(...)  → URL de firma embebida para un firmante
  - docusign_refresh_token(...)    → nuevo access_token via refresh_token
  - adobe_sign_refresh_token(...)  → nuevo access_token via refresh_token
  - docusign_exchange_code(...)    → access+refresh tokens via authorization code
  - adobe_sign_exchange_code(...)  → access+refresh tokens via authorization code
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from app.core.outbound_url import abrir, validate_outbound_url
from typing import Optional

logger = logging.getLogger(__name__)

# ── DocuSign auth base URLs ────────────────────────────────────────────────────
_DS_AUTH_DEMO = "https://account-d.docusign.com"
_DS_AUTH_PROD = "https://account.docusign.com"

# ── Adobe Sign default API base ────────────────────────────────────────────────
_ADOBE_DEFAULT_BASE = "https://api.na1.adobesign.com/api/rest/v6"


# ── Low-level HTTP helper ──────────────────────────────────────────────────────

def _http(method: str, url: str, headers: dict, body=None) -> dict:
    """Execute an HTTP request; return {"ok": True, "data": ...} or {"ok": False, "error": ...}."""
    # Punto único por el que salen todas las llamadas de este módulo: validar aquí
    # cubre DocuSign y Adobe Sign de una vez. `urlopen` aceptaría file:// y ftp://
    # si la URL base de proveedor estuviera mal configurada o manipulada.
    url = validate_outbound_url(url, field="URL de proveedor eSign")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
    try:
        with abrir(req, timeout=20) as resp:  # noqa: S310
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct:
                return {"ok": True, "data": json.loads(raw)}
            return {"ok": True, "data": raw.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:500]
        logger.warning("[esign] HTTP %d from %s: %s", exc.code, url, err_body)
        return {"ok": False, "status_code": exc.code, "error": f"HTTP {exc.code}: {err_body}"}
    except Exception as exc:
        logger.error("[esign] Request error to %s: %s", url, exc)
        return {"ok": False, "error": str(exc)}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── DocuSign OAuth ─────────────────────────────────────────────────────────────

def docusign_auth_url(
    integration_key: str,
    redirect_uri: str,
    *,
    is_demo: bool = True,
    scopes: str = "signature impersonation",
) -> str:
    """Return the OAuth authorization URL for DocuSign."""
    base = _DS_AUTH_DEMO if is_demo else _DS_AUTH_PROD
    params = urllib.parse.urlencode({
        "response_type": "code",
        "scope": scopes,
        "client_id": integration_key,
        "redirect_uri": redirect_uri,
    })
    return f"{base}/oauth/auth?{params}"


def docusign_exchange_code(
    integration_key: str,
    secret_key: str,
    code: str,
    redirect_uri: str,
    *,
    is_demo: bool = True,
) -> dict:
    """Exchange authorization code for access + refresh tokens.

    Returns {"ok": True, "access_token": str, "refresh_token": str, "expires_in": int}
    """
    base = _DS_AUTH_DEMO if is_demo else _DS_AUTH_PROD
    creds = base64.b64encode(f"{integration_key}:{secret_key}".encode()).decode()
    body_str = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    })
    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(f"{base}/oauth/token", field="URL de proveedor eSign"),
        data=body_str.encode(),
        method="POST",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with abrir(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return {
            "ok": True,
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": data.get("expires_in", 3600),
        }
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:300]
        return {"ok": False, "error": f"DocuSign token exchange failed: HTTP {exc.code}: {err}"}
    except Exception as exc:
        logger.warning("Fallo intercambiando código OAuth de DocuSign: %s", exc)
        return {"ok": False, "error": str(exc)}


def docusign_refresh_token(
    integration_key: str,
    secret_key: str,
    refresh_token: str,
    *,
    is_demo: bool = True,
) -> dict:
    """Obtain a new access token using refresh token.

    Returns {"ok": True, "access_token": str, "refresh_token": str}
    """
    base = _DS_AUTH_DEMO if is_demo else _DS_AUTH_PROD
    creds = base64.b64encode(f"{integration_key}:{secret_key}".encode()).decode()
    body_str = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(f"{base}/oauth/token", field="URL de proveedor eSign"),
        data=body_str.encode(),
        method="POST",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with abrir(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return {
            "ok": True,
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in", 3600),
        }
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:200]
        return {"ok": False, "error": f"DocuSign refresh failed: HTTP {exc.code}: {err}"}
    except Exception as exc:
        logger.warning("Fallo refrescando token de DocuSign: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── DocuSign envelope creation ─────────────────────────────────────────────────

def docusign_create_envelope(
    access_token: str,
    account_id: str,
    base_url: str,
    *,
    subject: str,
    message: Optional[str],
    signers: list,
    doc_name: str,
    doc_content: bytes,
    doc_extension: str = "pdf",
    send_immediately: bool = True,
) -> dict:
    """Create a DocuSign envelope and return its ID and status.

    signers: list of dicts with {name, email, routing_order}
    Returns {"ok": True, "envelope_id": str, "status": str, "uri": str}
    """
    api_base = base_url.rstrip("/")
    if not api_base.endswith("/restapi"):
        if "/restapi" not in api_base:
            api_base = f"{api_base}/restapi"

    doc_b64 = _b64(doc_content)
    env_status = "sent" if send_immediately else "created"

    # Build recipients list
    ds_signers = []
    for i, s in enumerate(signers):
        ds_signers.append({
            "recipientId": str(i + 1),
            "name": s.get("name", ""),
            "email": s.get("email", ""),
            "routingOrder": str(s.get("routing_order", i + 1)),
            "tabs": {
                "signHereTabs": [{
                    "documentId": "1",
                    "pageNumber": "1",
                    "xPosition": "100",
                    "yPosition": "650",
                    "anchorIgnoreIfNotPresent": "true",
                }]
            },
        })

    envelope_def = {
        "emailSubject": subject[:255],
        "emailBlurb": (message or "")[:1000],
        "documents": [{
            "documentBase64": doc_b64,
            "name": doc_name[:200],
            "fileExtension": doc_extension.lstrip(".").lower(),
            "documentId": "1",
        }],
        "recipients": {"signers": ds_signers},
        "status": env_status,
    }

    url = f"{api_base}/v2.1/accounts/{account_id}/envelopes"
    result = _http("POST", url, {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, envelope_def)

    if not result["ok"]:
        return result

    data = result["data"]
    if isinstance(data, str):
        return {"ok": False, "error": "Unexpected non-JSON response from DocuSign"}

    envelope_id = data.get("envelopeId")
    status = data.get("status", "sent")
    uri = data.get("uri", "")

    if not envelope_id:
        return {"ok": False, "error": f"DocuSign did not return envelopeId. Response: {str(data)[:300]}"}

    return {"ok": True, "envelope_id": envelope_id, "status": status, "uri": uri}


def docusign_get_signing_url(
    access_token: str,
    account_id: str,
    base_url: str,
    envelope_id: str,
    signer_email: str,
    signer_name: str,
    recipient_id: str,
    return_url: str,
) -> dict:
    """Get an embedded signing URL for a specific signer (for in-app signing experience).

    Returns {"ok": True, "url": str}
    """
    api_base = base_url.rstrip("/")
    if "/restapi" not in api_base:
        api_base = f"{api_base}/restapi"

    body = {
        "authenticationMethod": "None",
        "email": signer_email,
        "returnUrl": return_url,
        "userName": signer_name,
        "recipientId": recipient_id,
        "clientUserId": recipient_id,
    }
    url = f"{api_base}/v2.1/accounts/{account_id}/envelopes/{envelope_id}/views/recipient"
    result = _http("POST", url, {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }, body)

    if not result["ok"]:
        return result
    signing_url = result["data"].get("url")
    return {"ok": True, "url": signing_url}


# ── Adobe Sign OAuth ───────────────────────────────────────────────────────────

def adobe_sign_auth_url(
    client_id: str,
    redirect_uri: str,
    base_url: Optional[str] = None,
    scopes: str = "agreement_write:self user_read:self agreement_read:self",
) -> str:
    """Return the OAuth authorization URL for Adobe Sign."""
    base = (base_url or _ADOBE_DEFAULT_BASE).rstrip("/").replace("/api/rest/v6", "")
    params = urllib.parse.urlencode({
        "response_type": "code",
        "scope": scopes,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    })
    return f"{base}/public/oauth/v2?{params}"


def adobe_sign_exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    base_url: Optional[str] = None,
) -> dict:
    """Exchange authorization code for access + refresh tokens.

    Returns {"ok": True, "access_token": str, "refresh_token": str, "api_access_point": str}
    """
    base = (base_url or _ADOBE_DEFAULT_BASE).rstrip("/").replace("/api/rest/v6", "")
    body_str = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    })
    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(f"{base}/oauth/v2/token", field="URL de proveedor eSign"),
        data=body_str.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with abrir(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return {
            "ok": True,
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": data.get("expires_in", 3600),
            "api_access_point": data.get("api_access_point", base_url or _ADOBE_DEFAULT_BASE),
        }
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:300]
        return {"ok": False, "error": f"Adobe Sign token exchange failed: HTTP {exc.code}: {err}"}
    except Exception as exc:
        logger.warning("Fallo intercambiando código OAuth de Adobe Sign: %s", exc)
        return {"ok": False, "error": str(exc)}


def adobe_sign_refresh_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    base_url: Optional[str] = None,
) -> dict:
    """Obtain a new access token using refresh token.

    Returns {"ok": True, "access_token": str}
    """
    base = (base_url or _ADOBE_DEFAULT_BASE).rstrip("/").replace("/api/rest/v6", "")
    body_str = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(f"{base}/oauth/v2/token", field="URL de proveedor eSign"),
        data=body_str.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with abrir(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return {
            "ok": True,
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", refresh_token),
        }
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:200]
        return {"ok": False, "error": f"Adobe Sign refresh failed: HTTP {exc.code}: {err}"}
    except Exception as exc:
        logger.warning("Fallo refrescando token de Adobe Sign: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Adobe Sign agreement creation ──────────────────────────────────────────────

def adobe_sign_upload_document(
    access_token: str,
    base_url: str,
    doc_name: str,
    doc_content: bytes,
    mime_type: str = "application/pdf",
) -> dict:
    """Upload a document as transient document and return transientDocumentId.

    Returns {"ok": True, "transient_document_id": str}
    """
    api_base = base_url.rstrip("/")
    url = f"{api_base}/transientDocuments"

    boundary = "----ContecFlowBoundary7a8b9c"
    lines = [
        f"--{boundary}",
        f'Content-Disposition: form-data; name="File"; filename="{doc_name}"',
        f"Content-Type: {mime_type}",
        "",
    ]
    header_part = "\r\n".join(lines).encode()
    footer = f"\r\n--{boundary}--".encode()
    body = b"\r\n" + header_part + b"\r\n" + doc_content + footer

    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(url, field="URL de proveedor eSign"), data=body, method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with abrir(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read())
        tdoc_id = data.get("transientDocumentId")
        if not tdoc_id:
            return {"ok": False, "error": "Adobe Sign did not return transientDocumentId"}
        return {"ok": True, "transient_document_id": tdoc_id}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:300]
        return {"ok": False, "error": f"Adobe Sign document upload failed: HTTP {exc.code}: {err}"}
    except Exception as exc:
        logger.warning("Fallo subiendo documento a Adobe Sign: %s", exc)
        return {"ok": False, "error": str(exc)}


def adobe_sign_get_agreement_status(access_token: str, base_url: str, agreement_id: str) -> dict:
    """Estado actual de un acuerdo, leido de la API de Adobe Sign.

    Returns {"ok": True, "status": str} o {"ok": False, "error": ...}.
    """
    from urllib.parse import quote

    result = _http("GET", f"{base_url.rstrip('/')}/agreements/{quote(agreement_id, safe='')}", {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    if not result["ok"]:
        return result
    data = result["data"]
    if not isinstance(data, dict) or not data.get("status"):
        return {"ok": False, "error": "Respuesta de Adobe Sign sin estado"}
    return {"ok": True, "status": str(data["status"])}


def adobe_sign_create_agreement(
    access_token: str,
    base_url: str,
    *,
    subject: str,
    message: Optional[str],
    signers: list,
    doc_name: str,
    doc_content: bytes,
    doc_extension: str = "pdf",
) -> dict:
    """Upload document + create Adobe Sign agreement.

    signers: list of dicts with {name, email, routing_order}
    Returns {"ok": True, "agreement_id": str, "status": str}
    """
    api_base = base_url.rstrip("/")

    # Step 1: upload document
    mime = "application/pdf" if doc_extension.lower() in ("pdf",) else "application/octet-stream"
    upload_result = adobe_sign_upload_document(access_token, api_base, doc_name, doc_content, mime)
    if not upload_result["ok"]:
        return upload_result
    tdoc_id = upload_result["transient_document_id"]

    # Step 2: group signers by routing order
    participant_sets = []
    for s in signers:
        participant_sets.append({
            "memberInfos": [{"email": s.get("email", ""), "name": s.get("name", "")}],
            "order": s.get("routing_order", 1),
            "role": "SIGNER",
        })

    agreement_body = {
        "fileInfos": [{"transientDocumentId": tdoc_id}],
        "name": subject[:255],
        "message": (message or "")[:1000],
        "participantSetsInfo": participant_sets,
        "signatureType": "ESIGN",
        "state": "IN_PROCESS",
    }

    result = _http("POST", f"{api_base}/agreements", {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, agreement_body)

    if not result["ok"]:
        return result

    data = result["data"]
    if isinstance(data, str):
        return {"ok": False, "error": "Unexpected non-JSON response from Adobe Sign"}

    agreement_id = data.get("id")
    if not agreement_id:
        return {"ok": False, "error": f"Adobe Sign did not return agreement id. Response: {str(data)[:300]}"}

    return {"ok": True, "agreement_id": agreement_id, "status": "sent"}
