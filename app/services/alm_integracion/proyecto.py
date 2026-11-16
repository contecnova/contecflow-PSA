"""Recursos técnicos de un proyecto: su bolsa de asientos, las licencias y
equipos asignados al proyecto y a su equipo, y su coste en el periodo.

- Ver: quien ve el proyecto (`exigir_proyecto_visible`). Quien no tiene ficha
  ajena (empleado, subcontratado) ve lo del proyecto y, del equipo, solo lo suyo.
- Coste: el PM del proyecto, administración y quien ve el módulo financiero de
  presupuestos (`ve_modulo_financiero`). El cálculo es el de la fase 3
  (`alm_costes.lineas`, coste por titular y día).
- Asignar y liberar: el PM del proyecto o administración, siempre por
  `alm_asignaciones` (asientos, bolsa, aprobación de la empresa, acta).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.alm import ALMAsignacion, ALMLicense
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.alm_integracion import _comun as c

#: Días del periodo de coste cuando la pantalla no dice desde cuándo.
PERIODO_POR_DEFECTO_DIAS = 30


def _proyecto(db: Session, viewer, project_id: str) -> Project:
    from app.services.politica_de_visibilidad import exigir_proyecto_visible
    exigir_proyecto_visible(db, viewer, project_id)
    p = db.query(Project).filter(Project.id == project_id).first()
    c.exigir(p is not None, "almint_proyecto_no_encontrado", 404)
    return p


def puede_gestionar(viewer, proyecto: Project) -> bool:
    rol = getattr(viewer.role, "value", viewer.role)
    return bool(getattr(viewer, "is_superadmin", False) or rol == "admin" or proyecto.pm_id == viewer.id)


def ve_costes(db: Session, viewer, proyecto: Project) -> bool:
    if puede_gestionar(viewer, proyecto):
        return True
    from app.services.politica_de_visibilidad import ve_modulo_financiero
    return ve_modulo_financiero(db, viewer, "budgets")


def equipo_del_proyecto(db: Session, proyecto: Project) -> list[User]:
    ids = {uid for (uid,) in db.query(ProjectMember.user_id).filter(ProjectMember.project_id == proyecto.id,
                                                                    ProjectMember.is_active.is_(True))}
    if proyecto.pm_id:
        ids.add(proyecto.pm_id)
    return db.query(User).filter(User.id.in_(ids)).order_by(User.full_name).all() if ids else []


def _fila(db: Session, a: ALMAsignacion) -> dict:
    fila = c.asignaciones().serializar(db, a)
    if a.resource_type == "asset" and a.asset is not None:
        fila["asset_tag"] = a.asset.asset_tag
        fila["asset_type"] = getattr(a.asset.type, "value", a.asset.type)
    return fila


def recursos(db: Session, viewer, project_id: str, desde=None, hasta=None) -> dict:
    from app.services.alm_asignaciones import _fecha
    from app.services.politica_de_visibilidad import ve_contacto_ajeno
    proyecto = _proyecto(db, viewer, project_id)
    hasta = _fecha(hasta, "hasta") or c.hoy()
    desde = _fecha(desde, "desde") or (hasta - timedelta(days=PERIODO_POR_DEFECTO_DIAS - 1))
    c.exigir(desde <= hasta, "almint_periodo_invalido")

    vigentes = ("active", "pending")
    del_proyecto = db.query(ALMAsignacion).filter(
        ALMAsignacion.status.in_(vigentes),
        or_(ALMAsignacion.holder_project_id == proyecto.id, ALMAsignacion.charge_project_id == proyecto.id)).all()
    bolsas = [a for a in del_proyecto if a.mode == "pool"]
    hijas_de_bolsa = db.query(ALMAsignacion).filter(
        ALMAsignacion.parent_id.in_([b.id for b in bolsas] or [""]), ALMAsignacion.status.in_(vigentes)).all()
    sueltas = [a for a in del_proyecto if a.mode != "pool"]

    equipo = equipo_del_proyecto(db, proyecto)
    if not ve_contacto_ajeno(viewer):
        equipo = [u for u in equipo if u.id == viewer.id]
    ids_equipo = [u.id for u in equipo]
    ya = {a.id for a in del_proyecto} | {a.id for a in hijas_de_bolsa}
    del_equipo = [a for a in db.query(ALMAsignacion).filter(
        ALMAsignacion.holder_user_id.in_(ids_equipo or [""]), ALMAsignacion.status.in_(vigentes)).all()
        if a.id not in ya]

    salida = {
        "project_id": proyecto.id, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "puedo_gestionar": puede_gestionar(viewer, proyecto),
        "licencias_del_proyecto": [{"id": lic.id, "name": lic.name, "total_seats": lic.total_seats}
                                   for lic in db.query(ALMLicense).filter(ALMLicense.project_id == proyecto.id,
                                                                          ALMLicense.is_active.is_(True)).all()],
        "bolsas": [{**_fila(db, b), "hijas": [_fila(db, h) for h in hijas_de_bolsa if h.parent_id == b.id]}
                   for b in bolsas],
        "asignaciones": [_fila(db, a) for a in sueltas],
        "equipo": [{"user_id": u.id, "user_name": u.full_name,
                    "licencias": [_fila(db, a) for a in del_equipo
                                  if a.holder_user_id == u.id and a.resource_type == "license"],
                    "equipos": [_fila(db, a) for a in del_equipo
                                if a.holder_user_id == u.id and a.resource_type == "asset"]}
                   for u in equipo],
        "coste": None,
    }
    if ve_costes(db, viewer, proyecto):
        salida["coste"] = coste(db, proyecto, ids_equipo, desde, hasta)
    return salida


def coste(db: Session, proyecto: Project, ids_equipo: list[str], desde: date, hasta: date) -> dict:
    """Coste del periodo (fase 3): lo imputado al proyecto y, aparte, lo que el
    equipo tiene y se imputa a otro sitio (su centro de coste, otro proyecto)."""
    from app.services import alm_costes
    imputado = alm_costes.lineas(db, desde, hasta, project_id=proyecto.id)
    fuera = []
    if ids_equipo:
        equipo = set(ids_equipo)
        fuera = [li for li in alm_costes.lineas(db, desde, hasta, incluir_ociosos=False)
                 if li.holder_type == "user" and li.holder_id in equipo and li.project_id != proyecto.id]
    moneda = proyecto.currency if getattr(proyecto, "currency", None) else None

    def _total(filas):
        fx: dict = {}
        if not moneda:
            return round(sum(li.amount for li in filas), 2)
        return round(sum(alm_costes._convertir(db, li.amount, li.currency, moneda, hasta, fx) for li in filas), 2)

    def _por_recurso(filas):
        agrupado: dict = {}
        for li in filas:
            k = (li.resource_type, li.resource_id)
            g = agrupado.setdefault(k, {"resource_type": li.resource_type, "resource_id": li.resource_id,
                                        "resource_name": li.resource_name, "kind": li.kind, "amount": 0.0,
                                        "days": 0, "currency": li.currency})
            g["amount"] = round(g["amount"] + li.amount, 2)
            g["days"] += li.days
        return sorted(agrupado.values(), key=lambda g: -g["amount"])

    return {
        "moneda": moneda, "imputado": _total(imputado), "del_equipo_fuera": _total(fuera),
        "ocioso": _total([li for li in imputado if li.kind == "idle"]),
        "rebillable": _total([li for li in imputado if li.rebillable]),
        "por_recurso": _por_recurso(imputado), "del_equipo_por_recurso": _por_recurso(fuera),
    }


# ── Acciones ──────────────────────────────────────────────────────────────────

def asignar(db: Session, viewer, project_id: str, datos: dict) -> dict:
    """Asigna al proyecto (bolsa de asientos, equipo del proyecto) o a una
    persona de su equipo (de la bolsa si la hay). Sigue la aprobación de la empresa."""
    proyecto = _proyecto(db, viewer, project_id)
    c.exigir(puede_gestionar(viewer, proyecto), "almint_sin_permiso", 403)
    titular = datos.get("holder_type") or "project"
    c.exigir(titular in ("project", "user"), "almint_titular_invalido")
    holder_id = proyecto.id if titular == "project" else datos.get("holder_id")
    if titular == "user":
        c.exigir(holder_id in {u.id for u in equipo_del_proyecto(db, proyecto)}, "almint_no_es_del_equipo")
    parent_id = datos.get("parent_id") or None
    if parent_id:
        bolsa = db.get(ALMAsignacion, parent_id)
        c.exigir(bolsa is not None and bolsa.holder_project_id == proyecto.id, "almint_bolsa_de_otro_proyecto")
    a = c.asignaciones().asignar(
        db, actor=viewer, holder_type=titular, holder_id=holder_id,
        license_id=datos.get("license_id") or None, asset_id=datos.get("asset_id") or None,
        quantity=datos.get("quantity") or 1, valid_from=datos.get("valid_from"), valid_to=datos.get("valid_to"),
        reason=datos.get("reason"), mode=datos.get("mode") or None, parent_id=parent_id,
        charge_project_id=proyecto.id, source="manual")
    return _fila(db, a)


def liberar(db: Session, viewer, project_id: str, asignacion_id: str, motivo: Optional[str]) -> dict:
    """Libera una asignación del proyecto o de una persona de su equipo cargada al proyecto."""
    proyecto = _proyecto(db, viewer, project_id)
    c.exigir(puede_gestionar(viewer, proyecto), "almint_sin_permiso", 403)
    a = db.get(ALMAsignacion, asignacion_id)
    padre = db.get(ALMAsignacion, a.parent_id) if a is not None and a.parent_id else None
    del_proyecto = a is not None and (a.holder_project_id == proyecto.id or a.charge_project_id == proyecto.id
                                      or (padre is not None and padre.holder_project_id == proyecto.id))
    c.exigir(del_proyecto, "almint_asignacion_no_encontrada", 404)
    a = c.asignaciones().liberar(db, a.id, actor=viewer, motivo=motivo, tipo="released", origen="project")
    return _fila(db, a)
