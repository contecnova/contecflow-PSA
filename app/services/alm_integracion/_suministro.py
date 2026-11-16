"""Dar a una persona una licencia o un equipo: de la bolsa o del almacén si hay,
y si no, una petición de compra (ticket en la cola de compras).

Lo usan el kit de alta (`kits.confirmar`) y el cumplimiento de las peticiones
del catálogo (`catalogo.cumplir`). Toda asignación pasa por
`alm_asignaciones.asignar` (fase 1): asientos, bolsas, acta de entrega e
historial son suyos.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.alm import ALMAsignacion, ALMAsset, ALMLicense
from app.services.alm_integracion import _comun as c

logger = logging.getLogger(__name__)

#: Errores de `asignar` que significan «no queda dónde sacarlo»: se pide compra.
SIN_EXISTENCIAS = ("alm_sin_asientos", "alm_bolsa_sin_asientos", "alm_activo_no_disponible")

#: Estado físico preferido al elegir un equipo del almacén (mejor primero).
ORDEN_DE_CONDICION = ("new", "good", "fair", "poor")


def _bolsa_del_proyecto(db: Session, license_id: str, project_id: Optional[str]) -> Optional[ALMAsignacion]:
    """La bolsa activa de esa licencia en el proyecto que aún tiene asientos libres."""
    if not project_id:
        return None
    servicio = c.asignaciones()
    for bolsa in db.query(ALMAsignacion).filter(
            ALMAsignacion.license_id == license_id, ALMAsignacion.mode == "pool",
            ALMAsignacion.holder_type == "project", ALMAsignacion.holder_project_id == project_id,
            ALMAsignacion.status == "active").all():
        if servicio.usados_en_bolsa(db, bolsa) < (bolsa.quantity or 0):
            return bolsa
    return None


def equipo_disponible(db: Session, asset_type: str) -> Optional[ALMAsset]:
    """Un equipo de ese tipo en el almacén (sin titular), el de mejor estado primero."""
    filas = db.query(ALMAsset).filter(ALMAsset.type == asset_type, ALMAsset.is_active.is_(True),
                                      ALMAsset.status == "available").all()
    if not filas:
        return None

    def orden(a):
        cond = getattr(a.condition, "value", a.condition)
        return (ORDEN_DE_CONDICION.index(cond) if cond in ORDEN_DE_CONDICION else len(ORDEN_DE_CONDICION),
                -(a.purchase_date.toordinal() if a.purchase_date else 0))
    return sorted(filas, key=orden)[0]


def abrir_compra(db: Session, *, tipo: str, user_id: str, actor_id: Optional[str], org_id: Optional[str],
                 license_id: Optional[str] = None, asset_type: Optional[str] = None,
                 origen_ticket_id: Optional[str] = None, motivo: Optional[str] = None):
    """Petición de compra: ticket en la cola `ALM_PURCHASE_GROUP_ID`, enlazado a
    la licencia (si es de una) y a la petición de origen."""
    from app.models.user import User
    persona = db.get(User, user_id)
    nombre = persona.full_name if persona else "—"
    if tipo == "licencia":
        lic = db.get(ALMLicense, license_id) if license_id else None
        que = f"un asiento de {lic.name if lic else license_id}"
        enlace = (c.ENLACE_LICENCIA, license_id) if license_id else None
    else:
        que = f"un equipo de tipo {asset_type}"
        enlace = None
    descripcion = (f"No queda {que} disponible para {nombre}.\n"
                   + (f"Motivo: {motivo}\n" if motivo else "")
                   + "Al recibirlo, dalo de alta en el inventario y asígnalo desde ALM.")
    ticket = c.abrir_ticket(db, titulo=f"Compra: {que} para {nombre}", descripcion=descripcion,
                            solicitante_id=actor_id or user_id, grupo_ajuste="ALM_PURCHASE_GROUP_ID",
                            org_id=org_id, enlace=enlace)
    if origen_ticket_id:
        from app.models.service_desk import Ticket
        ticket.parent_ticket_id = origen_ticket_id if db.get(Ticket, origen_ticket_id) is not None else None
    return ticket


def dar_licencia(db: Session, *, actor, user_id: str, license_id: str, org_id: Optional[str],
                 project_id: Optional[str] = None, source: str, reason: Optional[str] = None,
                 origen_ticket_id: Optional[str] = None) -> dict:
    """Asigna la licencia (de la bolsa del proyecto si la hay) o pide su compra.

    Devuelve ``{"resultado": "asignada"|"compra"|"error", ...}``. No confirma.
    """
    bolsa = _bolsa_del_proyecto(db, license_id, project_id)
    try:
        a = c.asignaciones().asignar(
            db, actor=actor, holder_type="user", holder_id=user_id, license_id=license_id,
            parent_id=bolsa.id if bolsa else None, reason=reason, source=source,
            charge_project_id=project_id or None, require_approval=False, commit=False)
        return {"resultado": "asignada", "assignment_id": a.id, "desde_bolsa": bool(bolsa)}
    except ErrorDeDominio as exc:
        if exc.detail not in SIN_EXISTENCIAS:
            return {"resultado": "error", "codigo": exc.detail}
    t = abrir_compra(db, tipo="licencia", user_id=user_id, actor_id=getattr(actor, "id", None), org_id=org_id,
                     license_id=license_id, origen_ticket_id=origen_ticket_id, motivo=reason)
    return {"resultado": "compra", "ticket_id": t.id, "ticket_number": t.number}


def dar_equipo(db: Session, *, actor, user_id: str, asset_type: str, org_id: Optional[str],
               project_id: Optional[str] = None, source: str, reason: Optional[str] = None,
               origen_ticket_id: Optional[str] = None, valid_to=None) -> dict:
    """Asigna (o presta, con ``valid_to``) un equipo del almacén, o pide su compra. No confirma."""
    activo = equipo_disponible(db, asset_type)
    if activo is not None:
        try:
            a = c.asignaciones().asignar(
                db, actor=actor, holder_type="user", holder_id=user_id, asset_id=activo.id,
                mode="loan" if valid_to else "assignment", valid_to=valid_to, reason=reason, source=source,
                charge_project_id=project_id or None, require_approval=False, commit=False)
            c.enlazar_ticket(db, origen_ticket_id, c.ENLACE_ACTIVO, activo.id)
            return {"resultado": "asignado", "assignment_id": a.id, "asset_id": activo.id,
                    "asset_name": activo.name}
        except ErrorDeDominio as exc:
            if exc.detail not in SIN_EXISTENCIAS:
                return {"resultado": "error", "codigo": exc.detail}
    t = abrir_compra(db, tipo="equipo", user_id=user_id, actor_id=getattr(actor, "id", None), org_id=org_id,
                     asset_type=asset_type, origen_ticket_id=origen_ticket_id, motivo=reason)
    return {"resultado": "compra", "ticket_id": t.id, "ticket_number": t.number}


def disponibilidad(db: Session, *, license_id: Optional[str] = None, asset_type: Optional[str] = None,
                   project_id: Optional[str] = None) -> dict:
    """Si hay de dónde sacarlo ahora mismo (para que la propuesta lo diga antes de confirmar)."""
    if license_id:
        lic = db.get(ALMLicense, license_id)
        if lic is None:
            return {"disponible": False, "libres": 0}
        if _bolsa_del_proyecto(db, license_id, project_id) is not None:
            return {"disponible": True, "libres": None, "bolsa": True}
        limite = c.asignaciones()._limite_de_asientos(lic)
        if limite is None:
            return {"disponible": True, "libres": None}
        libres = max(0, limite - c.asignaciones().asientos_usados(db, lic))
        return {"disponible": libres > 0, "libres": libres}
    libres = db.query(ALMAsset).filter(ALMAsset.type == asset_type, ALMAsset.is_active.is_(True),
                                       ALMAsset.status == "available").count()
    return {"disponible": libres > 0, "libres": libres}
