"""
profitability_service.py — DB access layer for profitability & milestone operations.
All db.query/add/commit/delete/flush calls live here; the router stays free of ORM calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.bookings import ExchangeRate
from app.models.project import Project, ProjectStatus
from app.models.task import TaskStatus
from app.models.user import User
from app.core import timeutil

# ── FX helper ──────────────────────────────────────────────────────────────────

# Kept as empty module-level name for backward compatibility with existing imports/tests.
# Production code uses a call-local cache (passed as parameter) to avoid shared mutable state.
_fx_cache: dict = {}


def get_fx_rate(
    db: Session,
    from_currency: str,
    to_currency: str,
    as_of: date,
    _cache: dict | None = None,
) -> float:
    """Return FX rate for *from_currency* → *to_currency* on *as_of*.

    *_cache* is an optional call-local dict used to avoid redundant DB hits within
    the same computation.  Pass an explicit dict from the caller; never share one
    across concurrent requests.
    """
    if from_currency == to_currency:
        return 1.0
    key = (from_currency, to_currency, as_of)
    if _cache is not None and key in _cache:
        return _cache[key]
    row = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_currency,
            ExchangeRate.to_currency == to_currency,
            ExchangeRate.effective_date <= as_of,
        )
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.organization_id.is_(None))
        .first()
    )
    rate = row.rate if row else 1.0
    if _cache is not None:
        _cache[key] = rate
    return rate


# ── Cuenta de resultados de un proyecto ──────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `calc_project_profitability` era complejidad
# 23 y devuelve 38 cifras de dinero. Se ha partido en las fases que ya tenia
# dentro, cada una con nombre:
#
#   1. totales de imputacion, convertidos a la moneda de la organizacion
#   2. ingreso facturable (por tarifa/hora o por hitos facturados)
#   3. progreso, ponderado por estado de tarea
#   4. coste previsto
#   5. porcentaje planificado por calendario
#   6. indicadores EVM (PV, EV, AC, CPI, SPI, EAC, ETC, VAC, CV, SV)
#   7. bandera de riesgo
#
# La aritmetica es la misma linea por linea. La red es
# `tests/test_profitability_pnl.py`, donde las cifras primarias estan calculadas
# a mano y las derivadas se comprueban contra las identidades EVM estandar
# (CPI = EV/AC, EAC = AC + (BAC-EV)/CPI, ETC = EAC-AC, VAC = BAC-EAC, CV = EV-AC,
# SV = EV-PV) — que es lo que caza un refactor que intercambie operandos.


# El peso con el que cada estado de tarea cuenta hacia el progreso. Estaba como
# cadena de `elif`; los siete estados de `TaskStatus` estan aqui, y el test
# `test_la_tabla_de_pesos_cubre_todos_los_estados` lo comprueba para que un
# estado nuevo no entre valiendo cero sin que nadie lo decida.
_PESO_DE_PROGRESO = {
    TaskStatus.done: 1.0,
    TaskStatus.in_review: 0.8,
    TaskStatus.in_progress: 0.5,
    TaskStatus.todo: 0.0,
    TaskStatus.backlog: 0.0,
    TaskStatus.blocked: 0.0,
    TaskStatus.cancelled: 0.0,
}


def _totales_de_imputacion(
    project: Project,
    db: Session,
    imputation_totals: Optional[dict],
    project_currency: str,
    org_currency: str,
    desde=None,
    hasta=None,
) -> tuple[float, float, float]:
    """Horas totales, horas facturables y coste interno en moneda de la organizacion.

    Se recalcula desde las imputaciones —en vez de usar los totales que llegan
    ya sumados— cuando no llegan, o cuando la moneda del proyecto no es la de la
    organizacion: en ese caso los totales precalculados vendrian sin convertir y
    el coste saldria en la moneda equivocada, que es un error silencioso de los
    caros.
    """
    if imputation_totals is not None and project_currency == org_currency:
        return (
            float(imputation_totals.get("total_hours") or 0),
            float(imputation_totals.get("billable_hours") or 0),
            float(imputation_totals.get("internal_cost") or 0),
        )

    # Cache local a la llamada: nunca compartida entre peticiones concurrentes.
    _local_fx_cache: dict = {}
    imps = get_project_imputations(db, project.id, desde, hasta)
    total_hours = sum(i.hours for i in imps)
    billable_hours = sum(i.hours for i in imps if i.is_billable)

    # Se cargan los usuarios de golpe para poder leer su moneda al convertir.
    user_ids = {i.user_id for i in imps if i.user_id}
    if user_ids:
        user_currency_map = {
            u.id: (getattr(u, "currency", None) or org_currency)
            for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }
    else:
        user_currency_map = {}

    internal_cost = 0.0
    for i in imps:
        raw_cost = i.cost_amount or 0.0
        if raw_cost:
            user_currency = user_currency_map.get(i.user_id, org_currency) or org_currency
            if user_currency != org_currency:
                fx = get_fx_rate(db, user_currency, org_currency, i.date, _cache=_local_fx_cache)
                raw_cost = raw_cost * fx
            elif project_currency != org_currency:
                # Respaldo: se convierte por la moneda del proyecto cuando no se
                # conoce la del usuario.
                fx = get_fx_rate(db, project_currency, org_currency, i.date, _cache=_local_fx_cache)
                raw_cost = raw_cost * fx
        internal_cost += raw_cost

    return total_hours, billable_hours, internal_cost


def _ingreso_facturable(
    project: Project,
    db: Session,
    billable_hours: float,
    billed_milestones_total: Optional[float],
    desde=None,
    hasta=None,
) -> float:
    """Ingreso reconocido: por tarifa/hora, o por hitos facturados.

    El orden importa y es el original: si el proyecto tiene tarifa por hora y
    horas facturables, manda la tarifa. Los hitos solo entran en los proyectos a
    precio cerrado (`contract_amount`).
    """
    if project.billing_rate and billable_hours:
        return project.billing_rate * billable_hours
    if project.contract_amount:
        if billed_milestones_total is None:
            milestones = get_billed_milestones(db, project.id, desde, hasta)
            return sum(m.billing_amount or 0 for m in milestones)
        return float(billed_milestones_total or 0)
    return 0


def _progreso_por_tareas(project: Project) -> float:
    """Progreso en porcentaje, ponderando cada tarea por su estado.

    Sin tareas devuelve 0: no hay de donde deducir avance. Eso arrastra al EVM
    —EV sale 0 y con el CPI y SPI— y es correcto, porque un proyecto sin tareas
    no tiene valor ganado que medir.
    """
    tasks = project.tasks or []
    if not tasks:
        return 0
    ponderado = sum(_PESO_DE_PROGRESO.get(t.status, 0.0) for t in tasks)
    return (ponderado / len(tasks)) * 100


def _coste_previsto(
    internal_cost: float, progress: float, total_hours: float, budget_hours
) -> float:
    """Coste total previsto al cierre.

    Dos caminos, y el umbral del 5 % de progreso no es arbitrario: extrapolar
    linealmente desde un avance minimo multiplica el coste por veinte o mas. Por
    debajo de ahi se extrapola por horas presupuestadas, que es mas estable.
    """
    if progress >= 5.0:
        remaining_pct = 100 - progress
        return round(internal_cost + (internal_cost * remaining_pct / progress), 2)
    if total_hours > 0 and budget_hours:
        return round((internal_cost / total_hours) * budget_hours, 2)
    return 0


def _porcentaje_planificado(project: Project, hoy: date) -> Optional[float]:
    """Que porcentaje del calendario deberia estar consumido hoy.

    Devuelve None cuando el proyecto no tiene fechas utilizables. Ese None se
    propaga a PV, SPI y SV, y el resultado lo marca con `evm_no_schedule`: es la
    diferencia entre «va en plazo» y «no se puede saber», y mezclarlas daria un
    SPI inventado.
    """
    if not (project.start_date and project.end_date_planned
            and project.end_date_planned > project.start_date):
        return None
    total_days = (project.end_date_planned - project.start_date).days
    elapsed_days = max(0, (hoy - project.start_date).days)
    return min(100, (elapsed_days / total_days) * 100)


@dataclass(slots=True)
class _IndicadoresEVM:
    """Los indicadores de valor ganado. `pv`, `spi` y `sv` son None sin calendario."""

    pv: Optional[float]
    ev: float
    ac: float
    cpi: Optional[float]
    spi: Optional[float]
    eac: float
    etc: float
    vac: float
    cv: float
    sv: Optional[float]
    bac: float


def _indicadores_evm(
    project: Project,
    internal_cost: float,
    progress: float,
    planned_pct: Optional[float],
    forecast_cost: float,
) -> _IndicadoresEVM:
    """Calcula los indicadores EVM segun las formulas estandar."""
    pv = round((project.budget_amount or 0) * planned_pct / 100, 2) if planned_pct is not None else None
    ev = round((project.budget_amount or 0) * progress / 100, 2) if progress > 0 else 0
    ac = round(internal_cost, 2)

    cpi = round(ev / ac, 3) if ac > 0 else None
    spi = round(ev / pv, 3) if (pv is not None and pv > 0) else None

    bac = project.budget_amount or forecast_cost or 0
    if cpi and cpi > 0:
        eac = round(ac + (bac - ev) / cpi, 2)
    elif progress >= 1.0:
        # Sin CPI (coste real cero) pero con avance: se extrapola por progreso.
        eac = round(ac / (progress / 100), 2)
    else:
        eac = bac

    return _IndicadoresEVM(
        pv=pv, ev=ev, ac=ac, cpi=cpi, spi=spi, eac=eac,
        etc=round(max(eac - ac, 0), 2),
        vac=round(bac - eac, 2),
        cv=round(ev - ac, 2),
        sv=round(ev - pv, 2) if pv is not None else None,
        bac=bac,
    )


def _bandera_de_riesgo(cpi: Optional[float], margen_al_cierre: float) -> str:
    """Semaforo del proyecto: critico, aviso u ok.

    Un CPI por debajo de 0,8 o un margen previsto negativo son criticos. Ojo con
    el `cpi and`: sin coste real el CPI es None y no dispara nada, asi que un
    proyecto sin imputaciones nunca sale critico por CPI — solo por margen.
    """
    if (cpi and cpi < 0.8) or margen_al_cierre < 0:
        return "critical"
    if (cpi and cpi < 0.95) or margen_al_cierre < 10:
        return "warning"
    return "ok"


def calc_project_profitability(
    project: Project,
    db: Session,
    imputation_totals: Optional[dict] = None,
    billed_milestones_total: Optional[float] = None,
    desde=None,
    hasta=None,
) -> dict:
    """Calculate full P&L for a project (en el rango `desde`–`hasta` si se da).

    Costs are normalised to *settings.DEFAULT_CURRENCY* using the exchange rate
    effective on the imputation date.
    """
    org_currency = settings.DEFAULT_CURRENCY
    project_currency = getattr(project, "currency", org_currency) or org_currency

    total_hours, billable_hours, internal_cost = _totales_de_imputacion(
        project, db, imputation_totals, project_currency, org_currency, desde, hasta
    )
    billing_revenue = _ingreso_facturable(
        project, db, billable_hours, billed_milestones_total, desde, hasta
    )

    gross_margin = billing_revenue - internal_cost
    margin_pct = (gross_margin / billing_revenue * 100) if billing_revenue > 0 else 0

    budget_used_pct = 0
    if project.budget_amount and project.budget_amount > 0:
        budget_used_pct = (internal_cost / project.budget_amount) * 100

    progress = _progreso_por_tareas(project)
    forecast_cost = _coste_previsto(
        internal_cost, progress, total_hours, project.budget_hours
    )
    planned_pct = _porcentaje_planificado(project, timeutil.today())
    evm = _indicadores_evm(project, internal_cost, progress, planned_pct, forecast_cost)

    margin_at_completion = 0
    if billing_revenue > 0 and evm.eac > 0:
        margin_at_completion = round((billing_revenue - evm.eac) / billing_revenue * 100, 1)

    return {
        "project_id": project.id,
        "project_code": project.code,
        "project_name": project.name,
        "client_name": project.client_name,
        "department": project.department,
        "status": project.status,
        "billing_type": project.billing_type or "time_material",
        "is_billable": project.is_billable,
        "project_currency": project_currency,
        "reporting_currency": org_currency,
        "total_hours": round(total_hours, 1),
        "billable_hours": round(billable_hours, 1),
        "budget_hours": project.budget_hours,
        "hours_used_pct": round((total_hours / project.budget_hours * 100), 1) if project.budget_hours else None,
        "internal_cost": round(internal_cost, 2),
        "billing_revenue": round(billing_revenue, 2),
        "gross_margin": round(gross_margin, 2),
        "margin_pct": round(margin_pct, 1),
        "budget_amount": project.budget_amount,
        "contract_amount": project.contract_amount,
        "budget_used_pct": round(budget_used_pct, 1),
        "forecast_cost": round(forecast_cost, 2),
        "billing_rate": project.billing_rate,
        "avg_cost_rate": round(internal_cost / total_hours, 2) if total_hours > 0 else 0,
        "progress_pct": round(progress, 1),
        "pv": evm.pv,
        "ev": evm.ev,
        "ac": evm.ac,
        "cpi": evm.cpi,
        "spi": evm.spi,
        "cv": evm.cv,
        "sv": evm.sv,
        "evm_no_schedule": planned_pct is None,
        "eac": evm.eac,
        "etc": evm.etc,
        "vac": evm.vac,
        "margin_at_completion": margin_at_completion,
        "risk_flag": _bandera_de_riesgo(evm.cpi, margin_at_completion),
    }


# ── Imputation queries ─────────────────────────────────────────────────────────

def _en_rango_imp(q, desde=None, hasta=None):
    """Auditoria 2026-11: el selector de periodo del panel de finanzas no hacia
    nada; el rango llega ahora hasta las imputaciones (por su fecha)…"""
    if desde:
        q = q.filter(Imputation.date >= desde)
    if hasta:
        q = q.filter(Imputation.date <= hasta)
    return q


def _en_rango_hito(q, desde=None, hasta=None):
    """…y hasta los hitos facturados (por la fecha en que se facturaron)."""
    if desde:
        q = q.filter(ProjectMilestone.billed_at >= desde)
    if hasta:
        q = q.filter(ProjectMilestone.billed_at <= hasta)
    return q


def get_project_imputations(db: Session, project_id: str, desde=None, hasta=None) -> list:
    return _en_rango_imp(
        db.query(Imputation).filter(Imputation.project_id == project_id, Imputation.is_active == True),
        desde, hasta,
    ).all()


def get_imputation_totals_by_project(db: Session, project_ids: list, desde=None, hasta=None) -> dict:
    if not project_ids:
        return {}
    rows = (
        db.query(
            Imputation.project_id.label("project_id"),
            func.sum(Imputation.hours).label("total_hours"),
            func.sum(case((Imputation.is_billable == True, Imputation.hours), else_=0)).label("billable_hours"),
            func.sum(Imputation.cost_amount).label("internal_cost"),
        )
        .filter(Imputation.project_id.in_(project_ids), Imputation.is_active == True,
                *([Imputation.date >= desde] if desde else []), *([Imputation.date <= hasta] if hasta else []))
        .group_by(Imputation.project_id)
        .all()
    )
    return {
        r.project_id: {
            "total_hours": r.total_hours,
            "billable_hours": r.billable_hours,
            "internal_cost": r.internal_cost,
        }
        for r in rows
    }


def get_imputations_by_person(db: Session, project_id: str) -> list:
    return (
        db.query(
            Imputation.user_id,
            User.full_name,
            func.sum(Imputation.hours).label("hours"),
            func.sum(Imputation.cost_amount).label("cost"),
        )
        .join(User, User.id == Imputation.user_id)
        .filter(Imputation.project_id == project_id, Imputation.is_active == True)
        .group_by(Imputation.user_id, User.full_name)
        .all()
    )


def get_imputations_by_day(db: Session, project_id: str) -> list:
    return (
        db.query(
            Imputation.date,
            func.sum(Imputation.hours).label("hours"),
            func.sum(Imputation.cost_amount).label("cost"),
        )
        .filter(Imputation.project_id == project_id, Imputation.is_active == True)
        .group_by(Imputation.date)
        .order_by(Imputation.date)
        .all()
    )


# ── Milestone queries ──────────────────────────────────────────────────────────

def get_billed_milestones(db: Session, project_id: str, desde=None, hasta=None) -> list:
    return _en_rango_hito(
        db.query(ProjectMilestone).filter(
            ProjectMilestone.project_id == project_id,
            ProjectMilestone.is_active == True,
            ProjectMilestone.is_billed == True,
        ),
        desde, hasta,
    ).all()


def get_billed_milestones_total_by_project(db: Session, project_ids: list, desde=None, hasta=None) -> dict:
    if not project_ids:
        return {}
    rows = (
        db.query(
            ProjectMilestone.project_id.label("project_id"),
            func.sum(ProjectMilestone.billing_amount).label("billing_revenue"),
        )
        .filter(
            ProjectMilestone.project_id.in_(project_ids),
            ProjectMilestone.is_active == True,
            ProjectMilestone.is_billed == True,
            *([ProjectMilestone.billed_at >= desde] if desde else []),
            *([ProjectMilestone.billed_at <= hasta] if hasta else []),
        )
        .group_by(ProjectMilestone.project_id)
        .all()
    )
    return {r.project_id: r.billing_revenue for r in rows}


def list_milestones(db: Session, project_id: str) -> list:
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.project_id == project_id, ProjectMilestone.is_active == True)
        .order_by(ProjectMilestone.sort_order)
        .all()
    )


def get_milestone(db: Session, milestone_id: str, project_id: str) -> Optional[ProjectMilestone]:
    return (
        db.query(ProjectMilestone)
        .filter(
            ProjectMilestone.id == milestone_id,
            ProjectMilestone.project_id == project_id,
            ProjectMilestone.is_active == True,
        )
        .first()
    )


def create_milestone(db: Session, project_id: str, data: dict) -> ProjectMilestone:
    m = ProjectMilestone(project_id=project_id, **data)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_milestone(db: Session, m: ProjectMilestone, updates: dict) -> ProjectMilestone:
    for k, v in updates.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


def delete_milestone(db: Session, m: ProjectMilestone) -> None:
    if m.is_billed or m.invoice_id:
        raise ValueError("No se puede eliminar un hito ya facturado")
    m.is_active = False
    db.commit()


# ── Project queries ────────────────────────────────────────────────────────────

def get_summary_projects(db: Session, status: Optional[str] = None) -> list:
    q = db.query(Project).options(joinedload(Project.tasks))
    if status:
        q = q.filter(Project.status == status)
    else:
        q = q.filter(Project.status.in_([ProjectStatus.active, ProjectStatus.closed]))
    return q.all()


def get_project_with_tasks(db: Session, project_id: str) -> Optional[Project]:
    return (
        db.query(Project)
        .options(joinedload(Project.tasks), joinedload(Project.project_manager))
        .filter(Project.id == project_id)
        .first()
    )
