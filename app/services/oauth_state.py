"""`state` de OAuth firmado, de un solo uso y ligado a la organizacion y al usuario.

Auditoria 2026-11 (#26). Dos flujos OAuth no protegian el `state`:

- DocuSign y Adobe Sign no mandaban `state`: el callback aceptaba cualquier
  `code`, asi que un atacante podia hacer que un administrador guardase los
  tokens de la cuenta de eSign DEL ATACANTE (los contratos de la empresa se
  firmarian en su cuenta) con un enlace al callback.
- Las integraciones de colaboracion guardaban un `state` aleatorio en memoria
  de proceso, sin atarlo a nadie: el enlace de autorizacion de una integracion
  del atacante, abierto por la victima, guardaba los tokens de la victima en la
  integracion del atacante. Y en memoria no sobrevivia a varios workers.

Es el mismo mecanismo que el SSO OIDC (`routers/auth_sso.py`): `state` =
`aleatorio.HMAC(SECRET_KEY)`, y lo ligado al flujo se guarda en el almacen de
estados de un solo uso (Redis con respaldo en memoria). Aqui se anade el
proposito al HMAC (un `state` de eSign no vale para colaboracion) y se guardan
el usuario y la organizacion que lo pidieron.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from app.core.config import settings
from app.core.errores import ErrorDeDominio


def _firma(proposito: str, crudo: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{proposito}:{crudo}".encode(), hashlib.sha256).hexdigest()


def _clave(proposito: str, crudo: str) -> str:
    return f"oauth:{proposito}:{crudo}"


def huella(valor: str) -> str:
    return hashlib.sha256((valor or "").encode()).hexdigest()


def emitir(proposito: str, *, user_id: Optional[str], org_id: Optional[str], **datos) -> str:
    """Un `state` nuevo para `proposito`, con `datos` guardados para el callback."""
    from app.services.auth_service.estado_efimero import register_sso_state

    crudo = secrets.token_urlsafe(32)
    register_sso_state(_clave(proposito, crudo), {**datos, "user_id": user_id, "org_id": org_id})
    return f"{crudo}.{_firma(proposito, crudo)}"


def consumir(proposito: str, state: Optional[str], *, user_id: Optional[str] = None,
             org_id: Optional[str] = None) -> dict:
    """Valida la firma, consume el estado (un solo uso) y devuelve sus datos.

    Si se pasan `user_id`/`org_id`, tienen que ser los mismos que lo emitieron.
    Cualquier fallo es un 400 sin detalle de cual.
    """
    from app.services.auth_service.estado_efimero import consume_sso_state_payload

    if not state or "." not in state:
        raise ErrorDeDominio(400, "state OAuth ausente o inválido")
    crudo, firma = state.rsplit(".", 1)
    if not hmac.compare_digest(_firma(proposito, crudo), firma):
        raise ErrorDeDominio(400, "state OAuth ausente o inválido")
    datos = consume_sso_state_payload(_clave(proposito, crudo))
    if datos is None:
        raise ErrorDeDominio(400, "state OAuth caducado o ya utilizado")
    if user_id is not None and datos.get("user_id") != user_id:
        raise ErrorDeDominio(400, "state OAuth de otro usuario")
    if org_id is not None and datos.get("org_id") != org_id:
        raise ErrorDeDominio(400, "state OAuth de otra organización")
    return datos
