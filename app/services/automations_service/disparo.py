"""Disparo de reglas por evento, barridos periodicos y reglas programadas.

Parte de `app.services.automations_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core import timeutil
from app.models.automations import AutomationExecution, AutomationRule
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

from app.services.automations_service.catalogo import CATALOGO_DISPARADORES, check_conditions
from app.services.automations_service.acciones import (
    _TAREA_ABIERTA,
    _contexto_publico,
    execute_actions,
)
from app.services.automations_service._comun import _v, logger


# ═════════════════════════════════════════════════════════════════════════════
# Disparo
# ═════════════════════════════════════════════════════════════════════════════

def _encendidas(db: Session, org_id: Optional[str]) -> bool:
    from app.services.settings_service import get_runtime_bool
    valor = get_runtime_bool(db, "AUTOMATIONS_ENABLED", org_id)
    return True if valor is None else bool(valor)


def _reglas(db: Session, trigger_type: str, org_id: str) -> list:
    return db.query(AutomationRule).filter(
        AutomationRule.trigger_type == trigger_type,
        AutomationRule.is_active.is_(True),
        AutomationRule.organization_id == org_id,
    ).order_by(AutomationRule.created_at).all()


def disparar(db: Session, trigger_type: str, context: dict, org_id: Optional[str], *,
             profundidad: int = 0, clave: Optional[str] = None) -> dict:
    """Ejecuta las reglas activas de `org_id` con ese disparador. No hace commit.

    `clave`: si la regla ya actuo con esta clave, no repite (barrido).
    """
    from app.services.settings_service import get_runtime_int

    if not org_id or not _encendidas(db, org_id):
        return {"rules": []}
    maximo = get_runtime_int(db, "AUTOMATIONS_MAX_CHAIN_DEPTH", org_id)
    if profundidad > (3 if maximo is None else maximo):
        logger.warning("automatizaciones: cadena cortada en %s (profundidad %s)", trigger_type, profundidad)
        return {"rules": [], "cut": True}

    context = {**context, "organization_id": org_id, "event_type": trigger_type}
    ejecutadas = []
    for rule in _reglas(db, trigger_type, org_id):
        if rule.project_id and rule.project_id != context.get("project_id"):
            continue
        conditions = json.loads(rule.trigger_conditions) if rule.trigger_conditions else None
        if not check_conditions(conditions, context):
            continue
        if clave and db.query(AutomationExecution.id).filter(
                AutomationExecution.rule_id == rule.id, AutomationExecution.dedupe_key == clave).first():
            continue
        ejecutadas.append(_ejecutar_regla(db, rule, context, profundidad, clave))
    return {"rules": ejecutadas}


def _ejecutar_regla(db: Session, rule: AutomationRule, context: dict, profundidad: int,
                    clave: Optional[str]) -> dict:
    """Corre las acciones de una regla y deja constancia. No hace commit."""
    from app.services.automation_events import PROFUNDIDAD
    context = {**context, "rule_owner_id": rule.created_by}
    previa = db.info.get(PROFUNDIDAD)
    db.info[PROFUNDIDAD] = profundidad + 1
    try:
        results = execute_actions(json.loads(rule.actions) if rule.actions else [], context, db)
        db.flush()
    finally:
        if previa is None:
            db.info.pop(PROFUNDIDAD, None)
        else:
            db.info[PROFUNDIDAD] = previa
    success = all(r.get("ok", True) for r in results)
    db.add(AutomationExecution(
        rule_id=rule.id, organization_id=rule.organization_id, dedupe_key=clave,
        trigger_context=json.dumps(_contexto_publico(context), default=str),
        actions_taken=json.dumps(results, default=str),
        success=success,
        error=None if success else "; ".join(str(r.get("error")) for r in results if not r.get("ok", True))[:500],
    ))
    rule.run_count = (rule.run_count or 0) + 1
    rule.last_run_at = datetime.now(timezone.utc)
    rule.last_error = None if success else json.dumps(
        [r for r in results if not r.get("ok", True)], default=str)[:500]
    return {"rule_id": rule.id, "success": success}


# ── Barrido periodico: fechas y umbrales ────────────────────────────────────

def _orgs_con_reglas(db: Session, trigger_type: str, org_id: Optional[str]) -> list[str]:
    q = db.query(AutomationRule.organization_id).filter(
        AutomationRule.trigger_type == trigger_type, AutomationRule.is_active.is_(True),
        AutomationRule.organization_id.isnot(None))
    if org_id:
        q = q.filter(AutomationRule.organization_id == org_id)
    return [o for (o,) in q.distinct().all()]


def _contexto_de_tarea(t: Task) -> dict:
    return {"task_id": t.id, "project_id": t.project_id, "code": t.code, "title": t.title,
            "status": _v(t.status), "priority": _v(t.priority), "assignee_id": t.assignee_id,
            "user_id": t.assignee_id, "due_date": str(t.due_date) if t.due_date else None}


def _barrer_tareas_vencidas(db: Session, org: str, hoy) -> int:
    n = 0
    for t in db.query(Task).filter(Task.organization_id == org, Task.is_active.is_(True),
                                   Task.due_date < hoy, Task.status.notin_(_TAREA_ABIERTA)):
        r = disparar(db, "task_overdue", {**_contexto_de_tarea(t), "days_overdue": (hoy - t.due_date).days},
                     org, clave=f"task_overdue:{t.id}:{t.due_date}")
        n += len(r["rules"])
    return n


def _barrer_tareas_que_vencen(db: Session, org: str, hoy) -> int:
    from app.services.settings_service import get_runtime_int
    dias = get_runtime_int(db, "AUTOMATIONS_DEADLINE_DAYS", org)
    dias = 2 if dias is None else dias
    n = 0
    for t in db.query(Task).filter(Task.organization_id == org, Task.is_active.is_(True),
                                   Task.due_date >= hoy, Task.due_date <= hoy + timedelta(days=dias),
                                   Task.status.notin_(_TAREA_ABIERTA)):
        r = disparar(db, "task_deadline_approaching",
                     {**_contexto_de_tarea(t), "days_left": (t.due_date - hoy).days},
                     org, clave=f"task_deadline:{t.id}:{t.due_date}")
        n += len(r["rules"])
    return n


def _barrer_presupuesto(db: Session, org: str, hoy) -> int:
    """Consumo = coste imputado / presupuesto, como el motor de alertas."""
    from app.models.project import ProjectStatus
    from app.models.imputation import Imputation
    proyectos = db.query(Project).filter(Project.organization_id == org, Project.status == ProjectStatus.active,
                                         Project.budget_amount > 0).all()
    if not proyectos:
        return 0
    costes = dict(db.query(Imputation.project_id, func.sum(Imputation.cost_amount)).filter(
        Imputation.project_id.in_([p.id for p in proyectos])).group_by(Imputation.project_id).all())
    n = 0
    for p in proyectos:
        pct = round(float(costes.get(p.id) or 0) / float(p.budget_amount) * 100, 1)
        # Una vez por regla y proyecto: la condicion de la regla decide el umbral.
        r = disparar(db, "budget_threshold", {"project_id": p.id, "code": p.code, "name": p.name,
                                              "budget_pct": pct}, org, clave=f"budget_threshold:{p.id}")
        n += len(r["rules"])
    return n


def _barrer_partes(db: Session, org: str, hoy) -> int:
    from app.models.financial import Timesheet, TimesheetStatus
    from app.services.settings_service import get_runtime_int
    dia = get_runtime_int(db, "AUTOMATIONS_TIMESHEET_WEEKDAY", org) or 5
    if hoy.isoweekday() < dia:
        return 0
    lunes = hoy - timedelta(days=hoy.weekday())
    enviados = {u for (u,) in db.query(Timesheet.user_id).filter(
        Timesheet.week_start == lunes, Timesheet.status != TimesheetStatus.draft)}
    n = 0
    for u in db.query(User).filter(User.organization_id == org, User.is_active.is_(True)):
        if u.id in enviados or _v(u.role) in ("client",):
            continue
        r = disparar(db, "timesheet_not_submitted", {"user_id": u.id, "week_start": str(lunes)}, org,
                     clave=f"timesheet_not_submitted:{u.id}:{lunes}")
        n += len(r["rules"])
    return n


def _barrer_facturas_vencidas(db: Session, org: str, hoy) -> int:
    """Enviadas y con el vencimiento pasado (nada marca hoy `overdue` por sí solo)."""
    from app.models.billing_reports import Invoice, InvoiceStatus
    n = 0
    for f in db.query(Invoice).filter(Invoice.organization_id == org, Invoice.due_date < hoy,
                                      Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])):
        r = disparar(db, "invoice_overdue", {**contexto_de_factura(f), "days_overdue": (hoy - f.due_date).days},
                     org, clave=f"invoice_overdue:{f.id}:{f.due_date}")
        n += len(r["rules"])
    return n


def contexto_de_factura(f) -> dict:
    return {"invoice_id": f.id, "number": f.number, "project_id": f.project_id, "client_id": f.client_id,
            "client_name": f.client_name, "total": float(f.total or 0), "status": _v(f.status),
            "due_date": str(f.due_date) if f.due_date else None}


_BARRIDOS = {
    "invoice_overdue": _barrer_facturas_vencidas,
    "task_overdue": _barrer_tareas_vencidas,
    "task_deadline_approaching": _barrer_tareas_que_vencen,
    "budget_threshold": _barrer_presupuesto,
    "timesheet_not_submitted": _barrer_partes,
}
assert set(_BARRIDOS) == {k for k, d in CATALOGO_DISPARADORES.items() if d.get("scan")}


def escanear(db: Session, org_id: Optional[str] = None) -> dict:
    """Disparadores de fecha y umbral. Solo mira las organizaciones con reglas activas."""
    from app.services.service_desk.ticket_events import como_organizacion
    hoy = timeutil.today()
    salida = {}
    for disparador, barrer in _BARRIDOS.items():
        total = 0
        for org in _orgs_con_reglas(db, disparador, org_id):
            if not _encendidas(db, org):
                continue
            with como_organizacion(db, org):
                try:
                    with db.begin_nested():
                        total += barrer(db, org, hoy)
                except Exception:
                    logger.exception("automatizaciones: el barrido %s fallo en %s", disparador, org)
        salida[disparador] = total
    salida["scheduled"] = _correr_programadas(db, org_id)
    db.commit()
    return {"executed": sum(salida.values()), "by_trigger": salida}


# ── Reglas programadas (revisión 2026-11) ───────────────────────────────────

def _zona_de(db: Session, org_id: Optional[str]):
    from app.models.mfa import Organization
    org = db.get(Organization, org_id) if org_id else None
    return timeutil.resolve_zone(getattr(org, "timezone", None))


def proxima_ejecucion(db: Session, rule: AutomationRule, desde: Optional[datetime] = None) -> Optional[datetime]:
    """Siguiente instante del cron de la regla, en la zona de su empresa (guardado en UTC)."""
    if _v(rule.trigger_type) != "scheduled" or not rule.schedule_cron:
        return None
    from apscheduler.triggers.cron import CronTrigger
    zona = _zona_de(db, rule.organization_id)
    disparador = CronTrigger.from_crontab(rule.schedule_cron, timezone=zona)
    ahora = (desde or datetime.now(timezone.utc)).astimezone(zona)
    siguiente = disparador.get_next_fire_time(None, ahora)
    return siguiente.astimezone(timezone.utc) if siguiente else None


def _correr_programadas(db: Session, org_id: Optional[str] = None) -> int:
    """Las reglas programadas que ya tocan. Una vez por instante (`dedupe_key`)
    aunque el barrido se retrase: si se perdieron varios, corre una y salta al
    siguiente futuro, sin ponerse al día en ráfaga."""
    from app.services.service_desk.ticket_events import como_organizacion
    ahora = datetime.now(timezone.utc)
    q = db.query(AutomationRule).filter(AutomationRule.trigger_type == "scheduled",
                                        AutomationRule.is_active.is_(True),
                                        AutomationRule.organization_id.isnot(None),
                                        AutomationRule.next_run_at.isnot(None),
                                        AutomationRule.next_run_at <= ahora)
    if org_id:
        q = q.filter(AutomationRule.organization_id == org_id)
    n = 0
    for rule in q.all():
        org = rule.organization_id
        if not _encendidas(db, org):
            continue
        instante = rule.next_run_at
        clave = f"scheduled:{rule.id}:{instante.isoformat()}"
        local = instante.astimezone(_zona_de(db, org))
        ctx = {"organization_id": org, "event_type": "scheduled", "project_id": rule.project_id,
               "scheduled_for": instante.isoformat(), "weekday": local.isoweekday(), "hour": local.hour}
        with como_organizacion(db, org):
            try:
                with db.begin_nested():
                    ya = db.query(AutomationExecution.id).filter(
                        AutomationExecution.rule_id == rule.id, AutomationExecution.dedupe_key == clave).first()
                    condiciones = json.loads(rule.trigger_conditions) if rule.trigger_conditions else None
                    if not ya and check_conditions(condiciones, ctx):
                        _ejecutar_regla(db, rule, ctx, 0, clave)
                        n += 1
            except Exception:
                logger.exception("automatizaciones: la regla programada %s fallo", rule.id)
            rule.next_run_at = proxima_ejecucion(db, rule, desde=ahora)
    return n


def run_scheduled_automations(db: Session, org_id: Optional[str] = None) -> dict:
    """Compatibilidad con `POST /automations/run-scheduled`: corre el barrido."""
    return escanear(db, org_id)
