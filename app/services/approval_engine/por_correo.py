"""Aprobar o rechazar desde el correo (revisión 2026-11).

El aviso al aprobador lleva un enlace firmado, solo para él y para ESE paso, con
caducidad (`APPROVAL_EMAIL_LINK_HOURS`). El enlace abre una página sin login con
el resumen y los botones: decidir es un POST, nunca el GET del enlace, porque
los gestores de correo abren los enlaces solos para analizarlos.

La decisión pasa por el mismo camino que la bandeja (`decide_approval_request`):
autorización del paso, segregación de funciones, voto doble, quórum. Si el paso
ya cambió o la solicitud ya no está pendiente, el enlace deja de valer.
"""
from __future__ import annotations
import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing_reports import ApprovalRequest
from app.models.user import User
from app.core.codigos_de_error import error

_TIPO = "approval_email"


def _horas(db: Session) -> int:
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "APPROVAL_EMAIL_LINK_HOURS", db.info.get("organization_id")) or settings.APPROVAL_EMAIL_LINK_HOURS)


def crear_enlace(db: Session, req, user_id: str) -> str:
    import jwt
    from app.core.security import ALGORITHM, get_jwt_signing_key
    import uuid
    kid, key = get_jwt_signing_key()
    # M54 (auditoría 22-11-2026): `jti` de un solo uso (ver `_consumir`).
    token = jwt.encode({"type": _TIPO, "sub": user_id, "req": req.id, "step": req.current_step,
                        "jti": uuid.uuid4().hex,
                        "exp": datetime.now(timezone.utc) + timedelta(hours=_horas(db))},
                       key, algorithm=ALGORITHM, headers={"kid": kid})
    return f"{settings.FRONTEND_URL.rstrip('/')}/approvals/decide?token={token}"


def _leer(db: Session, token: str):
    """(solicitud, usuario) del enlace, o 410/404 si ya no vale."""
    from app.core.security import decode_token
    from app.db.session import publicar_contexto_de_tenant, sin_filtro_de_tenant
    datos = decode_token(token or "")
    if not datos or datos.get("type") != _TIPO:
        raise error(410, "aprobacion_enlace_caducado")
    with sin_filtro_de_tenant(db):
        usuario = db.get(User, datos["sub"])
        req = db.get(ApprovalRequest, datos["req"])
    if usuario is None or not usuario.is_active:
        raise error(410, "enlace_ya_no_valido")
    if req is None:
        raise error(404, "no_encontrado", detail="Solicitud no encontrada", que="solicitud")
    # La sesión es la del aprobador en la empresa de la solicitud (puede ser
    # suya por pertenencia, no por su ficha). Si ya no pertenece, no vale.
    from app.services.entrada_service import pertenece
    if not usuario.is_superadmin and req.organization_id and not pertenece(db, usuario, req.organization_id):
        raise error(410, "enlace_ya_no_valido")
    # Segunda auditoría 2026-11 (#10): la empresa de la SOLICITUD desactivada → 403
    # (antes solo se miraba la de ficha del aprobador).
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, req.organization_id)
    publicar_contexto_de_tenant(db, usuario)
    if req.organization_id:
        # 24-11-2026 (migración 208): también con un superadmin aprobador (antes
        # su sesión quedaba en su empresa de ficha, o en ninguna, y el rastro de
        # la decisión no tenía de dónde sacar la empresa). Su ficha no se toca.
        db.info["organization_id"] = req.organization_id
    if req.organization_id and not usuario.is_superadmin:
        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(usuario, "organization_id", req.organization_id)
    if req.status != "pending" or req.current_step != datos.get("step"):
        raise error(410, "aprobacion_ya_decidida_o_cambio_paso")
    if _usado(datos.get("jti")):
        raise error(410, "enlace_ya_no_valido")
    return req, usuario


#: M54: enlaces ya usados (jti → caducidad). Con Redis, compartido entre
#: procesos; si no, en memoria. Un enlace de aprobación sirve UNA vez: si se
#: reenvía el correo después de decidir, ya no vale (antes valía hasta caducar).
_USADOS: dict = {}


def _clave(jti: str) -> str:
    return f"approval_email:used:{jti}"


def _usado(jti) -> bool:
    if not jti:
        return False
    from app.services.auth_service.estado_efimero import get_sso_redis
    r = get_sso_redis()
    if r is not None:
        try:
            return bool(r.exists(_clave(jti)))
        except Exception:
            logging.getLogger(__name__).debug("_usado: excepcion ignorada", exc_info=True)
    import time
    exp = _USADOS.get(jti)
    return bool(exp and exp > time.time())


def _consumir(jti, segundos: int) -> None:
    if not jti:
        return
    from app.services.auth_service.estado_efimero import get_sso_redis
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(_clave(jti), max(int(segundos), 1), "1")
            return
        except Exception:
            logging.getLogger(__name__).debug("_consumir: excepcion ignorada", exc_info=True)
    import time
    ahora = time.time()
    for k in [k for k, v in _USADOS.items() if v <= ahora]:
        _USADOS.pop(k, None)
    _USADOS[jti] = ahora + segundos


def resumen(db: Session, token: str) -> dict:
    req, usuario = _leer(db, token)
    return {"request_id": req.id, "entity_type": req.entity_type, "summary": req.entity_summary,
            "step": req.current_step, "approver": usuario.full_name or usuario.email}


def decidir(db: Session, token: str, decision: str, nota) -> dict:
    from app.services.approval_engine.requests import decide_approval_request
    if decision not in ("approved", "rejected"):
        raise error(422, "decision_no_valida")
    if decision == "rejected" and not (nota or "").strip():
        raise error(422, "motivo_de_rechazo_obligatorio", detail="Para rechazar indica el motivo")
    req, usuario = _leer(db, token)
    req = decide_approval_request(req.id, decision, nota, None, db, usuario)
    from app.core.security import decode_token
    _consumir((decode_token(token or "") or {}).get("jti"), _horas(db) * 3600)
    return {"request_id": req.id, "status": req.status}
