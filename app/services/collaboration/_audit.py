"""Append-only audit log with chained integrity hash (per-org).

Each row hashes: prev_hash + payload_canonical_json.
A tampered row breaks the chain — verifiable by the eDiscovery exporter.
Desde la migración 201 cada fila nueva lleva además `hmac` + `key_id` (llavero).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


#: Versión del hash de las filas nuevas (migración 196, 23-11-2026, C5).
#: - "v1": sha256(anterior|acción|tipo|id|payload), sin clave ni actor (filas
#:   antiguas: se siguen verificando así para no romper la cadena existente);
#: - "v2": HMAC-SHA256 con la clave del despliegue y además actor (usuario o
#:   cliente), IP y fecha (UTC, al segundo). Sin la clave no se recalcula.
HASH_VERSION = "v2"


def _fecha_canonica(valor) -> str:
    """UTC al segundo, sin zona: igual en SQLite (devuelve sin zona) y Postgres."""
    from datetime import timezone
    if valor is None:
        return ""
    if valor.tzinfo is not None:
        valor = valor.astimezone(timezone.utc).replace(tzinfo=None)
    return valor.replace(microsecond=0).isoformat()


def _huella(version: str, prev_hash: str, fila) -> str:
    base = f"{prev_hash}|{fila.action}|{fila.entity_type}|{fila.entity_id or ''}|{_canonical(fila.payload or {})}"
    if version != "v2":
        return hashlib.sha256(base.encode()).hexdigest()
    import hmac
    from app.core.config import settings
    clave = (getattr(settings, "SECRET_KEY", "") or "").encode()
    datos = "|".join([base, fila.actor_user_id or "", fila.actor_client_id or "", fila.ip_address or "",
                      _fecha_canonica(fila.created_at)])
    return hmac.new(clave, datos.encode(), hashlib.sha256).hexdigest()


# ── HMAC con el llavero (migración 201, 23-11-2026, C5) ──────────────────────
# Además de la huella encadenada, cada fila nueva lleva `hmac` (HMAC-SHA256 de
# id, empresa, anterior y huella) con la clave ACTIVA del llavero de
# `app/services/key_management.py` y su `kid` en `key_id`. La clave se deriva
# del material del llavero con una etiqueta propia (no se reutiliza tal cual la
# de firmar JWT). Verificar usa la clave de ese `kid`: rotar no rompe nada
# mientras el llavero la conserve; si ya se podó (`JWT_KEY_RETENTION_COUNT`), la
# fila se informa como «sin clave», no como rotura. Las filas anteriores a la
# 201 (`hmac` NULL) se verifican solo por `integrity_hash`, como antes.
_ETIQUETA_HMAC = b"contecflow:collaboration_audit_chain:v1"


def _derivar(material: str) -> bytes:
    import hmac
    return hmac.new(material.encode(), _ETIQUETA_HMAC, hashlib.sha256).digest()


def _mensaje_hmac(fila) -> bytes:
    return "|".join([fila.id or "", fila.organization_id or "", fila.prev_event_id or "",
                     fila.integrity_hash or ""]).encode()


def _firmar(fila) -> None:
    """Pone `hmac` y `key_id` con la clave activa; sin llavero, los deja NULL."""
    import hmac
    try:
        from app.services.key_management import get_jwt_signing_key
        kid, material = get_jwt_signing_key()
    except Exception:
        logger.warning("cadena de colaboración: llavero no disponible; fila sin HMAC", exc_info=True)
        return
    fila.key_id = kid
    fila.hmac = hmac.new(_derivar(material), _mensaje_hmac(fila), hashlib.sha256).hexdigest()


def _comprobar_hmac(fila, claves: dict) -> Optional[str]:
    """None si cuadra; "sin_clave" o "hmac" si no. Filas sin HMAC: None."""
    import hmac
    if not getattr(fila, "hmac", None):
        return None
    material = claves.get(fila.key_id or "")
    if not material:
        return "sin_clave"
    esperado = hmac.new(_derivar(material), _mensaje_hmac(fila), hashlib.sha256).hexdigest()
    return None if hmac.compare_digest(esperado, fila.hmac) else "hmac"


# Auditoría 22-11-2026 (C5). El lock anterior (threading.Lock por proceso) se
# soltaba al volver de `write`, ANTES del commit del llamador: dos peticiones
# leían el mismo `prev` y la cadena se bifurcaba (`verify_chain` daba roturas
# falsas). Ahora el bloqueo dura hasta el fin de la TRANSACCIÓN:
#
# - PostgreSQL: `pg_advisory_xact_lock` por empresa (vale entre procesos y
#   workers; lo suelta la base al confirmar o deshacer);
# - otros motores (SQLite en desarrollo y tests): un semáforo por empresa que se
#   suelta al terminar la transacción exterior (`after_transaction_end`).
#
# Y el anterior es la COLA de la cadena (el evento al que nadie apunta), no el
# de `created_at` más reciente: dentro de una transacción `now()` es el mismo
# para todos y el desempate por id (uuid) elegía uno al azar.
_org_locks: dict[str, threading.Semaphore] = {}
_locks_meta_lock = threading.Lock()
_CLAVE_SESION = "collab_audit_locks"
_ESPERA_MAXIMA_S = 30


def _lock_for(org_id: str) -> threading.Semaphore:
    # Semáforo (no RLock): lo puede soltar otro hilo (el cierre de la sesión
    # en FastAPI puede ir en otro hilo del pool). La reentrada de la misma
    # transacción se resuelve con `session.info`.
    lk = _org_locks.get(org_id)
    if lk is None:
        with _locks_meta_lock:
            lk = _org_locks.get(org_id) or threading.Semaphore(1)
            _org_locks[org_id] = lk
    return lk


def _soltar_locks(session, transaction=None) -> None:
    # Solo al terminar la transacción EXTERIOR (no un SAVEPOINT de `begin_nested`).
    if transaction is not None and getattr(transaction, "parent", None) is not None:
        return
    for lk in session.info.pop(_CLAVE_SESION, {}).values():
        lk.release()


def _registrar_eventos() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session as _S
    # `after_transaction_end` cubre commit, rollback y close() sin confirmar.
    if not event.contains(_S, "after_transaction_end", _soltar_locks):
        event.listen(_S, "after_transaction_end", _soltar_locks)


_registrar_eventos()


def _bloquear_cadena(db: Session, organization_id: str) -> None:
    """Bloquea la cadena de la empresa hasta el fin de la transacción de `db`."""
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                   {"k": f"collab_audit:{organization_id}"})
        return
    tenidos = db.info.setdefault(_CLAVE_SESION, {})
    if organization_id in tenidos:      # segunda escritura de la misma transacción
        return
    lk = _lock_for(organization_id)
    if not lk.acquire(timeout=_ESPERA_MAXIMA_S):
        # Una sesión que nunca termina no puede colgar al resto (solo en desarrollo).
        logger.warning("cadena de auditoría de %s: bloqueo no obtenido en %ss", organization_id, _ESPERA_MAXIMA_S)
        return
    tenidos[organization_id] = lk


def write(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: Optional[str],
    actor_client_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    from app.models.collaboration import CollaborationAuditEvent

    payload = payload or {}
    _bloquear_cadena(db, organization_id)
    from sqlalchemy import exists
    from sqlalchemy.orm import aliased
    hijo = aliased(CollaborationAuditEvent)
    prev = (
        db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.organization_id == organization_id,
                ~exists().where(hijo.prev_event_id == CollaborationAuditEvent.id))
        .order_by(CollaborationAuditEvent.created_at.desc(), CollaborationAuditEvent.id.desc())
        .first()
    )
    prev_hash = prev.integrity_hash if prev and prev.integrity_hash else "GENESIS"
    from datetime import datetime, timezone
    import uuid

    row = CollaborationAuditEvent(
        id=str(uuid.uuid4()),          # entra en el HMAC: se fija antes del flush
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_client_id=actor_client_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        prev_event_id=prev.id if prev else None,
        # La fecha la pone el código (al segundo) porque entra en la huella v2.
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        hash_version=HASH_VERSION,
    )
    row.integrity_hash = _huella(HASH_VERSION, prev_hash, row)
    _firmar(row)
    db.add(row)
    # El siguiente `write` de esta misma transacción tiene que ver esta fila como cola.
    db.flush([row])
    return row


def verify_chain(db: Session, organization_id: str) -> dict:
    """Recompute the chain by following prev_event_id pointers."""
    from app.models.collaboration import CollaborationAuditEvent

    rows = {
        r.id: r
        for r in db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.organization_id == organization_id)
        .all()
    }
    hijos: dict = {}
    for r in rows.values():
        if r.prev_event_id:
            hijos.setdefault(r.prev_event_id, []).append(r)
    breaks = []
    sin_clave: list[str] = []
    claves: dict = {}
    if any(getattr(r, "hmac", None) for r in rows.values()):
        try:
            from app.services.key_management import get_jwt_verification_keys
            kids = {r.key_id for r in rows.values() if getattr(r, "hmac", None) and r.key_id}
            for kid in kids:
                claves.update(get_jwt_verification_keys(kid))
        except Exception:
            logger.warning("cadena de colaboración: llavero no disponible al verificar", exc_info=True)
    # Find the genesis (no prev_event_id) — should be exactly one if data is intact.
    seen_chains = 0
    for start in [r for r in rows.values() if not r.prev_event_id]:
        seen_chains += 1
        prev_hash = "GENESIS"
        cur = start
        visited = set()
        while cur and cur.id not in visited:
            visited.add(cur.id)
            h = _huella(getattr(cur, "hash_version", None) or "v1", prev_hash, cur)
            if h != cur.integrity_hash:
                breaks.append({"id": cur.id, "expected": h, "got": cur.integrity_hash})
            fallo_hmac = _comprobar_hmac(cur, claves)
            if fallo_hmac == "hmac":
                breaks.append({"id": cur.id, "hmac": "no_cuadra", "key_id": cur.key_id})
            elif fallo_hmac == "sin_clave":
                sin_clave.append(cur.id)
            prev_hash = cur.integrity_hash or h
            # Hijos (índice: O(n) en vez de O(n²)). Más de uno = bifurcación.
            children = hijos.get(cur.id, [])
            if len(children) > 1:
                breaks.append({"id": cur.id, "fork": [c.id for c in children]})
            cur = children[0] if children else None
    # `unverifiable`: filas con HMAC cuya clave ya no está en el llavero (podada
    # tras rotar). No es rotura: la huella encadenada se ha comprobado igual.
    return {"total": len(rows), "chains": seen_chains, "breaks": breaks,
            "unverifiable": sin_clave, "is_valid": not breaks and seen_chains <= 1}


# Public alias
audit_log = type("AuditLog", (), {"write": staticmethod(write), "verify_chain": staticmethod(verify_chain)})
