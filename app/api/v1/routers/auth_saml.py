"""
Auth SAML Router — SAML 2.0 service provider endpoints.

23-11-2026: además de la metadata y la salud, el flujo completo (antes la
metadata anunciaba un ACS y un SLO que no existían). La validación vive en
`app/services/auth_service/saml.py`; aquí solo HTTP, auditoría y redirecciones.

  GET  /saml/metadata             metadata del SP (entity ID, ACS, SLO)
  GET  /saml/health               salud de las configuraciones (org.administrar)
  GET  /saml/{config_id}/login    URL del IdP con la AuthnRequest
  POST /saml/callback             ACS (HTTP-POST desde el IdP) → ticket → /login
  POST /saml/canjear              el frontend canjea el ticket: tokens o MFA
  POST /saml/{config_id}/logout   SLO iniciado aquí: cierra la sesión y da la URL del IdP
  GET  /saml/logout               SLO del IdP (LogoutRequest firmada o LogoutResponse)
"""
import logging
import urllib.parse

from fastapi import APIRouter, Body, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db, sesion_de_sistema
from app.core.config import settings
from app.core.deps import get_current_user, requiere_capacidad
from app.core.network import extract_client_ip
from app.core.ratelimit import limiter
from app.core.codigos_de_error import error_http
from app.models.user import User
from app.services.audit import audit_log
from app.services.transaccion import confirmar
from app.services.auth_service import saml as _saml

import app.services.auth_service as _svc

logger = logging.getLogger(__name__)
router = APIRouter()


class SamlCanjeIn(BaseModel):
    ticket: str = Field(..., min_length=10, max_length=200)


def _frontend(ruta: str, **query) -> str:
    base = (settings.FRONTEND_URL or settings.BASE_URL or "").rstrip("/")
    return f"{base}{ruta}" + ("?" + urllib.parse.urlencode(query) if query else "")


def _config_saml(db: Session, config_id: str):
    config = _svc.get_sso_config_or_404(db, config_id)
    if str(getattr(config.provider, "value", config.provider)) != "saml":
        raise error_http(400, "sso_no_es_saml")
    return config


def _auditar_fallo(db: Session, request: Request, codigo: str, config_id=None) -> None:
    """Login SAML rechazado: queda en audit_log (sin la respuesta del IdP, que trae datos personales)."""
    try:
        audit_log(db, None, "LOGIN_FAILED", "users", None, None,
                  metadata={"metodo": "saml", "motivo": codigo, "sso_config_id": config_id},
                  ip_address=(extract_client_ip(request) or None),
                  user_agent=(request.headers.get("user-agent") or "")[:500] or None)
        confirmar(db)
    except Exception:  # noqa: BLE001 - la auditoría de un fallo no puede tapar el fallo
        db.rollback()
        logger.warning("SAML: no se pudo auditar el rechazo %s", codigo, exc_info=True)


@router.get("/saml/metadata", summary="Metadata SAML del Service Provider")
def saml_metadata():
    """Devuelve la metadata SAML 2.0 del service provider."""
    return Response(content=_saml.metadata_xml(), media_type="application/samlmetadata+xml")


@router.get("/saml/health", summary="Health de configuración SAML")
def saml_health(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    """Health check para configuraciones SAML activas."""
    urls = _saml.urls_sp()
    return {
        "metadata_url": urls["entity_id"],
        "acs_url": urls["acs"],
        "slo_url": urls["slo"],
        "configs": _svc.get_saml_health(db),
    }


@router.get("/saml/{config_id}/login", summary="Iniciar login SAML (AuthnRequest)")
@limiter.limit(settings.SSO_RATE_LIMIT)
def saml_login(request: Request, config_id: str,
               db: Session = Depends(sesion_de_sistema("login: SAML"))):
    config = _config_saml(db, config_id)
    try:
        url = _saml.iniciar_login(config)
    except _saml.ErrorSaml as e:
        raise error_http(400, "saml_rechazado", motivo=e.codigo)
    return {"authorization_url": url, "provider": "saml"}


@router.post("/saml/callback", summary="ACS SAML (HTTP-POST desde el IdP)")
@limiter.limit(settings.SSO_RATE_LIMIT)
def saml_acs(request: Request,
             SAMLResponse: str = Form(..., max_length=_saml.MAX_BYTES * 2),  # noqa: N803 - nombre del binding
             RelayState: str = Form("", max_length=200),  # noqa: N803
             db: Session = Depends(sesion_de_sistema("login: SAML"))):
    """Valida la respuesta del IdP y redirige al login del frontend con un ticket de un solo uso."""
    config_id = None
    try:
        pendiente = _saml.consumir_peticion(RelayState)
        config_id = pendiente["config_id"]
        config = _config_saml(db, config_id)
        identidad = _saml.validar_respuesta(config, SAMLResponse, pendiente["request_id"])
        ticket = _saml.emitir_ticket(identidad)
    except _saml.ErrorSaml as e:
        logger.warning("SAML ACS rechazado (%s): %s", e.codigo, e.detalle)
        _auditar_fallo(db, request, e.codigo, config_id)
        return RedirectResponse(_frontend("/login", saml_error=e.codigo), status_code=303)
    except Exception:  # noqa: BLE001
        logger.error("SAML ACS: error inesperado", exc_info=True)
        _auditar_fallo(db, request, "saml_error_interno", config_id)
        return RedirectResponse(_frontend("/login", saml_error="saml_error_interno"), status_code=303)
    return RedirectResponse(_frontend("/login", saml_ticket=ticket), status_code=303)


@router.post("/saml/canjear", summary="Canjear el ticket SAML por la sesión")
@limiter.limit(settings.SSO_RATE_LIMIT)
def saml_canjear(request: Request, response: Response, payload: SamlCanjeIn = Body(...),
                 db: Session = Depends(sesion_de_sistema("login: SAML"))):
    from app.api.v1.routers.auth_sso import completar_login_federado

    try:
        identidad = _saml.canjear_ticket(payload.ticket)
    except _saml.ErrorSaml as e:
        _auditar_fallo(db, request, e.codigo)
        raise error_http(400, "saml_rechazado", motivo=e.codigo)
    config = _config_saml(db, identidad.config_id)
    return completar_login_federado(db, request, response, config, identidad.email, identidad.nombre,
                                    _saml.claims_de(config, identidad), "saml")


@router.post("/saml/{config_id}/logout", summary="Cerrar sesión SAML (SLO iniciado por el SP)")
def saml_logout_sp(config_id: str, request: Request, response: Response,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Cierra la sesión aquí (como /auth/logout) y devuelve la URL de logout del IdP, si la tiene."""
    from app.api.v1.routers.auth_core import logout as _logout

    config = _config_saml(db, config_id)
    url = _saml.construir_logout_request(config, current_user.email or current_user.username)
    audit_log(db, current_user, "LOGOUT", "users", current_user.id, current_user.full_name,
              metadata={"metodo": "saml", "sso_config_id": config.id, "slo_idp": bool(url)},
              ip_address=(extract_client_ip(request) or None))
    _logout(request=request, response=response, db=db, current_user=current_user)
    return {"logout_url": url}


@router.get("/saml/logout", summary="SLO SAML desde el IdP (HTTP-Redirect)")
def saml_logout_idp(request: Request, db: Session = Depends(sesion_de_sistema("logout: SAML"))):
    """LogoutResponse → vuelta al login. LogoutRequest firmada → cierra las sesiones del usuario."""
    if request.query_params.get("SAMLResponse") and not request.query_params.get("SAMLRequest"):
        return RedirectResponse(_frontend("/login", reason="saml_logout"), status_code=303)
    saml_request = request.query_params.get("SAMLRequest")
    if not saml_request:
        raise error_http(400, "saml_sin_mensaje")
    try:
        config, peticion_id, cerradas = _saml.cerrar_sesiones_del_idp(
            db, request.url.query, saml_request, extract_client_ip(request) or None)
    except _saml.ErrorSaml as e:
        logger.warning("SAML SLO rechazado (%s): %s", e.codigo, e.detalle)
        raise error_http(400, "saml_rechazado", motivo=e.codigo)
    url = _saml.construir_logout_response(config, peticion_id)
    if url:
        return RedirectResponse(url, status_code=303)
    return {"detail": "Sesión cerrada", "sesiones_cerradas": cerradas}
