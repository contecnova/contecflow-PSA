"""«Pedir proyecto o servicio» desde el portal interno (docs/CLIENTES_INTERNOS.md §5.4).

La entrada es la del flujo de demanda (`app/services/demanda/entrada.py`, canal
portal interno, `Solicitante(kind="internal_user")`; docs/FLUJO_DE_DEMANDA.md).
No se crea otra entrada. Contrato que se usa:

    entrada.Solicitante(kind="internal_user", user=<User>, client_id=<unidad>)
    entrada.crear(db, solicitante, datos) -> dict con id, title, status, created_at
    entrada.listar(db, solicitante) -> list[dict]

Mientras ese módulo no exista (o no tenga esas funciones), o la empresa no tenga
ningún tipo de solicitud activo para el canal del portal interno (flujo de
demanda sin configurar), la petición entra en la cartera de siempre
(`cartera_service.guardar`, propuesta con `client_id` de la unidad), que es lo
que el flujo de demanda ejecuta al final.
"""
from __future__ import annotations

import importlib
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

TIPOS = ("proyecto", "servicio")


CANAL = "internal_portal"


def _entrada(db: Session = None, org_id: Optional[str] = None):
    """El módulo de entrada del flujo de demanda, si existe y (con `db`) la empresa
    tiene algún tipo de solicitud activo en el canal del portal interno."""
    try:
        m = importlib.import_module("app.services.demanda.entrada")
    except ImportError:
        return None
    if not all(hasattr(m, n) for n in ("Solicitante", "crear", "listar")):
        return None
    if db is not None and hasattr(m, "tipos_del_canal"):
        try:
            if not m.tipos_del_canal(db, CANAL, org_id):
                return None
        except Exception:
            logger.warning("flujo de demanda: no se pudieron leer los tipos del canal", exc_info=True)
            return None
    return m


def _solicitante(m, usuario, unidad):
    return m.Solicitante(kind="internal_user", user=usuario, client_id=unidad.id)


def _item(d: dict) -> dict:
    return {"id": d.get("id"), "title": d.get("title"), "status": d.get("status"),
            "created_at": d.get("created_at")}


def listar(db: Session, usuario, unidad) -> dict:
    m = _entrada(db, unidad.organization_id)
    if m is not None:
        try:
            return {"source": "demanda", "items": [_item(d) for d in m.listar(db, _solicitante(m, usuario, unidad))]}
        except Exception:
            logger.warning("flujo de demanda: no se pudieron listar las peticiones de %s", unidad.id, exc_info=True)
    from app.models.portfolio import PortfolioProposal
    filas = db.query(PortfolioProposal).filter(PortfolioProposal.client_id == unidad.id) \
        .order_by(PortfolioProposal.created_at.desc()).limit(200).all()
    return {"source": "cartera", "items": [{"id": p.id, "title": p.title, "status": p.status,
                                            "created_at": p.created_at.isoformat() if p.created_at else None}
                                           for p in filas]}


def pedir(db: Session, usuario, unidad, datos: dict) -> dict:
    tipo = datos.get("kind") or "proyecto"
    if tipo not in TIPOS:
        raise error(422, "interno_tipo_de_peticion_no_valido", valor=tipo)
    titulo = (datos.get("title") or "").strip()
    if not titulo:
        raise error(422, "campo_obligatorio", campo="title")
    m = _entrada(db, unidad.organization_id)
    if m is not None:
        d = m.crear(db, _solicitante(m, usuario, unidad), {**datos, "title": titulo, "client_id": unidad.id,
                                                           "origin": "internal_portal"})
        return {"source": "demanda", **_item(d if isinstance(d, dict) else {})}
    from app.services import cartera_service
    descripcion = (datos.get("description") or "").strip()
    if tipo == "servicio":
        descripcion = f"[servicio] {descripcion}".strip()
    d = cartera_service.guardar(db, usuario, {
        "title": titulo[:255], "description": descripcion or None, "client_id": unidad.id,
        "sponsor_id": unidad.business_owner_id, "estimated_budget": _num(datos.get("estimated_budget")),
        "wanted_start": _fecha(datos.get("wanted_start")), "wanted_end": _fecha(datos.get("wanted_end")),
    })
    return {"source": "cartera", "id": d.get("id"), "title": d.get("title"), "status": d.get("status"),
            "created_at": d.get("created_at")}


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _fecha(v):
    from datetime import date
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise error(422, "fecha_no_valida")
