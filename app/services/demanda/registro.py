"""Piezas del expediente de demanda que comparten `motor` y `ejecucion` (23-11-2026).

Vivían en `motor`; `ejecucion` las importaba de ahí y `motor` importaba
`ejecucion` dentro de una función (al cerrar), un ciclo escondido
(tests/test_auditoria_2026_11_arquitectura_c4.py). Aquí no dependen de ninguno
de los dos; `motor` las reexporta con el mismo nombre.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def jload(texto, defecto):
    try:
        v = json.loads(texto) if texto else defecto
    except (TypeError, ValueError):
        return defecto
    return v if v is not None else defecto


def flujo_de(req) -> dict:
    return D.cargar(req.flow_snapshot)


def datos_de(req) -> dict:
    return jload(req.data, {})


# ── Log inmutable ────────────────────────────────────────────────────────────

def _hash(previo: Optional[str], fila: dict) -> str:
    base = json.dumps(fila, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(((previo or "") + base).encode("utf-8")).hexdigest()


def registrar(db: Session, req, actor: Actor, decision: str, *, desde: Optional[str] = None,
              hacia: Optional[str] = None, paso: Optional[str] = None, justificacion: Optional[str] = None,
              estado_previo: Optional[str] = None, bypass: bool = False, datos: Optional[dict] = None):
    """Añade una transición al log del expediente (y al registro de auditoría)."""
    from app.models.demanda import DemandTransition
    from app.services.audit import audit_log
    # M92 (auditoría 22-11-2026): el expediente se bloquea hasta el commit antes
    # de leer la última transición: dos decisiones a la vez ya no encadenan las
    # dos sobre el mismo `prev_hash` (cadena bifurcada).
    from app.db.session import is_postgres
    if is_postgres():
        db.refresh(req, with_for_update=True)
    ultima = db.query(DemandTransition).filter(DemandTransition.request_id == req.id) \
        .order_by(DemandTransition.seq.desc()).first()
    seq = (ultima.seq + 1) if ultima else 1
    momento = ahora()
    fila = {"request_id": req.id, "seq": seq, "from_phase": desde, "to_phase": hacia, "step_key": paso,
            "decision": decision, "from_status": estado_previo, "to_status": req.status,
            "actor_user_id": actor.id if actor.kind == "user" else None,
            "actor_client_id": actor.id if actor.kind == "client" else None,
            "actor_role": actor.rol, "justification": justificacion, "is_bypass": bypass,
            "at": momento.isoformat()}
    t = DemandTransition(organization_id=req.organization_id, request_id=req.id, seq=seq, from_phase=desde,
                         to_phase=hacia, step_key=paso, decision=decision, from_status=estado_previo,
                         to_status=req.status, actor_user_id=fila["actor_user_id"],
                         actor_client_id=fila["actor_client_id"], actor_name=actor.nombre[:255] or None,
                         actor_role=actor.rol, justification=justificacion, is_bypass=bypass,
                         payload=json.dumps(datos, ensure_ascii=False, default=str) if datos else None,
                         prev_hash=ultima.hash if ultima else None, created_at=momento)
    t.hash = _hash(t.prev_hash, fila)
    db.add(t)
    audit_log(db, actor.user if actor.kind == "user" else None, f"DEMAND_{decision.upper()}", "demand_request",
              req.id, req.code, new_values={"phase": hacia or desde, "status": req.status, "step": paso},
              metadata={"justification": justificacion, "bypass": bypass, "actor_kind": actor.kind,
                        "client_user_id": actor.id if actor.kind == "client" else None})
    return t
