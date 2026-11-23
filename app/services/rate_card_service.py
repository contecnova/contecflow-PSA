"""
rate_card_service.py — Service layer for Rate Cards (RateTable / RateEntry / RateOverride).
"""
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session
from app.models.advanced_config import RateTable
from app.models.advanced_config import RateEntry
from app.models.advanced_config import RateOverride
from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error


# ── helpers ────────────────────────────────────────────────────────────────────

def _org_filter(q, model, org_id, is_superadmin):
    if not is_superadmin and org_id:
        q = q.filter(model.organization_id == org_id)
    return q


def _fecha(v) -> Optional[date]:
    """Las columnas son Date; las consultas llegan como texto ISO. Revisión 2026-11: antes se
    comparaban tal cual y la búsqueda reventaba en cuanto una tarifa tenía vigencia."""
    if v is None or v == "":
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _date_valid(valid_from, valid_to, today) -> bool:
    hoy = _fecha(today)
    if valid_from and hoy < _fecha(valid_from):
        return False
    if valid_to and hoy > _fecha(valid_to):
        return False
    return True


# ── RateTable ──────────────────────────────────────────────────────────────────

def list_rate_tables(db: Session, org_id, is_superadmin: bool):
    q = db.query(RateTable).filter(RateTable.is_active == True)
    q = _org_filter(q, RateTable, org_id, is_superadmin)
    return q.order_by(RateTable.is_default.desc(), RateTable.name).all()


def create_rate_table(db: Session, payload_dict: dict, org_id, is_superadmin: bool):
    if payload_dict.get("is_default"):
        q = db.query(RateTable)
        q = _org_filter(q, RateTable, org_id, is_superadmin)
        q.update({"is_default": False})
    t = RateTable(id=str(uuid.uuid4()), organization_id=org_id, **payload_dict)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def get_rate_table_or_404(db: Session, table_id: str, org_id, is_superadmin: bool):
    q = db.query(RateTable).filter(
        RateTable.id == table_id,
        RateTable.is_active == True,
    )
    q = _org_filter(q, RateTable, org_id, is_superadmin)
    t = q.first()
    if not t:
        raise ErrorDeDominio(404)
    return t


def update_rate_table(db: Session, table_id: str, payload: dict, org_id, is_superadmin: bool):
    t = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    allowed = ["name", "description", "applies_to", "is_default", "is_active"]
    if payload.get("is_default"):
        q2 = db.query(RateTable).filter(RateTable.id != table_id)
        q2 = _org_filter(q2, RateTable, org_id, is_superadmin)
        q2.update({"is_default": False})
    for k, v in payload.items():
        if k in allowed:
            setattr(t, k, v)
    db.commit()
    return t


def delete_rate_table(db: Session, table_id: str, org_id, is_superadmin: bool):
    t = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    t.is_active = False
    db.commit()


def duplicate_rate_table(
    db: Session,
    table_id: str,
    escalation_pct: float,
    new_name: Optional[str],
    org_id,
    is_superadmin: bool,
):
    src = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    new_table = RateTable(
        id=str(uuid.uuid4()),
        organization_id=src.organization_id,
        name=new_name or f"{src.name} +{escalation_pct}%",
        description=src.description,
        applies_to=src.applies_to,
        is_default=False,
        is_active=True,
    )
    db.add(new_table)
    db.flush()
    for e in (src.entries or []):
        new_rate = round((e.billing_rate or 0) * (1 + escalation_pct / 100), 2) if escalation_pct else e.billing_rate
        new_cost = round((e.cost_rate or 0) * (1 + escalation_pct / 100), 2) if escalation_pct else e.cost_rate
        db.add(RateEntry(
            id=str(uuid.uuid4()),
            table_id=new_table.id,
            label=e.label,
            billing_rate=new_rate,
            cost_rate=new_cost,
            escalation_pct=escalation_pct,
            valid_from=str(timeutil.today()),
        ))
    db.commit()
    db.refresh(new_table)
    return new_table


# ── RateEntry ──────────────────────────────────────────────────────────────────

def add_entry(db: Session, table_id: str, payload_dict: dict, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = RateEntry(id=str(uuid.uuid4()), table_id=table_id, **payload_dict)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def update_entry(
    db: Session,
    table_id: str,
    entry_id: str,
    payload: dict,
    org_id,
    is_superadmin: bool,
):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise ErrorDeDominio(404)
    allowed = ["label", "cost_rate", "billing_rate", "escalation_pct", "valid_from", "valid_to", "notes"]
    for k, v in payload.items():
        if k in allowed:
            setattr(e, k, v)
    db.commit()
    return e


def delete_entry(db: Session, table_id: str, entry_id: str, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise ErrorDeDominio(404)
    e.is_active = False
    db.commit()


# ── RateOverride ───────────────────────────────────────────────────────────────

def add_override(db: Session, table_id: str, payload_dict: dict, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    if not payload_dict.get("client_id") and not payload_dict.get("project_id"):
        raise error(400, "indica_cliente_o_proyecto", detail="Debe especificar client_id o project_id")
    o = RateOverride(id=str(uuid.uuid4()), table_id=table_id, **payload_dict)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def delete_override(db: Session, table_id: str, override_id: str, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    o = db.query(RateOverride).filter(
        RateOverride.id == override_id,
        RateOverride.table_id == table_id,
    ).first()
    if not o:
        raise ErrorDeDominio(404)
    db.delete(o)
    db.commit()


# ── Effective rate ─────────────────────────────────────────────────────────────

def _tarifa_por_excepcion(db: Session, role_label: str, client_id, project_id,
                          hoy: str) -> Optional[dict]:
    """Una excepción de tarifa vigente, si la hay.

    El orden es proyecto y después cliente, y **no** es alfabético: lo más
    concreto gana. Una tarifa pactada para un proyecto manda sobre la del
    cliente al que pertenece.
    """
    for ambito_id, columna in ((project_id, "project_id"), (client_id, "client_id")):
        if not ambito_id:
            continue
        # Ronda 2 auditoría 2026-11-22: solo excepciones de tablas ACTIVAS
        # (antes una tabla desactivada seguía imponiendo sus excepciones).
        excepciones = db.query(RateOverride).join(
            RateTable, RateTable.id == RateOverride.table_id,
        ).filter(
            getattr(RateOverride, columna) == ambito_id,
            RateOverride.role_label == role_label,
            RateTable.is_active == True,  # noqa: E712
        ).all()
        r = _elegir_excepcion(excepciones, columna, role_label, hoy)
        if r:
            return r
    return None


def _elegir_excepcion(excepciones, columna: str, role_label: str, hoy: str) -> Optional[dict]:
    """La primera excepción vigente de la lista (regla común a la consulta y a la precarga)."""
    for o in excepciones:
        if _date_valid(o.valid_from, o.valid_to, hoy):
            return {
                "billing_rate": o.billing_rate,
                "source": f"override_{columna}",
                "role_label": role_label,
                "override_id": o.id,
            }
    return None


def _con_escalado(entry, hoy_anio: int) -> float:
    """La tarifa con el escalado anual aplicado, si la entrada lo declara.

    El escalado es compuesto y se cuenta por años enteros desde `valid_from`:
    una tarifa de 2024 con 3 % anual vale, en 2026, `base * 1.03²`. El
    `max(0, ...)` evita que una entrada con fecha futura escale hacia atrás.
    """
    tarifa = entry.billing_rate
    if tarifa is None:        # entrada solo de coste: sin tarifa de venta (no 0)
        return None
    if not entry.escalation_pct or not entry.valid_from:
        return tarifa
    anios = hoy_anio - _fecha(entry.valid_from).year
    return round(tarifa * ((1 + entry.escalation_pct / 100) ** max(0, anios)), 2)


def _tarifa_en_tablas(db: Session, role_label: str, client_id, project_id,
                      hoy: str, org_id, is_superadmin: bool) -> Optional[dict]:
    """La primera tabla de tarifas vigente que tenga este rol.

    Las tablas se ordenan por concreción: las de cliente cuando se preguntó por
    un proyecto o un cliente, luego la tabla por defecto, luego el resto.
    """
    q = _org_filter(
        db.query(RateTable).filter(RateTable.is_active == True),  # noqa: E712
        RateTable, org_id, is_superadmin,
    )
    return _elegir_en_tablas(q.all(), role_label, client_id, project_id, hoy)


def _elegir_en_tablas(tablas, role_label: str, client_id, project_id, hoy: str) -> Optional[dict]:
    """La regla de `_tarifa_en_tablas` sobre tablas ya cargadas (también la precarga)."""
    tablas = sorted(tablas, key=lambda t: (
        0 if (project_id and t.applies_to == "client") else
        1 if (client_id and t.applies_to == "client") else
        2 if t.is_default else 3
    ))

    anio = _fecha(hoy).year      # el escalado del año consultado, no del año en curso
    for tabla in tablas:
        for entry in (tabla.entries or []):
            if not entry.is_active or entry.label.lower() != role_label.lower():
                continue
            if not _date_valid(entry.valid_from, entry.valid_to, hoy):
                continue
            return {
                "billing_rate": _con_escalado(entry, anio),
                "cost_rate": entry.cost_rate,
                "source": f"table:{tabla.name}",
                "role_label": role_label,
                "table_id": tabla.id,
                "entry_id": entry.id,
                "escalation_applied": entry.escalation_pct > 0,
            }
    return None


def get_effective_rate(
    db: Session,
    role_label: str,
    client_id: Optional[str],
    project_id: Optional[str],
    as_of: Optional[str],
    org_id,
    is_superadmin: bool,
) -> dict:
    """La tarifa que aplica a un rol, en este orden: excepción y luego tabla.

    Devuelve siempre un diccionario; `source` dice de dónde salió la cifra, y
    `not_found` es una respuesta válida —no hay tarifa para ese rol— y no un
    error.
    """
    hoy = as_of or str(timeutil.today())

    return (
        _tarifa_por_excepcion(db, role_label, client_id, project_id, hoy)
        or _tarifa_en_tablas(db, role_label, client_id, project_id, hoy, org_id, is_superadmin)
        or {"billing_rate": None, "source": "not_found", "role_label": role_label}
    )


# ── Serialization helpers ─────────────────────────────────────────────────────────

def serialize_rate_entry(e) -> dict:
    return {
        "id": e.id, "label": e.label,
        "cost_rate": e.cost_rate, "billing_rate": e.billing_rate,
        "escalation_pct": e.escalation_pct or 0.0,
        "valid_from": e.valid_from, "valid_to": e.valid_to,
        "notes": e.notes,
    }


def serialize_rate_override(o) -> dict:
    return {
        "id": o.id, "client_id": o.client_id, "project_id": o.project_id,
        "role_label": o.role_label, "billing_rate": o.billing_rate,
        "valid_from": o.valid_from, "valid_to": o.valid_to, "notes": o.notes,
    }


def serialize_rate_table(t, include_entries: bool = False) -> dict:
    d = {
        "id": t.id, "name": t.name, "description": t.description,
        "applies_to": t.applies_to, "is_default": t.is_default,
        "is_active": t.is_active,
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    }
    if include_entries:
        d["entries"]   = [serialize_rate_entry(e) for e in (t.entries or []) if e.is_active]
        d["overrides"] = [serialize_rate_override(o) for o in getattr(t, "overrides", []) if getattr(o, "is_active", True)]
    else:
        d["entry_count"] = len([e for e in (t.entries or []) if e.is_active])
    return d


# ── La tarifa con la que se factura (revisión 2026-11) ───────────────────────────

def tarifa_de_facturacion(db: Session, usuario, project, fecha, _cache: Optional[dict] = None) -> float:
    """€/h a facturar por las horas de una persona en un proyecto en una fecha.

    Primero las tarifas (excepción del proyecto o del cliente, luego tabla), con
    el perfil de la persona (`job_title`) como rol; si no hay ninguna, la tarifa
    del proyecto; si tampoco, la de la persona. Antes las tarifas no las leía
    nadie: se facturaba siempre por `projects.billing_rate`.
    """
    perfil = (getattr(usuario, "job_title", None) or "").strip()
    if perfil:
        clave = (perfil.lower(), project.id, str(fecha))
        if _cache is not None and clave in _cache:
            r = _cache[clave]
        else:
            r = get_effective_rate(db, perfil, getattr(project, "client_id", None), project.id, str(fecha),
                                   project.organization_id, False)
            if _cache is not None:
                _cache[clave] = r
        # Ronda 2: una tarifa 0 pactada (p. ej. horas sin cargo) es una tarifa, no
        # «sin tarifa»: antes caía a la del proyecto o la persona.
        if r.get("billing_rate") is not None:
            return float(r["billing_rate"])
    return float(project.billing_rate or getattr(usuario, "hourly_rate", 0) or 0)


class TarifasPrecargadas:
    """`tarifa_de_facturacion` y «¿hay tablas de tarifas?» para una LISTA de
    proyectos con tres consultas en total (auditoría 22-11-2026, §7.2: el
    cálculo único del margen en bloque). Mismas reglas que la versión con
    consultas (`_elegir_excepcion`, `_elegir_en_tablas`): excepción de
    proyecto, de cliente, tabla; si no, tarifa del proyecto o de la persona.
    """

    def __init__(self, db: Session, proyectos) -> None:
        from sqlalchemy import or_
        from sqlalchemy.orm import selectinload
        pids = {p.id for p in proyectos}
        cids = {getattr(p, "client_id", None) for p in proyectos} - {None}
        orgs = {p.organization_id for p in proyectos}
        self._exc: dict = {}
        if pids or cids:
            conds = [RateOverride.project_id.in_(pids)] if pids else []
            if cids:
                conds.append(RateOverride.client_id.in_(cids))
            for o in (db.query(RateOverride)
                      .join(RateTable, RateTable.id == RateOverride.table_id)
                      .filter(or_(*conds), RateTable.is_active == True)  # noqa: E712
                      .all()):
                if o.project_id in pids:
                    self._exc.setdefault(("project_id", o.project_id, o.role_label), []).append(o)
                if o.client_id in cids:
                    self._exc.setdefault(("client_id", o.client_id, o.role_label), []).append(o)
        q = db.query(RateTable).options(selectinload(RateTable.entries)).filter(RateTable.is_active == True)  # noqa: E712
        if None not in orgs:
            q = q.filter(RateTable.organization_id.in_(orgs))
        self._tablas = q.all() if orgs else []
        self._cache: dict = {}

    def hay_tarifas(self, org_id) -> bool:
        """Como `profitability_service._hay_tarifas`: alguna tabla activa de esa empresa."""
        return any(t.organization_id == org_id for t in self._tablas)

    def _efectiva(self, perfil: str, project, hoy: str) -> dict:
        for ambito_id, columna in ((project.id, "project_id"), (getattr(project, "client_id", None), "client_id")):
            if ambito_id:
                r = _elegir_excepcion(self._exc.get((columna, ambito_id, perfil), ()), columna, perfil, hoy)
                if r:
                    return r
        org = project.organization_id
        tablas = [t for t in self._tablas if org is None or t.organization_id == org]
        return (_elegir_en_tablas(tablas, perfil, getattr(project, "client_id", None), project.id, hoy)
                or {"billing_rate": None, "source": "not_found", "role_label": perfil})

    def tarifa(self, usuario, project, fecha) -> float:
        perfil = (getattr(usuario, "job_title", None) or "").strip()
        if perfil:
            clave = (perfil.lower(), project.id, str(fecha))
            if clave not in self._cache:
                self._cache[clave] = self._efectiva(perfil, project, str(fecha))
            r = self._cache[clave]
            if r.get("billing_rate") is not None:
                return float(r["billing_rate"])
        return float(project.billing_rate or getattr(usuario, "hourly_rate", 0) or 0)
