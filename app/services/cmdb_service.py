"""
CMDB Service — Business logic extracted from cmdb.py router.
Covers: wiki tags, internal comments, CMDB CRUD + changelog,
agent dashboard, wiki export, kanban, sprint planning, SLA calendars.
"""
from datetime import date, timedelta, timezone
from typing import Optional, List
import json
import logging

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from fastapi import HTTPException

from app.models.project import Project
from app.models.task import Task
from app.models.epics import WikiSpace, WikiPage
from app.models.cmdb import (
    WikiTag, WikiPageTag, WikiExportJob,
    KanbanConfig, KanbanColumn,
    SprintPlan, SprintPlanTask,
    SLACalendar, V21SLAHoliday,
)
from app.models.sprints import SprintTask
from app.core import timeutil

logger = logging.getLogger(__name__)

_CI_SPECIFIC = [
    'os', 'cpu_cores', 'ram_gb', 'serial_number', 'location', 'url', 'tech_stack',
    'repo_url', 'owner_team', 'sla_tier', 'db_engine', 'port', 'size_gb',
    'backup_schedule', 'vendor', 'cluster', 'namespace', 'replicas', 'cloud_provider',
    'region', 'resource_id', 'instance_type', 'monthly_cost', 'image', 'assigned_to',
    'warranty_date', 'protocol', 'capacity_tb', 'used_tb', 'model', 'dependencies',
]


def _404(m):
    raise HTTPException(404, f"{m} no encontrado")


# ──────────────────────────────────────────────────────────────────────────────
# WIKI TAGS
# ──────────────────────────────────────────────────────────────────────────────

def list_wiki_tags(space_id: str, db: Session) -> list:
    tags = db.query(WikiTag).filter(WikiTag.space_id == space_id, WikiTag.is_active == True).all()
    counts = dict(db.query(WikiPageTag.tag_id, func.count(WikiPageTag.id))
                   .filter(WikiPageTag.tag_id.in_([t.id for t in tags]))
                   .group_by(WikiPageTag.tag_id).all())
    return [{"id": t.id, "name": t.name, "color": t.color,
             "page_count": counts.get(t.id, 0)} for t in tags]


def create_wiki_tag(space_id: str, name: str, color: str, user_id: str, db: Session) -> dict:
    if not db.query(WikiSpace).filter(WikiSpace.id == space_id).first():
        _404("Espacio")
    t = WikiTag(space_id=space_id, name=name, color=color, created_by=user_id)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name, "color": t.color}


def update_wiki_tag(tag_id: str, name: str, color: str, db: Session) -> dict:
    t = db.query(WikiTag).filter(WikiTag.id == tag_id, WikiTag.is_active == True).first()
    if not t: _404("Etiqueta")
    t.name = name; t.color = color; db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name, "color": t.color}


def delete_wiki_tag(tag_id: str, db: Session) -> dict:
    t = db.query(WikiTag).filter(WikiTag.id == tag_id, WikiTag.is_active == True).first()
    if not t: _404("Etiqueta")
    linked_pages = db.query(func.count(WikiPageTag.id)).filter(WikiPageTag.tag_id == tag_id).scalar() or 0
    if linked_pages > 0:
        raise HTTPException(400, f"No se puede eliminar: la etiqueta esta asociada a {linked_pages} pagina(s)")
    t.is_active = False
    db.commit()
    return {"ok": True, "message": "Etiqueta eliminada correctamente"}


def add_page_tag(page_id: str, tag_id: str, db: Session) -> dict:
    if not db.query(WikiPageTag).filter(
            WikiPageTag.page_id == page_id, WikiPageTag.tag_id == tag_id).first():
        db.add(WikiPageTag(page_id=page_id, tag_id=tag_id))
        db.commit()
    return {"linked": True}


def remove_page_tag(page_id: str, tag_id: str, db: Session) -> dict:
    pt = db.query(WikiPageTag).filter(
        WikiPageTag.page_id == page_id, WikiPageTag.tag_id == tag_id).first()
    if pt: db.delete(pt); db.commit()
    return {"unlinked": True}


def get_page_tags(page_id: str, db: Session) -> list:
    pts = db.query(WikiPageTag).options(joinedload(WikiPageTag.tag)).filter(
        WikiPageTag.page_id == page_id).all()
    return [{"id": pt.tag.id, "name": pt.tag.name, "color": pt.tag.color}
            for pt in pts if pt.tag and pt.tag.is_active]


def get_pages_by_tag(space_id: str, tag_id: str, db: Session) -> list:
    tag = db.query(WikiTag).filter(WikiTag.id == tag_id, WikiTag.is_active == True).first()
    if not tag:
        _404("Etiqueta")
    pts = db.query(WikiPageTag).filter(WikiPageTag.tag_id == tag_id).all()
    page_ids = [p.page_id for p in pts]
    pages = db.query(WikiPage).filter(
        WikiPage.id.in_(page_ids), WikiPage.space_id == space_id).all()
    return [{"id": p.id, "title": p.title, "slug": p.slug} for p in pages]


# ──────────────────────────────────────────────────────────────────────────────
# INTERNAL TICKET COMMENTS
# ──────────────────────────────────────────────────────────────────────────────









# ──────────────────────────────────────────────────────────────────────────────
# AGENT DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

def get_agent_dashboard(agent_id: str, days: int, db: Session) -> dict:
    """Rendimiento del agente calculado sobre sus tickets.

    Auditoria 2026-11: leia `agent_metric_snapshots`, que solo escribia un boton
    con `open_tickets` y ceros en todo lo demas; ningun job la alimentaba, y el
    panel ensenaba 0 resueltos, 0 h, 0 % de SLA y sin CSAT. Los tickets ya
    guardan todo: quien los tiene, cuando se resolvieron, cuanto tardaron, si
    incumplieron el SLA y la valoracion. Los dias son los de la zona de quien
    mira (`timeutil`).
    """
    from app.models.service_desk import Ticket
    days = max(1, min(int(days or 30), 366))
    zona = timeutil.current_zone()
    hoy = timeutil.today()
    primer_dia = hoy - timedelta(days=days - 1)
    desde, _ = timeutil.day_bounds_in(primer_dia, zona)

    abiertos = db.query(func.count(Ticket.id)).filter(
        Ticket.assigned_to_user_id == agent_id,
        Ticket.status.notin_(["resolved", "closed", "cancelled"]),
    ).scalar() or 0
    resueltos = db.query(Ticket).filter(
        Ticket.assigned_to_user_id == agent_id,
        Ticket.resolved_at.isnot(None),
        Ticket.resolved_at >= desde,
    ).all()

    por_dia = {primer_dia + timedelta(days=n): {"resolved": 0, "sla_ok": 0, "sla_fail": 0, "csat": []}
               for n in range(days)}
    horas = []
    for t in resueltos:
        cuando = t.resolved_at if t.resolved_at.tzinfo else t.resolved_at.replace(tzinfo=timezone.utc)
        dia = por_dia.get(cuando.astimezone(zona).date())
        if dia is None:
            continue
        dia["resolved"] += 1
        dia["sla_fail" if t.sla_resolution_breached else "sla_ok"] += 1
        if t.csat_score is not None:
            dia["csat"].append(t.csat_score)
        if t.resolution_minutes is not None:
            horas.append(t.resolution_minutes / 60)

    total = sum(d["resolved"] for d in por_dia.values())
    ok = sum(d["sla_ok"] for d in por_dia.values())
    csat = [c for d in por_dia.values() for c in d["csat"]]
    return {
        "agent_id": agent_id,
        "period_days": days,
        "current": {"open_tickets": abiertos},
        "kpis": {
            "total_resolved": total,
            "avg_resolution_hours": round(sum(horas) / len(horas), 1) if horas else 0,
            "sla_compliance_pct": round(ok / total * 100) if total else 0,
            "avg_csat": round(sum(csat) / len(csat), 2) if csat else None,
        },
        "trend": [
            {"date": dia.isoformat(), "resolved": d["resolved"], "sla_ok": d["sla_ok"],
             "sla_fail": d["sla_fail"],
             "csat": round(sum(d["csat"]) / len(d["csat"]), 2) if d["csat"] else None}
            for dia, d in sorted(por_dia.items())
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# WIKI EXPORT
# ──────────────────────────────────────────────────────────────────────────────

def create_wiki_export_job(page_id: str, user_id: str, db: Session) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página wiki")
    job = WikiExportJob(page_id=page_id, status="pending", file_path=None, created_by=user_id)
    db.add(job); db.commit(); db.refresh(job)
    return {
        "job_id": job.id, "status": "pending",
        "page_title": page.title,
        "message": "Trabajo de exportación creado. Procesando en segundo plano.",
    }


def list_wiki_export_jobs(user_id: str, db: Session) -> list:
    jobs = db.query(WikiExportJob).filter(
        WikiExportJob.created_by == user_id
    ).order_by(WikiExportJob.created_at.desc()).limit(20).all()
    return [{"id": j.id, "page_id": j.page_id, "status": j.status,
             "file_path": j.file_path,
             "created_at": j.created_at.isoformat() if j.created_at else None}
            for j in jobs]


# ──────────────────────────────────────────────────────────────────────────────
# KANBAN
# ──────────────────────────────────────────────────────────────────────────────

def get_kanban_config(project_id: str, db: Session) -> dict:
    cfg = db.query(KanbanConfig).options(
        joinedload(KanbanConfig.columns)
    ).filter(KanbanConfig.project_id == project_id).first()
    if not cfg:
        return {"project_id": project_id, "swimlane_by": "none",
                "show_subtasks": True, "card_fields": ["priority", "assignee"],
                "columns": [], "configured": False}
    return {
        "id": cfg.id, "project_id": cfg.project_id,
        "swimlane_by": cfg.swimlane_by, "show_subtasks": cfg.show_subtasks,
        "card_fields": json.loads(cfg.card_fields) if cfg.card_fields else [],
        "configured": True,
        "columns": [
            {"id": col.id, "status": col.status, "label": col.label,
             "wip_limit": col.wip_limit, "color": col.color, "sort_order": col.sort_order}
            for col in (cfg.columns or []) if col.is_active
        ],
    }


def upsert_kanban_config(
    project_id: str, swimlane_by: str, show_subtasks: bool,
    card_fields: Optional[List[str]], db: Session,
) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        _404("Proyecto")
    cfg = db.query(KanbanConfig).filter(KanbanConfig.project_id == project_id).first()
    if cfg:
        cfg.swimlane_by = swimlane_by
        cfg.show_subtasks = show_subtasks
        cfg.card_fields = json.dumps(card_fields or [])
    else:
        cfg = KanbanConfig(
            project_id=project_id, swimlane_by=swimlane_by,
            show_subtasks=show_subtasks, card_fields=json.dumps(card_fields or []),
        )
        db.add(cfg)
    db.commit(); db.refresh(cfg)
    return {"id": cfg.id, "project_id": project_id, "swimlane_by": cfg.swimlane_by}


def add_kanban_column(
    project_id: str, status: str, label: Optional[str],
    wip_limit: Optional[int], color: Optional[str], sort_order: int, db: Session,
) -> dict:
    cfg = db.query(KanbanConfig).filter(KanbanConfig.project_id == project_id).first()
    if not cfg: raise HTTPException(400, "Configura el tablero Kanban primero")
    existing = db.query(KanbanColumn).filter(
        KanbanColumn.config_id == cfg.id,
        KanbanColumn.status == status,
        KanbanColumn.is_active == True,
    ).first()
    if existing:
        raise HTTPException(400, f"El estado '{status}' ya tiene columna")
    col = KanbanColumn(config_id=cfg.id, status=status, label=label,
                       wip_limit=wip_limit, color=color, sort_order=sort_order)
    db.add(col); db.commit(); db.refresh(col)
    return {"id": col.id, "status": col.status, "wip_limit": col.wip_limit}


def update_kanban_column(
    column_id: str, label: Optional[str], wip_limit: Optional[int],
    color: Optional[str], sort_order: int, db: Session,
) -> dict:
    col = db.query(KanbanColumn).filter(KanbanColumn.id == column_id, KanbanColumn.is_active == True).first()
    if not col: _404("Columna")
    col.label = label; col.wip_limit = wip_limit
    col.color = color; col.sort_order = sort_order
    db.commit(); db.refresh(col)
    return {"id": col.id, "status": col.status, "wip_limit": col.wip_limit}


def delete_kanban_column(column_id: str, db: Session) -> dict:
    col = db.query(KanbanColumn).filter(KanbanColumn.id == column_id, KanbanColumn.is_active == True).first()
    if not col: _404("Columna")
    tasks_using_column = db.query(func.count(Task.id)).filter(
        Task.project_id == col.config.project_id,
        Task.status == col.status,
    ).scalar() or 0
    if tasks_using_column > 0:
        raise HTTPException(400, f"No se puede eliminar: {tasks_using_column} tarea(s) usan esta columna")
    col.is_active = False
    db.commit()
    return {"ok": True, "message": "Columna eliminada correctamente"}


def get_kanban_board(
    project_id: str, sprint_id: Optional[str],
    swimlane_value: Optional[str], db: Session,
) -> dict:
    cfg = db.query(KanbanConfig).options(joinedload(KanbanConfig.columns)).filter(
        KanbanConfig.project_id == project_id).first()
    cols = [c for c in cfg.columns if c.is_active] if cfg else []
    statuses = [c.status for c in cols] if cols else []

    q = db.query(Task).filter(Task.project_id == project_id)
    if sprint_id:
        sids = {st.task_id for st in db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint_id).all()}
        q = q.filter(Task.id.in_(sids))
    tasks = q.all()

    wip = {}
    for col in cols:
        col_tasks = [t for t in tasks if t.status == col.status]
        wip[col.status] = {
            "count": len(col_tasks), "limit": col.wip_limit,
            "over_limit": col.wip_limit and len(col_tasks) > col.wip_limit,
        }

    by_status: dict = {}
    for t in tasks:
        by_status.setdefault(t.status, []).append({
            "id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "story_points": t.story_points,
            "issue_type": t.issue_type, "assigned_to": t.assignee_id,
        })

    return {
        "project_id": project_id,
        "config": {
            "swimlane_by": cfg.swimlane_by if cfg else "none",
            "show_subtasks": cfg.show_subtasks if cfg else True,
        },
        "columns": [
            {"status": c.status, "label": c.label or c.status,
             "wip_limit": c.wip_limit, "color": c.color,
             "tasks": by_status.get(c.status, []),
             "wip": wip.get(c.status, {})}
            for c in cols
        ],
        "unconfigured_tasks": {s: ts for s, ts in by_status.items()
                               if s not in statuses} if statuses else by_status,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SPRINT PLANNING
# ──────────────────────────────────────────────────────────────────────────────

def generate_sprint_plan(
    project_id: str, sprint_id: Optional[str], name: str,
    team_capacity: int, priorities: List[str], user_id: str, db: Session,
) -> dict:
    backlog_raw = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status == "todo",
    ).all()

    if not backlog_raw:
        raise HTTPException(400, "No hay tareas en estado 'todo' en este proyecto")

    unestimated_ids = set()
    for t in backlog_raw:
        if t.story_points is None:
            t.story_points = 1
            unestimated_ids.add(t.id)

    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    backlog = sorted(
        backlog_raw,
        key=lambda t: (-t.story_points, PRIORITY_ORDER.get(t.priority or "low", 3))
    )

    selected = []; total = 0; reasoning_parts = []
    must_include = {tid for tid in (priorities or [])}

    for t in backlog:
        if t.id in must_include:
            selected.append(t); total += t.story_points
            est_note = " (sin estimar — asignado 1p por defecto)" if t.id in unestimated_ids else ""
            reasoning_parts.append(f"• '{t.title}' incluida por prioridad manual ({t.story_points}p){est_note}")

    for t in backlog:
        if t.id in {s.id for s in selected}:
            continue
        pts = t.story_points
        est_note = " [~1p sin estimación]" if t.id in unestimated_ids else ""
        if total + pts <= team_capacity:
            selected.append(t); total += pts
            reasoning_parts.append(
                f"• '{t.title}' — {pts}p, prioridad {t.priority or 'normal'}{est_note}")
        else:
            reason = "capacidad alcanzada" if total >= team_capacity * 0.7 else \
                     f"añadir {pts}p superaría la capacidad de {team_capacity}p"
            reasoning_parts.append(f"  ✗ '{t.title}' ({pts}p) excluida — {reason}")

    unestimated_count = len([t for t in selected if t.id in unestimated_ids])
    unestimated_note = (
        f"\n⚠ {unestimated_count} tarea(s) sin story points estimados — asignado 1p por defecto. "
        "Se recomienda estimar el backlog antes de planificar."
        if unestimated_count else ""
    )
    reasoning = (
        f"Plan generado para capacidad de {team_capacity} story points.\n"
        f"Tareas seleccionadas: {len(selected)} ({total}p de {team_capacity}p disponibles)."
        f"{unestimated_note}\n\n" + "\n".join(reasoning_parts)
    )

    plan = SprintPlan(
        project_id=project_id, sprint_id=sprint_id, name=name,
        total_points=total, team_capacity=team_capacity,
        ai_reasoning=reasoning, status="draft", created_by=user_id,
    )
    db.add(plan); db.flush()
    for i, t in enumerate(selected):
        db.add(SprintPlanTask(plan_id=plan.id, task_id=t.id, priority=i,
                              ai_note=f"{t.story_points}p · {t.priority or 'normal'}"))
    db.commit(); db.refresh(plan)
    db.expire_all()

    return {
        "id": plan.id, "name": plan.name, "status": plan.status,
        "total_points": total, "team_capacity": team_capacity,
        "utilization_pct": round(total / team_capacity * 100) if team_capacity else 0,
        "task_count": len(selected),
        "ai_reasoning": reasoning,
        "unestimated_count": unestimated_count,
        "tasks": [{"task_id": t.id, "title": t.title,
                   "story_points": t.story_points, "priority": t.priority,
                   "unestimated": t.id in unestimated_ids}
                  for t in selected],
    }


def list_sprint_plans(project_id: str, db: Session) -> list:
    plans = db.query(SprintPlan).filter(
        SprintPlan.project_id == project_id,
        SprintPlan.is_active == True,
    ).order_by(SprintPlan.created_at.desc()).all()
    return [{"id": p.id, "name": p.name, "status": p.status,
             "total_points": p.total_points, "team_capacity": p.team_capacity,
             "task_count": len(p.tasks),
             "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in plans]


def update_sprint_plan_status(plan_id: str, status: str, db: Session) -> dict:
    if status not in ("draft", "accepted", "rejected"):
        raise HTTPException(400, "Estado válido: draft, accepted, rejected")
    plan = db.query(SprintPlan).filter(SprintPlan.id == plan_id, SprintPlan.is_active == True).first()
    if not plan: _404("Plan")
    plan.status = status; db.commit()
    return {"id": plan.id, "status": plan.status}


def delete_sprint_plan(plan_id: str, db: Session) -> dict:
    plan = db.query(SprintPlan).filter(SprintPlan.id == plan_id, SprintPlan.is_active == True).first()
    if not plan: _404("Plan")
    if plan.status == "accepted":
        raise HTTPException(400, "No se puede eliminar un plan aceptado")
    plan.is_active = False
    db.commit()
    return {"ok": True, "message": "Plan eliminado correctamente"}


# ──────────────────────────────────────────────────────────────────────────────
# SLA CALENDARS
# ──────────────────────────────────────────────────────────────────────────────

def list_sla_calendars(db: Session) -> list:
    cals = db.query(SLACalendar).options(joinedload(SLACalendar.holidays)).filter(SLACalendar.is_active == True).all()
    return [{"id": c.id, "name": c.name, "timezone": c.timezone,
             "work_start": c.work_start, "work_end": c.work_end,
             "work_days": c.work_days,
             "holiday_count": len([h for h in c.holidays if h.is_active])} for c in cals]


def create_sla_calendar(
    name: str, timezone: str, work_start: str, work_end: str, work_days: str, db: Session,
) -> dict:
    c = SLACalendar(name=name, timezone=timezone,
                    work_start=work_start, work_end=work_end, work_days=work_days)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}


def update_sla_calendar(cal_id: str, payload, db: Session) -> dict:
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id, SLACalendar.is_active == True).first()
    if not c: _404("Calendario")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}


def delete_sla_calendar(cal_id: str, db: Session) -> dict:
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id, SLACalendar.is_active == True).first()
    if not c: _404("Calendario")
    holiday_count = db.query(func.count(V21SLAHoliday.id)).filter(
        V21SLAHoliday.calendar_id == cal_id,
        V21SLAHoliday.is_active == True,
    ).scalar() or 0
    if holiday_count > 0:
        raise HTTPException(400, f"No se puede eliminar: el calendario tiene {holiday_count} festivo(s) activos")
    from app.models.service_desk import SLAPolicy
    en_uso = db.query(SLAPolicy.name).filter(
        SLAPolicy.calendar_id == cal_id, SLAPolicy.is_active == True,  # noqa: E712
    ).all()
    if en_uso:
        raise HTTPException(400, "No se puede eliminar: lo usan las políticas SLA "
                                 + ", ".join(n for (n,) in en_uso))
    c.is_active = False
    db.commit()
    return {"ok": True, "message": "Calendario eliminado correctamente"}


def list_sla_holidays(cal_id: str, db: Session) -> list:
    hs = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.calendar_id == cal_id,
        V21SLAHoliday.is_active == True,
    ).order_by(V21SLAHoliday.holiday_date).all()
    return [{"id": h.id, "holiday_date": h.holiday_date, "name": h.name} for h in hs]


def add_sla_holiday(cal_id: str, holiday_date: str, name: Optional[str], db: Session) -> dict:
    if not db.query(SLACalendar).filter(SLACalendar.id == cal_id, SLACalendar.is_active == True).first():
        _404("Calendario")
    h = V21SLAHoliday(calendar_id=cal_id, holiday_date=holiday_date, name=name)
    db.add(h); db.commit(); db.refresh(h)
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}


def update_sla_holiday(
    cal_id: str, holiday_id: str, holiday_date: str, name: Optional[str], db: Session,
) -> dict:
    h = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.id == holiday_id,
        V21SLAHoliday.calendar_id == cal_id,
        V21SLAHoliday.is_active == True,
    ).first()
    if not h: _404("Festivo")
    h.holiday_date = holiday_date
    if name is not None:
        h.name = name
    db.commit(); db.refresh(h)
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}


def delete_sla_holiday(cal_id: str, holiday_id: str, db: Session) -> dict:
    h = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.id == holiday_id,
        V21SLAHoliday.calendar_id == cal_id,
        V21SLAHoliday.is_active == True,
    ).first()
    if not h: _404("Festivo")
    h.is_active = False
    db.commit()
    return {"ok": True, "message": "Festivo eliminado correctamente"}


def check_is_business_day(cal_id: str, check_date: str, db: Session) -> dict:
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id, SLACalendar.is_active == True).first()
    if not c: _404("Calendario")
    try:
        d = date.fromisoformat(check_date)
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido. Usa YYYY-MM-DD")
    work_days = set(int(x) for x in c.work_days.split(",") if x.strip())
    dow = d.isoweekday()
    is_weekend  = dow not in work_days
    holiday_obj = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.calendar_id == cal_id,
        V21SLAHoliday.holiday_date == check_date,
        V21SLAHoliday.is_active == True,
    ).first()
    is_holiday   = holiday_obj is not None
    holiday_name = holiday_obj.name if holiday_obj else None

    return {
        "date": check_date,
        "is_business_day": not is_weekend and not is_holiday,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "day_of_week": d.strftime("%A"),
    }
