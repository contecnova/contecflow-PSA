"""
revenue_service.py — ASC 606 / IFRS 15 Revenue Recognition service.

4 recognition methods:
  over_time     — T&M: recognized proportional to approved timesheet hours/cost
  milestone     — Fixed-price: recognized when milestone is marked completed
  consumption   — Hourly bag: same as over_time but capped at bag size
  straight_line — Retainer: 1/N allocation per calendar month

Design invariants:
  - RevenueEntry records are never deleted (immutable accounting log)
  - Corrections create a new entry of type 'reversal' + a corrected entry
  - RevenuePeriodClose locks entries for a month; new entries blocked for closed periods
  - TenantSession auto-filters by organization_id for API-path queries
  - Celery tasks use SessionLocal() directly — iterate all active contracts
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.revenue import (
    ASCMethod, EntryType, RevenueContract, RevenueEntry,
    RevenueObligation, RevenuePeriodClose,
)
from app.models.financial import ProjectMilestone
from app.models.project import Project
from app.core import timeutil

# Un dato que falta —un proyecto sin tarifa— no puede ser silencio: quien opera
# el cierre mensual tiene que poder ver qué contratos no se han podido reconocer.
_logger = logging.getLogger("contecflow.revenue")


# ── Contract CRUD ──────────────────────────────────────────────────────────────

def list_contracts(db: Session, project_id: Optional[str] = None):
    q = db.query(RevenueContract)
    if project_id:
        q = q.filter(RevenueContract.project_id == project_id)
    return q.order_by(RevenueContract.created_at.desc()).all()


def get_contract(db: Session, contract_id: str) -> RevenueContract:
    c = db.query(RevenueContract).filter(RevenueContract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Contrato de reconocimiento no encontrado")
    return c


def create_contract(db: Session, organization_id: str, data: dict) -> RevenueContract:
    c = RevenueContract(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        **data,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_contract(db: Session, contract_id: str, data: dict) -> RevenueContract:
    c = get_contract(db, contract_id)
    allowed = {
        "name", "contract_value", "currency", "method",
        "start_date", "end_date", "duration_months", "is_active", "notes",
    }
    for k, v in data.items():
        if k in allowed:
            setattr(c, k, v)
    db.commit()
    return c


def delete_contract(db: Session, contract_id: str) -> None:
    c = get_contract(db, contract_id)
    has_entries = db.query(RevenueEntry).filter(RevenueEntry.rev_contract_id == contract_id).first()
    if has_entries:
        raise HTTPException(400, "No se puede eliminar un contrato con entradas contables")
    db.delete(c)
    db.commit()


# ── Obligation CRUD ────────────────────────────────────────────────────────────

def list_obligations(db: Session, contract_id: str):
    return (
        db.query(RevenueObligation)
        .filter(RevenueObligation.contract_id == contract_id)
        .order_by(RevenueObligation.created_at)
        .all()
    )


def create_obligation(db: Session, contract_id: str, data: dict) -> RevenueObligation:
    c = get_contract(db, contract_id)
    ob = RevenueObligation(
        id=str(uuid.uuid4()),
        organization_id=c.organization_id,
        contract_id=contract_id,
        **data,
    )
    db.add(ob)
    db.commit()
    db.refresh(ob)
    return ob


def update_obligation(db: Session, obligation_id: str, data: dict) -> RevenueObligation:
    ob = db.query(RevenueObligation).filter(RevenueObligation.id == obligation_id).first()
    if not ob:
        raise HTTPException(404, "Obligación no encontrada")
    allowed = {"name", "allocated_pct", "allocated_amount", "is_satisfied", "satisfied_date", "milestone_id"}
    for k, v in data.items():
        if k in allowed:
            setattr(ob, k, v)
    db.commit()
    return ob


def delete_obligation(db: Session, obligation_id: str) -> None:
    ob = db.query(RevenueObligation).filter(RevenueObligation.id == obligation_id).first()
    if not ob:
        raise HTTPException(404, "Obligación no encontrada")
    db.delete(ob)
    db.commit()


# ── Period Close ───────────────────────────────────────────────────────────────

def list_period_closes(db: Session):
    return (
        db.query(RevenuePeriodClose)
        .order_by(RevenuePeriodClose.period_year.desc(), RevenuePeriodClose.period_month.desc())
        .all()
    )


def is_period_closed(db: Session, year: int, month: int, organization_id: Optional[str] = None) -> bool:
    q = db.query(RevenuePeriodClose).filter(
        RevenuePeriodClose.period_year == year,
        RevenuePeriodClose.period_month == month,
    )
    if organization_id:
        q = q.filter(RevenuePeriodClose.organization_id == organization_id)
    return q.first() is not None


def close_period(db: Session, organization_id: str, year: int, month: int, user_id: str, notes: Optional[str] = None) -> RevenuePeriodClose:
    if is_period_closed(db, year, month, organization_id):
        raise HTTPException(400, f"El período {year}-{month:02d} ya está cerrado")
    pc = RevenuePeriodClose(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        period_year=year,
        period_month=month,
        closed_by=user_id,
        notes=notes,
    )
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


def reopen_period(db: Session, organization_id: str, year: int, month: int) -> None:
    pc = (
        db.query(RevenuePeriodClose)
        .filter(
            RevenuePeriodClose.organization_id == organization_id,
            RevenuePeriodClose.period_year == year,
            RevenuePeriodClose.period_month == month,
        )
        .first()
    )
    if not pc:
        raise HTTPException(404, "Período no encontrado o no cerrado")
    db.delete(pc)
    db.commit()


# ── Entry helpers ──────────────────────────────────────────────────────────────

def list_entries(
    db: Session,
    contract_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
):
    q = db.query(RevenueEntry)
    if contract_id:
        q = q.filter(RevenueEntry.rev_contract_id == contract_id)
    if year:
        q = q.filter(RevenueEntry.period_year == year)
    if month:
        q = q.filter(RevenueEntry.period_month == month)
    return q.order_by(RevenueEntry.created_at.desc()).all()


def _create_entry(
    db: Session,
    contract: RevenueContract,
    entry_type: EntryType,
    amount: float,
    year: int,
    month: int,
    user_id: Optional[str] = None,
    milestone_id: Optional[str] = None,
    description: Optional[str] = None,
    reverses_entry_id: Optional[str] = None,
) -> RevenueEntry:
    entry = RevenueEntry(
        id=str(uuid.uuid4()),
        organization_id=contract.organization_id,
        rev_contract_id=contract.id,
        entry_type=entry_type,
        amount=amount,
        currency=contract.currency,
        period_year=year,
        period_month=month,
        milestone_id=milestone_id,
        description=description,
        reverses_entry_id=reverses_entry_id,
        created_by=user_id,
    )
    db.add(entry)
    return entry


def reverse_entry(db: Session, entry_id: str, user_id: str) -> RevenueEntry:
    orig = db.query(RevenueEntry).filter(RevenueEntry.id == entry_id).first()
    if not orig:
        raise HTTPException(404, "Entrada no encontrada")
    if orig.entry_type == EntryType.reversal:
        raise HTTPException(400, "No se puede revertir una entrada de tipo 'reversal'")
    contract = get_contract(db, orig.rev_contract_id)
    if is_period_closed(db, orig.period_year, orig.period_month, contract.organization_id):
        raise HTTPException(400, "No se puede revertir una entrada de un período cerrado")
    rev = _create_entry(
        db, contract,
        entry_type=EntryType.reversal,
        amount=-orig.amount,
        year=orig.period_year,
        month=orig.period_month,
        user_id=user_id,
        milestone_id=orig.milestone_id,
        description=f"Reversal de entrada {entry_id[:8]}",
        reverses_entry_id=entry_id,
    )
    db.commit()
    return rev


# ── Recognition: milestone trigger ────────────────────────────────────────────

def recognize_on_milestone(db: Session, milestone_id: str, user_id: Optional[str] = None) -> None:
    """
    Called from milestone_service.complete_milestone() after commit.
    Finds any active RevenueContract linked to the milestone's project that
    uses method=milestone, and creates a recognized entry for each matching
    RevenueObligation.
    """
    milestone = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not milestone:
        return

    today = timeutil.today()
    year, month = today.year, today.month

    contracts = (
        db.query(RevenueContract)
        .filter(
            RevenueContract.project_id == milestone.project_id,
            RevenueContract.method == ASCMethod.milestone,
            RevenueContract.is_active == True,
        )
        .all()
    )

    for contract in contracts:
        if is_period_closed(db, year, month, contract.organization_id):
            continue

        obligations = (
            db.query(RevenueObligation)
            .filter(
                RevenueObligation.contract_id == contract.id,
                RevenueObligation.milestone_id == milestone_id,
                RevenueObligation.is_satisfied == False,
            )
            .all()
        )

        if not obligations:
            # No obligation mapped — recognize the full contract value / milestone pct
            amount = (
                (milestone.billing_pct or 0) / 100 * contract.contract_value
                if milestone.billing_pct
                else 0.0
            )
            if amount > 0:
                _create_entry(
                    db, contract, EntryType.recognized, amount,
                    year, month, user_id, milestone_id,
                    f"Hito completado: {milestone.name}",
                )
        else:
            for ob in obligations:
                amount = ob.allocated_amount or (ob.allocated_pct / 100 * contract.contract_value)
                _create_entry(
                    db, contract, EntryType.recognized, round(amount, 2),
                    year, month, user_id, milestone_id,
                    f"Obligación satisfecha: {ob.name}",
                )
                ob.is_satisfied = True
                ob.satisfied_date = today

    if contracts:
        try:
            db.commit()
        except Exception:
            db.rollback()


# ── Recognition: over_time / consumption ──────────────────────────────────────

def _ya_reconocido(db: Session, contract: RevenueContract, year: int, month: int) -> bool:
    """¿Existe ya asiento de reconocimiento para este contrato y este periodo?

    Auditoría 2026-08. Extraído de `_recognize_straight_line`, que era la única
    de las dos vías de reconocimiento que lo comprobaba. Compartirlo evita que la
    próxima vía que se añada vuelva a olvidarlo, que es lo que pasó con
    `_recognize_over_time`.

    Esta guarda NO basta por sí sola contra concurrencia —dos transacciones
    pueden leer «no hay» y ambas insertar—, por eso la tabla lleva además una
    restricción única sobre (contrato, año, mes, tipo). Ver la revisión 091.
    """
    return (
        db.query(RevenueEntry.id)
        .filter(
            RevenueEntry.rev_contract_id == contract.id,
            RevenueEntry.period_year == year,
            RevenueEntry.period_month == month,
            RevenueEntry.entry_type == EntryType.recognized,
        )
        .first()
        is not None
    )


def _recognize_over_time(db: Session, contract: RevenueContract, year: int, month: int, user_id: Optional[str]) -> float:
    """T&M / consumo: horas imputadas APROBADAS del periodo × tarifa del proyecto.

    Auditoría 2026-08. Esta función tenía tres defectos, y el primero la dejaba
    inservible por completo:

    1. Leía la tarifa con
       `getattr(proj, "hourly_rate", None) or getattr(proj, "daily_rate", None) or 0.0`
       y **ninguno de esos dos campos existe** en `Project` — el real es
       `billing_rate`. Como los dos `getattr` llevaban valor por defecto, no
       lanzaba: `avg_rate` valía siempre 0.0, `recognized` siempre 0.0 y el
       `if recognized > 0` nunca entraba. El reconocimiento ASC 606 de T&M y
       consumo llevaba reconociendo **cero euros, siempre**, sin un solo error en
       los registros. Comprobado ejecutándolo: el lote creaba 0 asientos.
       Ahora se accede al atributo directamente, sin `getattr` con defecto, para
       que un renombrado futuro lance en vez de devolver silencio.

    2. No comprobaba si ya existía asiento para (contrato, periodo), así que una
       segunda pasada del lote reconocía otra vez los mismos ingresos hasta
       agotar el valor del contrato. Su hermana `_recognize_straight_line`, 40
       líneas más abajo, sí lo hacía: era un olvido, no una decisión.

    3. Su propia documentación decía «approved imputation hours» y la consulta no
       filtraba `is_approved`. Reconocer ingresos sobre horas todavía sin aprobar
       es precisamente lo que un auditor de ASC 606 / IFRS 15 marca.

    Sobre la tarifa: se usa `billing_rate` del proyecto, que es la pactada con el
    cliente y la fuente que ya usan el resto de módulos (`dashboard_service`,
    `bi_intelligence_service`, `cab_service`). Una tarifa por rol vía
    `rate_card_service.get_effective_rate` sería más precisa, pero exige resolver
    el rol de cada persona imputación a imputación; queda como mejora, no se
    inventa aquí. Si el proyecto no tiene tarifa no se reconoce nada y se AVISA:
    antes ese caso era indistinguible del «no hay horas».
    """
    from sqlalchemy import extract

    from app.models.imputation import Imputation

    # Sólo horas aprobadas: es lo que dice el contrato de esta función y lo que
    # exige la norma. `is_approved` puede ser NULL en filas antiguas, así que se
    # compara explícitamente con True.
    total_hours = (
        db.query(func.sum(Imputation.hours))
        .filter(
            Imputation.project_id == contract.project_id,
            Imputation.is_approved.is_(True),
            extract("year", Imputation.date) == year,
            extract("month", Imputation.date) == month,
        )
        .scalar()
        or 0.0
    )

    if total_hours <= 0:
        return 0.0

    # Idempotencia: mismo criterio que `_recognize_straight_line`. Sin esto, un
    # reintento de Celery o un disparo manual duplicaban los ingresos del mes.
    if _ya_reconocido(db, contract, year, month):
        return 0.0

    proj = db.query(Project).filter(Project.id == contract.project_id).first()
    if proj is None:
        _logger.warning(
            "Contrato %s apunta a un proyecto inexistente (%s): no se reconoce nada",
            contract.id, contract.project_id,
        )
        return 0.0

    # Acceso directo, sin `getattr(..., None)`: si el campo se renombra, que
    # falle en voz alta. Ése fue exactamente el defecto que ocultó este fallo.
    avg_rate = float(proj.billing_rate or 0.0)
    if avg_rate <= 0:
        # Antes esto era silencio absoluto. Es un dato que falta, no un cero
        # legítimo, y quien opera el cierre necesita saberlo.
        _logger.warning(
            "Proyecto %s sin billing_rate: %.1f h del contrato %s no se pueden "
            "reconocer en %d-%02d",
            proj.id, total_hours, contract.id, year, month,
        )
        return 0.0

    recognized = round(total_hours * avg_rate, 2)

    # Tope en el valor de contrato que queda por reconocer.
    already_recognized = (
        db.query(func.sum(RevenueEntry.amount))
        .filter(
            RevenueEntry.rev_contract_id == contract.id,
            RevenueEntry.entry_type.in_([EntryType.recognized, EntryType.reversal]),
        )
        .scalar()
        or 0.0
    )
    remaining = max(contract.contract_value - already_recognized, 0.0)
    recognized = min(recognized, remaining)

    if recognized > 0:
        _create_entry(
            db, contract, EntryType.recognized, recognized, year, month, user_id,
            description=f"T&M reconocido: {total_hours:.1f}h × {avg_rate}",
        )
    return recognized


def _recognize_straight_line(db: Session, contract: RevenueContract, year: int, month: int, user_id: Optional[str]) -> float:
    """
    Retainer: 1/N per month. N = duration_months or derived from start/end.
    """
    n = contract.duration_months
    if not n and contract.start_date and contract.end_date:
        delta = (contract.end_date.year - contract.start_date.year) * 12 + (contract.end_date.month - contract.start_date.month) + 1
        n = max(delta, 1)
    if not n or n <= 0:
        return 0.0

    # Check if this period is within the contract dates
    period_date = date(year, month, 1)
    if contract.start_date and period_date < date(contract.start_date.year, contract.start_date.month, 1):
        return 0.0
    if contract.end_date and period_date > date(contract.end_date.year, contract.end_date.month, 1):
        return 0.0

    # Evitar doble reconocimiento del mismo periodo. Extraído a `_ya_reconocido`
    # para que las dos vías de reconocimiento compartan el criterio: estaba sólo
    # aquí y `_recognize_over_time` se lo había dejado.
    if _ya_reconocido(db, contract, year, month):
        return 0.0

    amount = round(contract.contract_value / n, 2)
    _create_entry(
        db, contract, EntryType.recognized, amount, year, month, user_id,
        description=f"Retainer {year}-{month:02d}: 1/{n} del contrato",
    )
    return amount


# ── Monthly batch recognition (Celery) ────────────────────────────────────────

def run_monthly_recognition(
    db: Session,
    year: int,
    month: int,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> dict:
    """Reconoce el periodo indicado para los contratos activos.

    Los contratos por HITOS se excluyen: se reconocen al completarse el hito.

    `organization_id` acota el lote a una organización (auditoría 2026-08). Hace
    falta porque el cierre ya no se dispara una vez para todo el mundo: el mes de
    cada organización empieza en SU zona horaria, así que la tarea recorre las
    organizaciones y llama aquí una vez por cada una. Sin este filtro, cada
    llamada recorrería los contratos de todas las demás — N veces el trabajo, y
    reconociendo el periodo de una organización con el calendario de otra.

    Sin `organization_id` mantiene el comportamiento anterior (todas), que es lo
    que usan el endpoint de recálculo manual y los tests.
    """
    q = db.query(RevenueContract).filter(
        RevenueContract.is_active == True,
        RevenueContract.method != ASCMethod.milestone,
    )
    if organization_id is not None:
        q = q.filter(RevenueContract.organization_id == organization_id)
    contracts = q.all()

    totals = {"over_time": 0.0, "consumption": 0.0, "straight_line": 0.0, "skipped": 0}

    for contract in contracts:
        if is_period_closed(db, year, month, contract.organization_id):
            totals["skipped"] += 1
            continue
        if contract.method in (ASCMethod.over_time, ASCMethod.consumption):
            amt = _recognize_over_time(db, contract, year, month, user_id)
            key = "over_time" if contract.method == ASCMethod.over_time else "consumption"
            totals[key] = round(totals[key] + amt, 2)
        elif contract.method == ASCMethod.straight_line:
            amt = _recognize_straight_line(db, contract, year, month, user_id)
            totals["straight_line"] = round(totals["straight_line"] + amt, 2)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"period": f"{year}-{month:02d}", "recognized": totals}


# ── Dashboard ──────────────────────────────────────────────────────────────────

def get_asc606_dashboard(db: Session, year: int, months: int = 12) -> dict:
    """
    Returns by-month recognized/deferred totals and contract summary.
    """
    from sqlalchemy import case

    monthly = []
    for m in range(1, months + 1):
        row = (
            db.query(
                func.sum(case((RevenueEntry.entry_type == EntryType.recognized, RevenueEntry.amount), else_=0)).label("recognized"),
                func.sum(case((RevenueEntry.entry_type == EntryType.deferred, RevenueEntry.amount), else_=0)).label("deferred"),
                func.sum(case((RevenueEntry.entry_type == EntryType.unbilled, RevenueEntry.amount), else_=0)).label("unbilled"),
            )
            .filter(RevenueEntry.period_year == year, RevenueEntry.period_month == m)
            .first()
        )
        monthly.append({
            "month": m,
            "year": year,
            "recognized": round(row.recognized or 0, 2),
            "deferred":   round(row.deferred or 0, 2),
            "unbilled":   round(row.unbilled or 0, 2),
        })

    totals = (
        db.query(
            func.sum(RevenueEntry.amount).label("total"),
            func.count(RevenueEntry.id).label("count"),
        )
        .filter(RevenueEntry.period_year == year)
        .first()
    )

    contracts = db.query(RevenueContract).filter(RevenueContract.is_active == True).all()

    return {
        "year": year,
        "total_recognized": round(totals.total or 0, 2),
        "entry_count": totals.count or 0,
        "by_month": monthly,
        "contracts": [_serialize_contract(c) for c in contracts],
    }


# ── Serializers ────────────────────────────────────────────────────────────────

def _serialize_contract(c: RevenueContract) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "client_id": c.client_id,
        "name": c.name,
        "contract_value": c.contract_value,
        "currency": c.currency,
        "method": c.method.value if c.method else None,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "duration_months": c.duration_months,
        "is_active": c.is_active,
        "notes": c.notes,
        "created_at": str(c.created_at)[:19] if c.created_at else None,
    }


def _serialize_obligation(ob: RevenueObligation) -> dict:
    return {
        "id": ob.id,
        "contract_id": ob.contract_id,
        "milestone_id": ob.milestone_id,
        "name": ob.name,
        "allocated_pct": ob.allocated_pct,
        "allocated_amount": ob.allocated_amount,
        "is_satisfied": ob.is_satisfied,
        "satisfied_date": str(ob.satisfied_date) if ob.satisfied_date else None,
    }


def _serialize_entry(e: RevenueEntry) -> dict:
    return {
        "id": e.id,
        "rev_contract_id": e.rev_contract_id,
        "entry_type": e.entry_type.value if e.entry_type else None,
        "amount": e.amount,
        "currency": e.currency,
        "period_year": e.period_year,
        "period_month": e.period_month,
        "milestone_id": e.milestone_id,
        "description": e.description,
        "reverses_entry_id": e.reverses_entry_id,
        "created_by": e.created_by,
        "created_at": str(e.created_at)[:19] if e.created_at else None,
    }


def _serialize_period_close(pc: RevenuePeriodClose) -> dict:
    return {
        "id": pc.id,
        "period_year": pc.period_year,
        "period_month": pc.period_month,
        "closed_by": pc.closed_by,
        "closed_at": str(pc.closed_at)[:19] if pc.closed_at else None,
        "notes": pc.notes,
    }
