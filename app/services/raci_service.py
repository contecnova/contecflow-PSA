"""
RACI service — business logic extracted from raci.py endpoint.
Covers: serialisers for User / RACIEntry / ChangelogEntry / UATCase,
        sprint retrospective insights computation, and burnout risk computation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.sprints import Sprint, SprintTask
from app.models.imputation import Imputation
from app.models.raci import (
    RACIEntry,
    BurnoutRiskLevel,
    ProjectChangelogEntry,
    UATCase,
)
from app.models.project import Project
from app.models.raci import RACIRole
from app.models.raci import SprintRetroNote
from app.models.raci import BurnoutRiskSnapshot
from app.models.raci import ProjectChangelogEntry as PCE, ChangelogEntryType
from app.models.raci import UATStatus
from app.models.sprints import Sprint as _Sprint
from app.models.task import Task as _Task, TaskPriority
from app.models.user import User as _User
from app.models.user import UserStatus
from datetime import timezone

if TYPE_CHECKING:
    pass   # avoid circular imports at runtime


# ── Serialisers ───────────────────────────────────────────────────────────────

def serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "role": u.role,
        "department": u.department,
        "job_title": getattr(u, "job_title", None),
        "avatar_initials": u.full_name[:2].upper(),
    }


def serialize_raci_entry(e: RACIEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "item_type": e.item_type,
        "item_label": e.item_label,
        "item_id": e.item_id,
        "user_id": e.user_id,
        "role": e.role.value,
        "user": serialize_user(e.user) if e.user else None,
    }


def serialize_changelog_entry(e: ProjectChangelogEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "version_tag": e.version_tag,
        "entry_date": e.entry_date.isoformat() if e.entry_date else None,
        "entry_type": e.entry_type.value,
        "title": e.title,
        "description": e.description,
        "is_auto_generated": e.is_auto_generated,
        "author": serialize_user(e.author) if e.author else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def serialize_uat_case(c: UATCase) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "task_id": c.task_id,
        "title": c.title,
        "description": c.description,
        "expected_result": c.expected_result,
        "actual_result": c.actual_result,
        "status": c.status.value if c.status else "pending",
        "priority": c.priority,
        "assigned_to_id": c.assigned_to_id,
        "assigned_to": serialize_user(c.assigned_to) if c.assigned_to else None,
        "task_title": c.task.title if c.task else None,
        "notes": c.notes,
        "executed_at": c.executed_at.isoformat() if c.executed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── Sprint retrospective ──────────────────────────────────────────────────────

def compute_retro_insights(sprint: Sprint, db: Session) -> dict:
    """
    Algorithmic retrospective insights from sprint data.
    No LLM required — derives meaningful conclusions from metrics.
    """
    sprint_tasks = (
        db.query(Task)
        .join(SprintTask, SprintTask.task_id == Task.id)
        .filter(SprintTask.sprint_id == sprint.id)
        .all()
    )

    total       = len(sprint_tasks)
    completed   = [t for t in sprint_tasks if t.status == TaskStatus.done]
    blocked     = [t for t in sprint_tasks if t.status == TaskStatus.blocked]
    in_progress = [t for t in sprint_tasks if t.status == TaskStatus.in_progress]

    planned_hours   = sum(t.estimated_hours or 0 for t in sprint_tasks)
    completed_hours = sum(t.actual_hours or t.estimated_hours or 0 for t in completed)
    completion_rate = round(len(completed) / total * 100, 1) if total > 0 else 0
    velocity_ratio  = round(completed_hours / planned_hours * 100, 1) if planned_hours > 0 else 0

    # Count tasks added after sprint start (scope creep indicator)
    added_mid = 0
    if sprint.start_date:
        start_dt = datetime.combine(sprint.start_date, datetime.min.time())
        added_mid = sum(
            1 for st in db.query(SprintTask).filter(SprintTask.sprint_id == sprint.id).all()
            if st.added_at and st.added_at > start_dt
        ) if hasattr(SprintTask, "added_at") else 0

    carryover = len(in_progress) + len([
        t for t in sprint_tasks
        if t.status not in (TaskStatus.done, TaskStatus.cancelled)
    ])

    went_well = []
    improve   = []
    actions   = []
    risks     = []

    if completion_rate >= 85:
        went_well.append(f"Alta tasa de completitud: {completion_rate}% de tareas entregadas")
    if completion_rate >= 95:
        went_well.append("Excelente predictibilidad — casi sin carryover")
    if not blocked:
        went_well.append("Ninguna tarea bloqueada durante el sprint")
    if velocity_ratio >= 90:
        went_well.append(f"Velocity muy ajustada a la planificación ({velocity_ratio}%)")

    if completion_rate < 70:
        improve.append(f"Tasa de completitud baja ({completion_rate}%) — revisar estimaciones o scope")
        actions.append({"text": "Revisar criterios de aceptación antes del siguiente sprint planning", "owner_id": None})
    if blocked:
        improve.append(f"{len(blocked)} tarea(s) bloqueadas — identificar patrones de impedimentos")
        actions.append({"text": "Daily standup: escalar bloqueos en máximo 24h", "owner_id": None})
    if added_mid > 2:
        improve.append(f"Scope creep detectado: {added_mid} tareas añadidas a mitad de sprint")
        actions.append({"text": "Reforzar la política de no añadir al sprint en curso salvo urgencias", "owner_id": None})
    if carryover > 0:
        improve.append(f"{carryover} tarea(s) con carryover — afecta a la previsibilidad")
    if velocity_ratio < 70:
        improve.append(f"Velocity {velocity_ratio}% — sobreestimación habitual, calibrar story points")
        risks.append("Estimaciones sistemáticamente optimistas → riesgo de promesas no cumplidas")

    if completion_rate >= 80 and not blocked:
        actions.append({"text": "Continuar con el ritmo actual; documentar las prácticas que funcionan", "owner_id": None})

    if not went_well:
        went_well.append("Sprint completado — analiza métricas para detectar áreas de mejora")
    if not improve:
        improve.append("No se detectaron problemas estructurales significativos")

    return {
        "metrics": {
            "total_tasks": total,
            "completed": len(completed),
            "blocked": len(blocked),
            "carryover": carryover,
            "added_mid_sprint": added_mid,
            "completion_rate_pct": completion_rate,
            "planned_hours": planned_hours,
            "completed_hours": completed_hours,
            "velocity_ratio_pct": velocity_ratio,
        },
        "went_well": went_well,
        "improve": improve,
        "actions": actions,
        "risks": risks,
    }


# ── Burnout risk ──────────────────────────────────────────────────────────────

def compute_user_burnout_risk(user: User, db: Session, today: date) -> dict:
    """
    Compute burnout risk for a user based on workload patterns.
    Uses last 8 weeks of imputation data.
    """
    weeks_data = []
    for w in range(8):
        week_end   = today - timedelta(days=today.weekday()) - timedelta(weeks=w - 1)
        week_start = week_end - timedelta(days=7)
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == user.id,
            Imputation.date >= week_start,
            Imputation.date < week_end,
        ).scalar() or 0.0
        capacity = user.weekly_capacity_hours or 40.0
        weeks_data.append({
            "week_start": week_start,
            "hours": hours,
            "capacity": capacity,
            "load_pct": round(hours / capacity * 100, 1),
        })

    current_load = weeks_data[0]["load_pct"] if weeks_data else 0
    avg_load_4w  = (
        sum(w["load_pct"] for w in weeks_data[:4]) / 4
        if len(weeks_data) >= 4 else current_load
    )

    streak = 0
    for w in weeks_data:
        if w["load_pct"] > 100:
            streak += 1
        else:
            break

    score = 0.0
    factors = []

    if current_load > 100:
        score += 25
        factors.append(f"Sobrecarga actual: {current_load:.0f}%")
    if avg_load_4w > 90:
        score += 20
        factors.append(f"Media 4 semanas: {avg_load_4w:.0f}%")
    if streak >= 2:
        score += streak * 10
        factors.append(f"{streak} semanas consecutivas al 100%+")
    if streak >= 4:
        factors.append("Riesgo alto de agotamiento sostenido")
    if current_load > 130:
        score += 20
        factors.append("Sobrecarga severa (>130%)")

    score = min(score, 100)

    if score >= 70:
        level = BurnoutRiskLevel.red
    elif score >= 45:
        level = BurnoutRiskLevel.orange
    elif score >= 20:
        level = BurnoutRiskLevel.yellow
    else:
        level = BurnoutRiskLevel.green

    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "department": user.department,
        "job_title": getattr(user, "job_title", None),
        "current_load_pct": current_load,
        "avg_load_4w": round(avg_load_4w, 1),
        "overload_weeks_streak": streak,
        "risk_score": round(score, 1),
        "risk_level": level.value,
        "factors": factors,
        "weekly_history": [
            {
                "week_start": w["week_start"].isoformat(),
                "load_pct": w["load_pct"],
                "hours": round(w["hours"], 1),
            }
            for w in weeks_data
        ],
    }


# ── RACI Matrix CRUD ──────────────────────────────────────────────────────────

def get_project_raci(project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    entries = (
        db.query(RACIEntry)
        .filter(RACIEntry.project_id == project_id)
        .order_by(RACIEntry.item_type, RACIEntry.item_label)
        .all()
    )
    items: dict = {}
    for e in entries:
        key = (e.item_type, e.item_label, e.item_id or "")
        if key not in items:
            items[key] = {"item_type": e.item_type, "item_label": e.item_label,
                          "item_id": e.item_id, "assignments": []}
        items[key]["assignments"].append({
            "entry_id": e.id, "user_id": e.user_id, "role": e.role.value,
            "user": serialize_user(e.user) if e.user else None,
        })
    return {
        "project_id": project_id,
        "project_name": project.name,
        "items": list(items.values()),
        "raw_entries": [serialize_raci_entry(e) for e in entries],
        "total": len(entries),
    }


def upsert_raci(project_id: str, entries_in: list, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    created, updated = 0, 0
    for entry_in in entries_in:
        try:
            role_enum = RACIRole(entry_in.role.upper())
        except ValueError:
            raise ValueError(f"422:Rol RACI inválido: '{entry_in.role}'. Usa R, A, C o I.")
        user = db.query(_User).filter(_User.id == entry_in.user_id).first()
        if not user:
            raise ValueError(f"Usuario {entry_in.user_id} no encontrado")
        existing = (
            db.query(RACIEntry)
            .filter(
                RACIEntry.project_id == project_id,
                RACIEntry.item_label == entry_in.item_label,
                RACIEntry.user_id == entry_in.user_id,
            )
            .first()
        )
        if existing:
            existing.role = role_enum
            existing.item_type = entry_in.item_type
            existing.item_id = entry_in.item_id
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            db.add(RACIEntry(
                project_id=project_id,
                item_type=entry_in.item_type,
                item_label=entry_in.item_label,
                item_id=entry_in.item_id,
                user_id=entry_in.user_id,
                role=role_enum,
            ))
            created += 1
    db.commit()
    return {"created": created, "updated": updated}


def delete_raci_entry(project_id: str, entry_id: str, db: Session) -> None:
    entry = db.query(RACIEntry).filter(
        RACIEntry.id == entry_id, RACIEntry.project_id == project_id
    ).first()
    if not entry:
        raise ValueError("Entrada RACI no encontrada")
    db.delete(entry)
    db.commit()


# ── Sprint Retrospective ──────────────────────────────────────────────────────

def get_sprint_retrospective(project_id: str, sprint_id: str, db: Session) -> dict:
    import json as _json
    sprint = db.query(_Sprint).filter(
        _Sprint.id == sprint_id, _Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise ValueError("Sprint no encontrado")
    insights = compute_retro_insights(sprint, db)
    saved = db.query(SprintRetroNote).filter(SprintRetroNote.sprint_id == sprint_id).first()
    return {
        "sprint_id": sprint_id,
        "sprint_name": sprint.name,
        "sprint_status": sprint.status.value if sprint.status else None,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
        "computed_insights": insights,
        "saved_notes": {
            "id": saved.id,
            "manual_notes": saved.manual_notes,
            "action_items": _json.loads(saved.action_items) if saved and saved.action_items else [],
            "updated_at": saved.updated_at.isoformat() if saved and saved.updated_at else None,
        } if saved else None,
    }


def save_sprint_retrospective(
    project_id: str, sprint_id: str, payload, current_user_id: str, db: Session
) -> dict:
    import json as _json
    sprint = db.query(_Sprint).filter(
        _Sprint.id == sprint_id, _Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise ValueError("Sprint no encontrado")
    insights = compute_retro_insights(sprint, db)
    m = insights["metrics"]
    saved = db.query(SprintRetroNote).filter(SprintRetroNote.sprint_id == sprint_id).first()
    if saved:
        saved.manual_notes = payload.manual_notes
        if payload.action_items is not None:
            saved.action_items = _json.dumps(payload.action_items)
        saved.updated_at = datetime.now(timezone.utc)
    else:
        saved = SprintRetroNote(
            sprint_id=sprint_id,
            project_id=project_id,
            velocity_completed=m["completed_hours"],
            velocity_planned=m["planned_hours"],
            completion_rate_pct=m["completion_rate_pct"],
            blocked_count=m["blocked"],
            added_mid_sprint=m["added_mid_sprint"],
            carryover_count=m["carryover"],
            went_well_items=_json.dumps(insights["went_well"]),
            improve_items=_json.dumps(insights["improve"]),
            action_items=_json.dumps(payload.action_items or insights["actions"]),
            risk_flags=_json.dumps(insights["risks"]),
            manual_notes=payload.manual_notes,
            facilitated_by_id=current_user_id,
        )
        db.add(saved)
    db.commit()
    db.refresh(saved)
    return {"id": saved.id, "sprint_id": sprint_id, "updated_at": saved.updated_at.isoformat()}


# ── Burnout Risk ──────────────────────────────────────────────────────────────

def get_burnout_risk(department: "Optional[str]", min_risk_level: "Optional[str]", db: Session) -> dict:
    today = date.today()
    q = db.query(_User).filter(_User.is_active == True, _User.status == UserStatus.active)
    if department:
        q = q.filter(_User.department == department)
    users = q.all()
    results = [compute_user_burnout_risk(u, db, today) for u in users]
    if min_risk_level:
        order = [BurnoutRiskLevel.green.value, BurnoutRiskLevel.yellow.value,
                 BurnoutRiskLevel.orange.value, BurnoutRiskLevel.red.value]
        try:
            min_idx = order.index(min_risk_level)
            results = [r for r in results if order.index(r["risk_level"]) >= min_idx]
        except ValueError:
            pass
    results.sort(key=lambda r: r["risk_score"], reverse=True)
    level_counts = {v.value: 0 for v in BurnoutRiskLevel}
    for r in results:
        level_counts[r["risk_level"]] += 1
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "total_analyzed": len(results),
        "summary": level_counts,
        "team_avg_load": round(sum(r["current_load_pct"] for r in results) / len(results), 1) if results else 0,
        "members": results,
    }


def compute_and_save_burnout_snapshots(db: Session) -> dict:
    import json as _json
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    users = db.query(_User).filter(_User.is_active == True, _User.status == UserStatus.active).all()
    saved_count = 0
    for user in users:
        risk_data = compute_user_burnout_risk(user, db, today)
        existing = db.query(BurnoutRiskSnapshot).filter(
            BurnoutRiskSnapshot.user_id == user.id,
            BurnoutRiskSnapshot.week_start == week_start,
        ).first()
        level = BurnoutRiskLevel(risk_data["risk_level"])
        if existing:
            existing.load_pct = risk_data["current_load_pct"]
            existing.overload_weeks_streak = risk_data["overload_weeks_streak"]
            existing.avg_load_4w = risk_data["avg_load_4w"]
            existing.risk_level = level
            existing.risk_score = risk_data["risk_score"]
            existing.factors = _json.dumps(risk_data["factors"])
        else:
            db.add(BurnoutRiskSnapshot(
                user_id=user.id,
                week_start=week_start,
                load_pct=risk_data["current_load_pct"],
                overload_weeks_streak=risk_data["overload_weeks_streak"],
                avg_load_4w=risk_data["avg_load_4w"],
                risk_level=level,
                risk_score=risk_data["risk_score"],
                factors=_json.dumps(risk_data["factors"]),
            ))
            saved_count += 1
    db.commit()
    return {"week_start": week_start.isoformat(), "processed": len(users), "new_snapshots": saved_count}


# ── Project Changelog ─────────────────────────────────────────────────────────

def get_project_changelog(
    project_id: str, entry_type: "Optional[str]", since: "Optional[date]", db: Session
) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    q = db.query(PCE).filter(PCE.project_id == project_id)
    if entry_type:
        try:
            q = q.filter(PCE.entry_type == ChangelogEntryType(entry_type))
        except ValueError:
            pass
    if since:
        q = q.filter(PCE.entry_date >= since)
    entries = q.order_by(PCE.entry_date.desc()).all()
    return {
        "project_id": project_id,
        "project_name": project.name,
        "total": len(entries),
        "entries": [serialize_changelog_entry(e) for e in entries],
    }


def create_changelog_entry(project_id: str, payload, author_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    try:
        entry_type = ChangelogEntryType(payload.entry_type)
    except ValueError:
        raise ValueError(f"422:Tipo de entrada inválido: '{payload.entry_type}'")
    entry = PCE(
        project_id=project_id,
        version_tag=payload.version_tag,
        entry_date=payload.entry_date,
        entry_type=entry_type,
        title=payload.title,
        description=payload.description,
        is_auto_generated=False,
        author_id=author_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    entry = db.query(PCE).filter(PCE.id == entry.id).first()
    return serialize_changelog_entry(entry)


def generate_changelog(
    project_id: str, weeks: int, version_tag: "Optional[str]", author_id: str, db: Session
) -> dict:
    import json as _json
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    since = date.today() - timedelta(weeks=weeks)
    since_dt = datetime.combine(since, datetime.min.time())
    completed_tasks = (
        db.query(_Task)
        .filter(
            _Task.project_id == project_id,
            _Task.status == TaskStatus.done,
            (_Task.updated_at >= since_dt) | (_Task.updated_at == None),
        )
        .order_by(_Task.priority, _Task.updated_at.desc())
        .limit(100)
        .all()
    )
    if not completed_tasks:
        return {"generated": 0, "message": "No hay tareas completadas en el período indicado"}

    def _guess_type(task) -> ChangelogEntryType:
        title_lower = (task.title or "").lower()
        if any(kw in title_lower for kw in ["bug", "fix", "error", "fallo", "corrección"]):
            return ChangelogEntryType.bugfix
        if any(kw in title_lower for kw in ["mejora", "optimiz", "refactor", "perf"]):
            return ChangelogEntryType.improvement
        if any(kw in title_lower for kw in ["roto", "breaking", "elimina", "depreca"]):
            return ChangelogEntryType.breaking
        if task.priority == TaskPriority.critical:
            return ChangelogEntryType.feature
        return ChangelogEntryType.feature

    created_entries = []
    for task in completed_tasks:
        existing = db.query(PCE).filter(
            PCE.project_id == project_id,
            PCE.source_task_ids.contains(f'"{task.id}"'),
        ).first()
        if existing:
            continue
        entry = PCE(
            project_id=project_id,
            version_tag=version_tag,
            entry_date=(task.updated_at or task.created_at).date() if (task.updated_at or task.created_at) else date.today(),
            entry_type=_guess_type(task),
            title=task.title,
            description=task.description,
            is_auto_generated=True,
            source_task_ids=_json.dumps([task.id]),
            author_id=author_id,
        )
        db.add(entry)
        created_entries.append(task.id)
    db.commit()
    return {
        "generated": len(created_entries),
        "version_tag": version_tag,
        "period_weeks": weeks,
        "task_ids": created_entries,
    }


def update_changelog_entry(project_id: str, entry_id: str, payload, db: Session) -> dict:
    entry = db.query(PCE).filter(
        PCE.id == entry_id, PCE.project_id == project_id
    ).first()
    if not entry:
        raise ValueError("Entrada no encontrada")
    if payload.version_tag is not None:
        entry.version_tag = payload.version_tag
    if payload.entry_date is not None:
        entry.entry_date = payload.entry_date
    if payload.entry_type is not None:
        try:
            entry.entry_type = ChangelogEntryType(payload.entry_type)
        except ValueError:
            raise ValueError(f"422:Tipo inválido: '{payload.entry_type}'")
    if payload.title is not None:
        entry.title = payload.title
    if payload.description is not None:
        entry.description = payload.description
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    entry = db.query(PCE).filter(PCE.id == entry.id).first()
    return serialize_changelog_entry(entry)


def delete_changelog_entry(project_id: str, entry_id: str, db: Session) -> None:
    entry = db.query(PCE).filter(
        PCE.id == entry_id, PCE.project_id == project_id
    ).first()
    if not entry:
        raise ValueError("Entrada no encontrada")
    db.delete(entry)
    db.commit()


# ── UAT Cases ─────────────────────────────────────────────────────────────────

def list_uat_cases(
    project_id: str, status: "Optional[str]", task_id: "Optional[str]", db: Session
) -> dict:
    q = db.query(UATCase).filter(UATCase.project_id == project_id)
    if status:
        try:
            q = q.filter(UATCase.status == UATStatus(status))
        except ValueError:
            pass
    if task_id:
        q = q.filter(UATCase.task_id == task_id)
    cases = q.order_by(UATCase.created_at.desc()).all()
    stats = {
        "total": len(cases),
        "pending": sum(1 for c in cases if c.status == UATStatus.pending),
        "passed": sum(1 for c in cases if c.status == UATStatus.passed),
        "failed": sum(1 for c in cases if c.status == UATStatus.failed),
        "blocked": sum(1 for c in cases if c.status == UATStatus.blocked),
    }
    return {"cases": [serialize_uat_case(c) for c in cases], "stats": stats}


def create_uat_case(project_id: str, payload, db: Session) -> dict:
    case = UATCase(
        project_id=project_id,
        task_id=payload.task_id or None,
        title=payload.title,
        description=payload.description,
        expected_result=payload.expected_result,
        actual_result=payload.actual_result,
        status=UATStatus(payload.status) if payload.status else UATStatus.pending,
        priority=payload.priority or "medium",
        assigned_to_id=payload.assigned_to_id or None,
        notes=payload.notes,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize_uat_case(case)


def update_uat_case(project_id: str, case_id: str, payload, db: Session) -> dict:
    case = db.query(UATCase).filter(
        UATCase.id == case_id, UATCase.project_id == project_id
    ).first()
    if not case:
        raise ValueError("Caso UAT no encontrado")
    for field, val in payload.model_dump(exclude_unset=True).items():
        if field == "status" and val:
            setattr(case, field, UATStatus(val))
        elif field in ("task_id", "assigned_to_id"):
            setattr(case, field, val or None)
        else:
            setattr(case, field, val)
    if payload.status in ("passed", "failed", "blocked"):
        case.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return serialize_uat_case(case)


def delete_uat_case(project_id: str, case_id: str, db: Session) -> None:
    case = db.query(UATCase).filter(
        UATCase.id == case_id, UATCase.project_id == project_id
    ).first()
    if not case:
        raise ValueError("Caso UAT no encontrado")
    db.delete(case)
    db.commit()


def export_uat_report(project_id: str, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    cases = db.query(UATCase).filter(UATCase.project_id == project_id).order_by(UATCase.created_at).all()
    STATUS_EMOJI = {"pending": "⏳", "passed": "✅", "failed": "❌", "blocked": "🔒", "skipped": "⏭"}
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_cases = sorted(cases, key=lambda c: PRIORITY_ORDER.get(c.priority, 2))
    lines = [
        f"# Plan de Pruebas UAT — {project.name}",
        f"Generado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
        "",
        f"Total: {len(cases)} casos | "
        f"Pendientes: {sum(1 for c in cases if c.status == UATStatus.pending)} | "
        f"Pasados: {sum(1 for c in cases if c.status == UATStatus.passed)} | "
        f"Fallidos: {sum(1 for c in cases if c.status == UATStatus.failed)}",
        "",
        "---",
    ]
    for i, c in enumerate(sorted_cases, 1):
        st = STATUS_EMOJI.get(c.status.value, "?")
        lines += [
            "",
            f"## {i}. {c.title}  {st}",
            f"**Prioridad:** {c.priority.upper()}  |  **Estado:** {c.status.value}",
        ]
        if c.task_title:
            lines.append(f"**Tarea vinculada:** {c.task_title}")
        if c.description:
            lines += ["", "**Pasos a ejecutar:**", c.description]
        if c.expected_result:
            lines += ["", "**Resultado esperado:**", c.expected_result]
        if c.actual_result:
            lines += ["", "**Resultado obtenido:**", c.actual_result]
        if c.notes:
            lines += ["", "**Notas:**", c.notes]
    return {"project_name": project.name, "text": "\n".join(lines), "cases_count": len(cases)}
