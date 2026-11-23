"""
profitability_service.py — DB access layer for profitability & milestone operations.
All db.query/add/commit/delete/flush calls live here; the router stays free of ORM calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.services.settings_service import por_empresa as _pe
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.bookings import ExchangeRate
from app.models.project import Project, ProjectStatus
from app.models.task import TaskStatus
from app.models.user import User
from app.core.codigos_de_error import ErrorConCodigo

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
    # Auditoría 22-11-2026 (A41): un solo resolutor (directo, inverso o cruzado
    # por EUR). Sin tipo ya no es 1,0 en silencio: se anota en
    # `currency_rates_service.TiposQueFaltan` y la respuesta lo avisa.
    from app.services.currency_rates_service import tipo_o_aviso
    rate = tipo_o_aviso(db, from_currency, to_currency, as_of)
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
# Rev. 173: la tabla de pesos es la del valor ganado (una sola).
from app.services.evm_service import PESO_DE_PROGRESO_POR_ESTADO as _PESO_DE_PROGRESO  # noqa: E402


def coste_de_imputacion_en_moneda(db: Session, coste, moneda_usuario: Optional[str], moneda_proyecto: str,
                                  moneda_org: str, fecha, cache: dict) -> float:
    """Coste de una imputacion en la moneda de la organizacion: por la moneda de
    la persona y, si es la de la organizacion, por la del proyecto (respaldo
    cuando no se conoce la de la persona). La usan la cuenta de resultados y la
    evolucion del margen (`app/services/evolucion_del_margen.py`)."""
    raw_cost = float(coste or 0.0)
    if not raw_cost:
        return 0.0
    user_currency = moneda_usuario or moneda_org
    if user_currency != moneda_org:
        return raw_cost * get_fx_rate(db, user_currency, moneda_org, fecha, _cache=cache)
    if moneda_proyecto != moneda_org:
        return raw_cost * get_fx_rate(db, moneda_proyecto, moneda_org, fecha, _cache=cache)
    return raw_cost


def _hay_tarifas(db: Session, project: Project) -> bool:
    from app.models.advanced_config import RateTable
    return db.query(RateTable.id).filter(RateTable.is_active.is_(True),
                                         RateTable.organization_id == project.organization_id).first() is not None


def partidas_de_ingreso(db: Session, project: Project, imputaciones: list, hitos: list,
                        hay_tarifas: Optional[bool] = None, tarifa=None) -> list[tuple]:
    """El ingreso de un proyecto repartido por fecha: ``[(fecha, importe)]``.

    Misma regla y mismo orden, decididos con las imputaciones y los hitos que se
    pasan (los del periodo): con tablas de tarifas, cada hora facturable a su
    tarifa de facturacion; si no sale nada, ``billing_rate`` por hora
    facturable; si no, en proyectos a precio cerrado (`contract_amount`), los
    hitos facturados en su ``billed_at``. Sumadas, son el ingreso del periodo
    (`margen_de_proyectos`, el cálculo único). ``imputaciones``: objetos con
    ``date``, ``hours``, ``is_billable`` y ``user`` (la persona, para la tarifa).
    """
    facturables = [i for i in imputaciones if i.is_billable and i.hours]
    if facturables:
        if hay_tarifas is None:
            hay_tarifas = _hay_tarifas(db, project)
        if hay_tarifas:
            if tarifa is None:   # `tarifa`: la precargada del cálculo en bloque (misma regla)
                from app.services.rate_card_service import tarifa_de_facturacion
                cache: dict = {}

                def tarifa(u, pr, f):
                    return tarifa_de_facturacion(db, u, pr, f, cache)
            partidas = [(i.date, i.hours * tarifa(i.user, project, i.date))
                        for i in facturables if i.user]
            if sum(v for _, v in partidas):
                return partidas
        if project.billing_rate:
            return [(i.date, project.billing_rate * i.hours) for i in facturables]
    if project.contract_amount:
        return [(m.billed_at, float(m.billing_amount or 0)) for m in hitos if m.billed_at]
    return []


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


def _indicadores_evm(project: Project, db: Session, total_cost: float) -> _IndicadoresEVM:
    """Valor ganado del proyecto con el cálculo único (`evm_service`, rev. 173).

    Rentabilidad solo aporta su AC (el coste del rango pedido): PV sale de la
    línea base vigente y EV del avance real de cada tarea, como en la ficha y
    en la cartera. Antes aquí había una tercera copia con PV lineal y EV por
    el porcentaje de tareas terminadas.
    """
    from app.services.evm_service import evm_de_proyecto
    d = evm_de_proyecto(db, project, ac=total_cost)
    return _IndicadoresEVM(
        pv=d["pv"], ev=d["ev"], ac=d["ac"], cpi=d["cpi"], spi=d["spi"], eac=d["eac"],
        etc=d["etc"], vac=d["vac"], cv=d["cv"], sv=d["sv"], bac=d["bac"],
    )


def _bandera_de_riesgo(cpi: Optional[float], margen_al_cierre: float, db=None, org_id=None) -> str:
    """Semaforo del proyecto: critico, aviso u ok.

    Un CPI por debajo de 0,8 o un margen previsto negativo son criticos. Ojo con
    el `cpi and`: sin coste real el CPI es None y no dispara nada, asi que un
    proyecto sin imputaciones nunca sale critico por CPI — solo por margen.
    """
    # 19-11-2026: el CPI con los cortes de EVM_INDEX_* de la empresa
    # (`app.core.umbrales`, métrica «evm»); antes 0,8/0,95 fijos aquí.
    from app.core.umbrales import tono_de
    tono = tono_de("evm", cpi, db, org_id) if cpi else None
    if tono == "danger" or margen_al_cierre < 0:
        return "critical"
    if tono == "warning" or margen_al_cierre < 10:
        return "warning"
    return "ok"


def calc_project_profitability(
    project: Project,
    db: Session,
    imputation_totals: Optional[dict] = None,
    billed_milestones_total: Optional[float] = None,
    desde=None,
    hasta=None,
    cifras: Optional[dict] = None,
) -> dict:
    """La cuenta de resultados y, en `fx_warnings`, los tipos de cambio que
    faltaron (auditoría 22-11-2026, A41: antes se contaban 1:1 en silencio).

    Auditoría 22-11-2026 (§7.2): ingreso, horas y costes salen del cálculo
    único (`margen_de_proyectos.margen_en_bloque`), el mismo del panel, la
    evolución del margen, el EVM y el BI. Para una lista, quien llama calcula
    el bloque una vez y pasa `cifras` de cada proyecto (sin consultas por
    proyecto para el dinero). `imputation_totals` y `billed_milestones_total`
    se aceptan por compatibilidad y ya no se usan: venían sin convertir.
    """
    from app.services.currency_rates_service import TiposQueFaltan
    with TiposQueFaltan() as faltan:
        if cifras is None:
            from app.services.margen_de_proyectos import margen_en_bloque
            cifras = margen_en_bloque(db, [project], desde, hasta)[project.id]
        res = _calc_project_profitability(project, db, cifras)
    res["fx_warnings"] = sorted(set(faltan) | set(cifras.get("fx_warnings") or ()))
    return res


def _calc_project_profitability(project: Project, db: Session, cifras: dict) -> dict:
    """Calculate full P&L for a project from the shared figures (`cifras`)."""
    org_currency = cifras.get("currency") or _pe.moneda_de_empresa(db, registro=project)
    project_currency = getattr(project, "currency", org_currency) or org_currency

    total_hours = float(cifras["hours"])
    billable_hours = float(cifras["billable_hours"])
    internal_cost = float(cifras["internal_cost"])
    billing_revenue = float(cifras["revenue"])
    externos = {"gastos": cifras["expenses_cost"], "subcontrata": cifras["subcontract_cost"],
                "alm": cifras["alm_cost"]}
    total_cost = float(cifras["total_cost"])

    gross_margin = billing_revenue - total_cost
    margin_pct = (gross_margin / billing_revenue * 100) if billing_revenue > 0 else 0

    budget_used_pct = 0
    if project.budget_amount and project.budget_amount > 0:
        budget_used_pct = (total_cost / project.budget_amount) * 100

    progress = _progreso_por_tareas(project)
    forecast_cost = _coste_previsto(
        total_cost, progress, total_hours, project.budget_hours
    )
    evm = _indicadores_evm(project, db, total_cost)

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
        "internal_cost": round(internal_cost, 2),          # personal (imputaciones)
        "expenses_cost": externos["gastos"],
        "subcontract_cost": externos["subcontrata"],
        "alm_cost": externos.get("alm", 0.0),          # licencias y equipos (ALM, fase 3)
        "total_cost": round(total_cost, 2),
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
        "evm_no_schedule": evm.pv is None,
        "eac": evm.eac,
        "etc": evm.etc,
        "vac": evm.vac,
        "margin_at_completion": margin_at_completion,
        "risk_flag": _bandera_de_riesgo(evm.cpi, margin_at_completion, db, project.organization_id),
    }


# ── Imputation queries ─────────────────────────────────────────────────────────

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
        raise ErrorConCodigo("hito_facturado_no_eliminable")
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
