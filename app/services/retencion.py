"""Políticas de retención generales y bloqueo legal (revisión 2026-11, lo que contecmind y contecintelligence tenían).

Hasta ahora sólo el chat de colaboración tenía retención. Esto la extiende a
los tipos de registro donde tiene sentido, con la misma regla en todos:

- **Política** por empresa y tipo: cuántos días se guarda (`keep_days`). Nace
  apagada; la **vista previa** dice cuántos registros borraría y cuántos salva
  un bloqueo antes de activarla. Mínimo `RETENTION_MIN_DAYS`.
- **Bloqueo legal**: lo que coincide (tipo, o todos, + campo = valor; p. ej. el
  cliente de un litigio) no se borra **ni por retención ni a mano**: el borrado
  manual de un registro bloqueado devuelve 409 (evento `before_flush`).
- Un trabajo diario aplica las políticas activas; cada pasada queda en el
  registro de auditoría con lo borrado por tipo.

Lo que NO se retiene, a propósito: el registro de auditoría (es la evidencia; la
cadena se rompería) ni los datos financieros, que la ley obliga a conservar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import HTTPException
from sqlalchemy import false, func, or_

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tipo:
    modelo: Callable                  # devuelve la clase (import diferido)
    fecha: Callable                   # (Modelo) -> expresión de la fecha que cuenta
    condicion: Optional[Callable]     # (Modelo) -> filtro extra (p. ej. sólo cerrados)
    campos: tuple[str, ...]           # campos por los que se puede bloquear


def _ticket():
    from app.models.service_desk.tickets import Ticket
    return Ticket


def _documento():
    from app.models.documents import Document
    return Document


def _conversacion():
    from app.models.ai_chat import AIConversation
    return AIConversation


def _uso_ia():
    from app.models.ai_providers import AIUsageLog
    return AIUsageLog


def _aviso():
    from app.models.enterprise import Notification
    return Notification


TIPOS: dict[str, Tipo] = {
    # Sólo tickets cerrados, contando desde el cierre.
    "tickets": Tipo(_ticket, lambda M: M.closed_at, lambda M: M.closed_at.isnot(None),
                    ("id", "client_id", "project_id", "requester_user_id", "created_by_user_id")),
    # Sólo documentos archivados, desde su último cambio.
    "documents": Tipo(_documento, lambda M: func.coalesce(M.updated_at, M.created_at), lambda M: M.is_archived.is_(True),
                      ("id", "client_id", "project_id", "created_by")),
    "ai_conversations": Tipo(_conversacion, lambda M: func.coalesce(M.updated_at, M.created_at), None, ("id", "user_id")),
    "ai_usage_logs": Tipo(_uso_ia, lambda M: M.created_at, None, ("id", "user_id")),
    "notifications": Tipo(_aviso, lambda M: M.created_at, None, ("id", "user_id")),
}


class BloqueoLegalActivo(HTTPException):
    def __init__(self, caso: str):
        super().__init__(409, f"Este registro está bajo bloqueo legal ({caso}) y no se puede borrar")


# ── Bloqueos ──────────────────────────────────────────────────────────────────

def _sin_filtro(db):
    from app.db.session import sin_filtro_de_tenant
    return sin_filtro_de_tenant(db)


def bloqueos_activos(db, org) -> list:
    from app.models.governance import LegalHold
    with _sin_filtro(db):
        return db.query(LegalHold).filter(LegalHold.organization_id == org, LegalHold.is_active.is_(True)).all()


def _condicion_bloqueada(clave: str, M, bloqueos: list):
    """Expresión SQL: el registro coincide con algún bloqueo activo de su tipo."""
    tipo = TIPOS[clave]
    # COALESCE: con un campo vacío (NULL) la comparación da NULL, y su negación
    # también; sin él, «no bloqueado» excluía todo lo que no tenía ese campo.
    partes = [func.coalesce(getattr(M, b.field) == b.value, false()) for b in bloqueos
              if b.entity in ("*", clave) and b.field in tipo.campos]
    return or_(*partes) if partes else false()


def _bloqueo_de(clave: str, objeto, bloqueos: list):
    tipo = TIPOS[clave]
    for b in bloqueos:
        if b.entity in ("*", clave) and b.field in tipo.campos and str(getattr(objeto, b.field, None)) == b.value:
            return b
    return None


def validar_bloqueo(entidad: str, campo: str) -> None:
    if entidad != "*" and entidad not in TIPOS:
        raise HTTPException(422, f"Tipo desconocido: {entidad}")
    validos = set().union(*(t.campos for t in TIPOS.values())) if entidad == "*" else set(TIPOS[entidad].campos)
    if campo not in validos:
        raise HTTPException(422, f"Campo no válido para {entidad}: {campo}. Válidos: {sorted(validos)}")


# ── Vista previa y aplicación ─────────────────────────────────────────────────

def _corte(dias: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=int(dias))


def _vencidos(db, org, clave: str, dias: int):
    tipo = TIPOS[clave]
    M = tipo.modelo()
    q = db.query(M).filter(M.organization_id == org, tipo.fecha(M) < _corte(dias))
    if tipo.condicion:
        q = q.filter(tipo.condicion(M))
    return M, q


def minimo_de_dias(db, org) -> int:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "RETENTION_MIN_DAYS", org) or settings.RETENTION_MIN_DAYS)


def politicas(db, org) -> list[dict]:
    """Una fila por tipo retenible: la política de la empresa (o ninguna)."""
    from app.models.governance import RetentionPolicy
    with _sin_filtro(db):
        filas = {p.entity: p for p in db.query(RetentionPolicy).filter(RetentionPolicy.organization_id == org)}
    salida = []
    for clave, tipo in TIPOS.items():
        p = filas.get(clave)
        salida.append({"entity": clave, "hold_fields": list(tipo.campos),
                       "keep_days": p.keep_days if p else None, "is_active": bool(p and p.is_active),
                       "last_run_at": p.last_run_at.isoformat() if p and p.last_run_at else None,
                       "last_deleted": p.last_deleted if p else None})
    return salida


def guardar_politica(db, org, usuario, clave: str, dias: int, activa: bool) -> dict:
    from app.models.governance import RetentionPolicy
    from app.services.audit import audit_log
    if clave not in TIPOS:
        raise HTTPException(422, f"Tipo desconocido: {clave}")
    minimo = minimo_de_dias(db, org)
    if dias < minimo:
        raise HTTPException(422, f"Mínimo {minimo} días (RETENTION_MIN_DAYS)")
    with _sin_filtro(db):
        p = db.query(RetentionPolicy).filter(RetentionPolicy.organization_id == org,
                                             RetentionPolicy.entity == clave).first()
    if p is None:
        p = RetentionPolicy(organization_id=org, entity=clave)
        db.add(p)
    p.keep_days, p.is_active, p.updated_by = int(dias), bool(activa), usuario.id
    audit_log(db, usuario, "UPDATE", "retention_policy", clave, clave,
              new_values={"keep_days": int(dias), "is_active": bool(activa)})
    db.commit()
    return next(x for x in politicas(db, org) if x["entity"] == clave)


def vista_previa(db, org, clave: str, dias: int) -> dict:
    """Cuántos registros borraría hoy esa política y cuántos salva un bloqueo."""
    bloqueos = bloqueos_activos(db, org)
    with _sin_filtro(db):
        M, q = _vencidos(db, org, clave, dias)
        total = q.count()
        retenidos = q.filter(_condicion_bloqueada(clave, M, bloqueos)).count()
    return {"entity": clave, "keep_days": dias, "expired": total, "held": retenidos,
            "would_delete": total - retenidos, "cutoff": _corte(dias).isoformat()}


def aplicar(db, org, usuario=None) -> dict:
    """Borra lo vencido y no bloqueado de cada política activa. Registro a registro
    (para que el ORM aplique sus cascadas); lo que no se puede borrar se cuenta."""
    from app.models.governance import RetentionPolicy
    from app.services.audit import audit_log
    bloqueos = bloqueos_activos(db, org)
    with _sin_filtro(db):
        activas = db.query(RetentionPolicy).filter(RetentionPolicy.organization_id == org,
                                                   RetentionPolicy.is_active.is_(True)).all()
    informe = {}
    for p in activas:
        if p.entity not in TIPOS:
            continue
        borrados, fallidos = 0, 0
        with _sin_filtro(db):
            M, q = _vencidos(db, org, p.entity, p.keep_days)
            ids = [i for (i,) in q.filter(~_condicion_bloqueada(p.entity, M, bloqueos)).with_entities(M.id)]
            for i in ids:
                try:
                    with db.begin_nested():
                        fila = db.get(M, i)
                        if fila is not None:
                            db.delete(fila)
                    borrados += 1
                except Exception:
                    fallidos += 1
                    logger.warning("retención: no se pudo borrar %s %s", p.entity, i, exc_info=True)
        p.last_run_at, p.last_deleted = datetime.now(timezone.utc), borrados
        informe[p.entity] = {"deleted": borrados, "failed": fallidos, "keep_days": p.keep_days}
    if informe:
        audit_log(db, usuario, "RETENTION_PURGE", "retention", None, "retention run",
                  metadata={"organization_id": org, "by_entity": informe, "active_holds": len(bloqueos)})
        _sellar(db, org)
    db.commit()
    return informe


def _sellar(db, org) -> None:
    """El trabajo de fondo no tiene sesión de empresa: la entrada de auditoría va a la suya."""
    from app.models.enterprise import AuditLog
    for obj in db.new:
        if isinstance(obj, AuditLog) and obj.organization_id is None:
            obj.organization_id = org


def aplicar_job() -> None:
    """Trabajo diario: las políticas activas de todas las empresas."""
    from app.db.session import SessionLocal
    from app.models.governance import RetentionPolicy
    db = SessionLocal()
    try:
        with _sin_filtro(db):
            orgs = {o for (o,) in db.query(RetentionPolicy.organization_id).filter(
                RetentionPolicy.is_active.is_(True)).distinct()}
        for org in orgs:
            try:
                informe = aplicar(db, org)
                logger.info("retención %s: %s", org, informe)
            except Exception:
                db.rollback()
                logger.exception("retención: falló la empresa %s", org)
    finally:
        db.close()


# ── Bloqueo del borrado manual ────────────────────────────────────────────────

def comprobar_borrados(session) -> None:
    """`before_flush`: ningún registro bloqueado se borra, venga de donde venga (ORM)."""
    if not session.deleted:
        return
    clases = {TIPOS[c].modelo(): c for c in TIPOS}
    por_org: dict = {}
    for obj in list(session.deleted):
        clave = clases.get(type(obj))
        if clave is None:
            continue
        org = getattr(obj, "organization_id", None)
        if org not in por_org:
            por_org[org] = bloqueos_activos(session, org)
        b = _bloqueo_de(clave, obj, por_org[org])
        if b is not None:
            raise BloqueoLegalActivo(b.case_reference)
