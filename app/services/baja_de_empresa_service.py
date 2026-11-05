"""Baja definitiva de una empresa: cuarentena, exportación y borrado.

Revisión multitenant 2026-11 (como contecpos, ADR-019):

1. **Pedir la baja** suspende la empresa en el acto (nadie entra, las sesiones
   abiertas se cortan) y abre una cuarentena de `TENANT_DELETION_QUARANTINE_DAYS`.
2. Durante la cuarentena se puede **deshacer**, y se puede **descargar** todo lo
   suyo (un ZIP con un JSON por tabla).
3. Al vencer, el trabajo diario **borra** sus filas de todas las tablas, en
   orden de dependencias y en una sola transacción: o se borra todo o nada.

Los usuarios cuya ficha es de la empresa pero que pertenecen a otras no se
borran: su ficha pasa a otra de sus empresas y solo pierden esta.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models.mfa import Organization
from app.models.user import User, UserOrganizationMembership

_log = logging.getLogger(__name__)


def _dias_de_cuarentena(db: Session) -> int:
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "TENANT_DELETION_QUARANTINE_DAYS") or settings.TENANT_DELETION_QUARANTINE_DAYS)


def pedir_baja(db: Session, org: Organization, motivo: str, actor) -> Organization:
    if not (motivo or "").strip():
        raise ValueError("motivo_requerido")
    ahora = datetime.now(timezone.utc)
    org.is_active = False
    org.suspension_reason = f"Baja: {motivo.strip()}"
    org.deletion_requested_at = ahora
    org.deletion_purge_after = ahora + timedelta(days=_dias_de_cuarentena(db))
    org.deletion_requested_by = getattr(actor, "id", None)
    db.commit()
    return org


def deshacer_baja(db: Session, org: Organization) -> Organization:
    """Cancela la baja; la empresa sigue suspendida hasta que se reactive."""
    if org.deletion_requested_at is None:
        raise ValueError("sin_baja")
    org.deletion_requested_at = org.deletion_purge_after = org.deletion_requested_by = None
    db.commit()
    return org


# ── Qué es de la empresa ─────────────────────────────────────────────────────

def _tablas_con_organizacion():
    return [t for t in Base.metadata.sorted_tables if "organization_id" in t.c]


def _tablas_de_sus_usuarios():
    """Tablas sin `organization_id` que cuelgan de `users`: (tabla, columnas hacia users)."""
    out = []
    for t in Base.metadata.sorted_tables:
        if "organization_id" in t.c:
            continue
        cols = [fk.parent for fk in t.foreign_keys if fk.column.table.name == "users"]
        if cols:
            out.append((t, cols))
    return out


def _usuarios_que_se_van(db: Session, org_id: str) -> tuple[set, dict]:
    """(los que se borran, {usuario: otra empresa} de los que solo pierden esta)."""
    # Los superadmins de la plataforma nunca se borran: se quedan sin empresa.
    de_ficha = {u for (u,) in db.execute(sa.select(User.id).where(
        User.organization_id == org_id, User.is_superadmin.isnot(True)))}
    otras = {}
    for uid, otra in db.execute(sa.select(UserOrganizationMembership.user_id, UserOrganizationMembership.organization_id)
                                .where(UserOrganizationMembership.user_id.in_(de_ficha),
                                       UserOrganizationMembership.organization_id != org_id)):
        otras.setdefault(uid, otra)
    return de_ficha - set(otras), otras


def _a_json(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, bytes):
        return None
    return valor


def exportar(db: Session, org_id: str) -> bytes:
    """ZIP con un JSON por tabla con todas las filas de la empresa."""
    from app.db.session import sin_filtro_de_tenant
    borrar, _ = _usuarios_que_se_van(db, org_id)
    buf = io.BytesIO()
    with sin_filtro_de_tenant(db), zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        resumen = {}
        for t in _tablas_con_organizacion():
            filas = [{k: _a_json(v) for k, v in f._mapping.items()}
                     for f in db.execute(sa.select(t).where(t.c.organization_id == org_id))]
            if t.name == "users":
                for f in filas:
                    f.pop("hashed_password", None)
                    f.pop("mfa_secret", None)
            if filas:
                zf.writestr(f"{t.name}.json", json.dumps(filas, ensure_ascii=False, indent=1, default=str))
                resumen[t.name] = len(filas)
        for t, cols in _tablas_de_sus_usuarios():
            if not borrar:
                break
            cond = sa.or_(*[c.in_(borrar) for c in cols])
            filas = [{k: _a_json(v) for k, v in f._mapping.items()} for f in db.execute(sa.select(t).where(cond))]
            if filas:
                zf.writestr(f"{t.name}.json", json.dumps(filas, ensure_ascii=False, indent=1, default=str))
                resumen[t.name] = len(filas)
        zf.writestr("_resumen.json", json.dumps({"organization_id": org_id, "tablas": resumen,
                                                  "exportado": datetime.now(timezone.utc).isoformat()}, indent=1))
    return buf.getvalue()


# Columnas que solo dicen quien creo o asigno algo: al irse el usuario se vacian
# (la fila es de otro, p. ej. una politica global de la plataforma).
_SOLO_AUTORIA = {"created_by", "assigned_by", "lead_analyst", "assigned_to"}


def _soltar_referencias_externas(db: Session, org_id: str, borrar: set, borrados: dict) -> None:
    for t in Base.metadata.sorted_tables:
        for fk in t.foreign_keys:
            madre = fk.column.table
            if "organization_id" not in madre.c or madre.name == "organizations":
                continue
            if madre.name == "users":
                if not borrar:
                    continue
                ids = sa.select(madre.c.id).where(madre.c.id.in_(borrar))
            else:
                ids = sa.select(fk.column).where(madre.c.organization_id == org_id)
            col = fk.parent
            fuera = col.in_(ids)
            if "organization_id" in t.c:
                fuera = sa.and_(fuera, sa.or_(t.c.organization_id.is_(None), t.c.organization_id != org_id))
            if col.nullable and not col.primary_key:
                db.execute(sa.update(t).where(fuera).values({col.name: None}))
            else:
                n = db.execute(sa.delete(t).where(fuera)).rowcount
                if n:
                    borrados[t.name] = borrados.get(t.name, 0) + n


class BloqueoLegalImpidePurga(RuntimeError):
    """La empresa tiene bloqueos legales activos: sus datos no se pueden borrar."""


def purgar(db: Session, org_id: str) -> dict:
    """Borra todo lo de la empresa en una transacción. Devuelve filas por tabla.

    Revisión 2026-11: con un bloqueo legal activo no se borra nada (la purga se
    niega y la empresa sigue en cuarentena hasta que se levante).
    """
    from app.db.session import sin_filtro_de_tenant
    from app.services.retencion import bloqueos_activos
    activos = bloqueos_activos(db, org_id)
    if activos:
        raise BloqueoLegalImpidePurga(", ".join(sorted({b.case_reference for b in activos})))
    borrados: dict = {}
    with sin_filtro_de_tenant(db):
        borrar, se_quedan = _usuarios_que_se_van(db, org_id)
        # Los que tienen otra empresa: su ficha pasa a ella.
        for uid, otra in se_quedan.items():
            db.execute(sa.update(User.__table__).where(User.id == uid).values(organization_id=otra))
        # Lo que cuelga de sus usuarios sin columna de empresa: lo que es suyo
        # se borra; si la columna admite NULL (quien lo creo) se vacia.
        for t, cols in _tablas_de_sus_usuarios():
            if not borrar:
                break
            vaciables = [c for c in cols if c.nullable and c.name in _SOLO_AUTORIA]
            for c in vaciables:
                db.execute(sa.update(t).where(c.in_(borrar)).values({c.name: None}))
            suyas = [c for c in cols if c not in vaciables]
            if suyas:
                n = db.execute(sa.delete(t).where(sa.or_(*[c.in_(borrar) for c in suyas]))).rowcount
                if n:
                    borrados[t.name] = n
        # Los superadmins que viven en ella pasan a otra empresa (la columna no
        # admite NULL en Postgres). Si no queda ninguna, no se borra.
        if db.execute(sa.select(User.id).where(User.organization_id == org_id, User.is_superadmin.is_(True))).first():
            otra = db.execute(sa.select(Organization.id).where(Organization.id != org_id)
                              .order_by(Organization.created_at)).scalar()
            if otra is None:
                raise ValueError("Es la única empresa y en ella vive el superadmin: no se puede borrar")
            db.execute(sa.update(User.__table__).where(User.organization_id == org_id, User.is_superadmin.is_(True))
                       .values(organization_id=otra))
        # Lo de FUERA de la empresa (otras empresas, filas globales) que apunta a
        # algo suyo: se vacia la referencia si admite NULL, si no la fila se va.
        # Medido en Postgres: registros de IA globales apuntaban a sus usuarios.
        _soltar_referencias_externas(db, org_id, borrar, borrados)
        # Las tablas de la empresa, de hijas a madres.
        for t in reversed(_tablas_con_organizacion()):
            if t.name == "organizations":
                continue
            cond = t.c.organization_id == org_id
            if t.name == "users":
                cond = sa.and_(cond, t.c.id.in_(borrar)) if borrar else sa.false()
            n = db.execute(sa.delete(t).where(cond)).rowcount
            if n:
                borrados[t.name] = n
        # Lo que apunta a la empresa por otra columna (p. ej. `org_id`) tambien es suyo.
        for t in reversed(Base.metadata.sorted_tables):
            for fk in t.foreign_keys:
                if fk.column.table.name == "organizations" and fk.parent.name != "organization_id":
                    n = db.execute(sa.delete(t).where(fk.parent == org_id)).rowcount
                    if n:
                        borrados[t.name] = borrados.get(t.name, 0) + n
        db.execute(sa.delete(Organization.__table__).where(Organization.id == org_id))
    db.commit()
    return borrados


def purgar_caducadas(db: Session) -> list:
    """Trabajo diario: borra las empresas cuya cuarentena ha vencido."""
    ahora = datetime.now(timezone.utc)
    hechas = []
    vencidas = [o for (o,) in db.query(Organization.id).filter(
        Organization.deletion_purge_after.isnot(None), Organization.deletion_purge_after <= ahora).all()]
    for org_id in vencidas:
        try:
            filas = purgar(db, org_id)
            hechas.append({"organization_id": org_id, "rows": sum(filas.values())})
            _log.warning("Empresa %s borrada tras su cuarentena: %d filas", org_id, sum(filas.values()))
        except Exception:
            db.rollback()
            _log.exception("No se pudo borrar la empresa %s; se reintenta mañana", org_id)
    return hechas


def purgar_caducadas_job() -> None:
    from app.db.session import worker_db_session
    with worker_db_session() as db:
        purgar_caducadas(db)


def obtener(db: Session, org_id: str) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise ValueError("not_found")
    return org


def usuario_de(db: Session, user_id: str) -> User:
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        usuario = db.get(User, user_id)
    if usuario is None:
        raise ValueError("not_found")
    return usuario
