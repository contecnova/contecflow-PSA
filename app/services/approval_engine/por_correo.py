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

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing_reports import ApprovalRequest
from app.models.user import User
from app.core.errores import ErrorDeDominio

_TIPO = "approval_email"


def _horas(db: Session) -> int:
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "APPROVAL_EMAIL_LINK_HOURS", db.info.get("organization_id")) or settings.APPROVAL_EMAIL_LINK_HOURS)


def crear_enlace(db: Session, req, user_id: str) -> str:
    from jose import jwt
    from app.core.security import ALGORITHM, get_jwt_signing_key
    kid, key = get_jwt_signing_key()
    token = jwt.encode({"type": _TIPO, "sub": user_id, "req": req.id, "step": req.current_step,
                        "exp": datetime.now(timezone.utc) + timedelta(hours=_horas(db))},
                       key, algorithm=ALGORITHM, headers={"kid": kid})
    return f"{settings.FRONTEND_URL.rstrip('/')}/approvals/decide?token={token}"


def _leer(db: Session, token: str):
    """(solicitud, usuario) del enlace, o 410/404 si ya no vale."""
    from app.core.security import decode_token
    from app.db.session import publicar_contexto_de_tenant, sin_filtro_de_tenant
    datos = decode_token(token or "")
    if not datos or datos.get("type") != _TIPO:
        raise ErrorDeDominio(410, "El enlace ha caducado o no es válido: decide desde la bandeja de aprobaciones")
    with sin_filtro_de_tenant(db):
        usuario = db.get(User, datos["sub"])
        req = db.get(ApprovalRequest, datos["req"])
    if usuario is None or not usuario.is_active:
        raise ErrorDeDominio(410, "El enlace ya no es válido")
    if req is None:
        raise ErrorDeDominio(404, "Solicitud no encontrada")
    # La sesión es la del aprobador en la empresa de la solicitud (puede ser
    # suya por pertenencia, no por su ficha). Si ya no pertenece, no vale.
    from app.services.entrada_service import pertenece
    if not usuario.is_superadmin and req.organization_id and not pertenece(db, usuario, req.organization_id):
        raise ErrorDeDominio(410, "El enlace ya no es válido")
    # Segunda auditoría 2026-11 (#10): la empresa de la SOLICITUD desactivada → 403
    # (antes solo se miraba la de ficha del aprobador).
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, req.organization_id)
    publicar_contexto_de_tenant(db, usuario)
    if req.organization_id and not usuario.is_superadmin:
        from sqlalchemy.orm.attributes import set_committed_value
        db.info["organization_id"] = req.organization_id
        set_committed_value(usuario, "organization_id", req.organization_id)
    if req.status != "pending" or req.current_step != datos.get("step"):
        raise ErrorDeDominio(410, "Esta solicitud ya se decidió o cambió de paso")
    return req, usuario


def resumen(db: Session, token: str) -> dict:
    req, usuario = _leer(db, token)
    return {"request_id": req.id, "entity_type": req.entity_type, "summary": req.entity_summary,
            "step": req.current_step, "approver": usuario.full_name or usuario.email}


def decidir(db: Session, token: str, decision: str, nota) -> dict:
    from app.services.approval_engine.requests import decide_approval_request
    if decision not in ("approved", "rejected"):
        raise ErrorDeDominio(422, "Decisión no válida")
    if decision == "rejected" and not (nota or "").strip():
        raise ErrorDeDominio(422, "Para rechazar indica el motivo")
    req, usuario = _leer(db, token)
    req = decide_approval_request(req.id, decision, nota, None, db, usuario)
    return {"request_id": req.id, "status": req.status}
