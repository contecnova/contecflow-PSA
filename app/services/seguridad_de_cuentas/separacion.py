"""Separación de funciones en seguridad (`SECURITY_SOD_TWO_ADMINS`).

Con la regla encendida, un cambio de política o un restablecimiento de MFA no se
aplica: queda como solicitud que aplica OTRO administrador. Nadie aprueba la
suya, ni restablece su propio MFA. La regla también protege su propio apagado:
apagarla es un cambio de política y necesita al segundo administrador.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.codigos_de_error import error

#: Una solicitud sin decidir caduca a los 7 días.
CADUCIDAD_DIAS = 7


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def exige_segundo(db, org_id: str) -> bool:
    from app.services.seguridad_de_cuentas.politica import leer
    return bool(leer(db, org_id).SECURITY_SOD_TWO_ADMINS)


def pedir(db, org_id: str, actor, tipo: str, payload: dict, objetivo_id: Optional[str] = None,
          motivo: Optional[str] = None):
    from app.models.seguridad_de_cuentas import SecurityChangeRequest
    from app.services.seguridad_de_cuentas import alertas
    s = SecurityChangeRequest(organization_id=org_id, kind=tipo, target_user_id=objetivo_id,
                              payload=json.dumps(payload, default=str), reason=(motivo or None),
                              requested_by=actor.id, status="pending")
    db.add(s)
    db.flush()
    alertas.a_los_admins(db, org_id, "seguridad.alerta.solicitud", actor=actor.email or actor.full_name)
    return s


def _caducar(db, org_id: str) -> None:
    from app.models.seguridad_de_cuentas import SecurityChangeRequest
    limite = _ahora() - timedelta(days=CADUCIDAD_DIAS)
    for s in db.query(SecurityChangeRequest).filter(SecurityChangeRequest.organization_id == org_id,
                                                    SecurityChangeRequest.status == "pending",
                                                    SecurityChangeRequest.requested_at < limite).all():
        s.status = "expired"


def listar(db, org_id: str) -> list[dict]:
    from app.models.seguridad_de_cuentas import SecurityChangeRequest
    from app.models.user import User
    _caducar(db, org_id)
    filas = (db.query(SecurityChangeRequest).filter(SecurityChangeRequest.organization_id == org_id)
             .order_by(SecurityChangeRequest.requested_at.desc()).limit(200).all())
    nombres = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(
        {x for f in filas for x in (f.requested_by, f.decided_by, f.target_user_id) if x} or {""}))}
    return [{"id": f.id, "kind": f.kind, "status": f.status, "payload": json.loads(f.payload or "{}"),
             "reason": f.reason, "target_user_id": f.target_user_id, "target_user": nombres.get(f.target_user_id),
             "requested_by": f.requested_by, "requested_by_name": nombres.get(f.requested_by),
             "requested_at": f.requested_at, "decided_by_name": nombres.get(f.decided_by),
             "decided_at": f.decided_at, "decision_comment": f.decision_comment} for f in filas]


def decidir(db, org_id: str, solicitud_id: str, actor, aprobar: bool, comentario: Optional[str] = None):
    """Marca la solicitud (no aplica: lo hace el endpoint con el servicio que toque)."""
    from app.models.seguridad_de_cuentas import SecurityChangeRequest
    _caducar(db, org_id)
    s = db.query(SecurityChangeRequest).filter(SecurityChangeRequest.id == solicitud_id,
                                               SecurityChangeRequest.organization_id == org_id).first()
    if s is None:
        raise error(404, "no_encontrado", que="solicitud")
    if s.status != "pending":
        raise error(409, "solicitud_ya_decidida")
    if s.requested_by == actor.id:
        raise error(403, "separacion_de_funciones_misma_persona")
    if aprobar and s.kind == "mfa_reset" and s.target_user_id == actor.id:
        raise error(403, "separacion_de_funciones_misma_persona")
    s.status = "applied" if aprobar else "rejected"
    s.decided_by, s.decided_at = actor.id, _ahora()
    s.decision_comment = (comentario or None)
    return s, json.loads(s.payload or "{}")
