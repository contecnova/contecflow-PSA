"""
raci — Market-leader feature expansion:
  1. RACI Matrix         GET/PUT /projects/{id}/raci
                         DELETE  /projects/{id}/raci/{entry_id}
  2. Sprint Retrospective GET  /projects/{pid}/sprints/{sid}/retrospective
                          PUT  /projects/{pid}/sprints/{sid}/retrospective
  3. Burnout Risk Monitor GET  /resources/burnout-risk
                          POST /resources/burnout-risk/compute
  4. Project Changelog    GET  /projects/{id}/changelog
                          POST /projects/{id}/changelog          (manual entry)
                          POST /projects/{id}/changelog/generate (auto from tasks)
                          PATCH/DELETE /projects/{id}/changelog/{entry_id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from app.core.ratelimit import limiter
from fastapi import Request
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserStatus
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.project import Project, ProjectStatus, ProjectPhase
from app.models.sprints import Sprint, SprintTask, SprintStatus
from app.models.imputation import Imputation
from app.models.raci import (
    RACIEntry, RACIRole,
    SprintRetroNote,
    BurnoutRiskSnapshot, BurnoutRiskLevel,
    ProjectChangelogEntry, ChangelogEntryType,
    UATCase, UATStatus,
)
from app.services.raci_service import (
    serialize_user as _user_out,
    serialize_raci_entry as _raci_entry_out,
    compute_retro_insights as _compute_retro_insights,
    compute_user_burnout_risk as _compute_user_burnout_risk,
    serialize_changelog_entry as _entry_out,
    serialize_uat_case as _uat_out,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# 1. RACI MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

class RACIEntryIn(BaseModel):
    item_type:  str              # deliverable | milestone | phase | custom
    item_label: str
    item_id:    Optional[str] = None
    user_id:    str
    role:       str              # R | A | C | I


class RACIBatchIn(BaseModel):
    entries: List[RACIEntryIn]


@router.get("/projects/{project_id}/raci", summary="RACI Matrix del proyecto",
            tags=["v25 — RACI"])
def get_project_raci(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    entries = (
        db.query(RACIEntry)
        .filter(RACIEntry.project_id == project_id)
        .order_by(RACIEntry.item_type, RACIEntry.item_label)
        .all()
    )

    # Group into matrix: {item_label → {user_id → role}}
    items: dict = {}
    for e in entries:
        key = (e.item_type, e.item_label, e.item_id or "")
        if key not in items:
            items[key] = {"item_type": e.item_type, "item_label": e.item_label,
                          "item_id": e.item_id, "assignments": []}
        items[key]["assignments"].append({
            "entry_id": e.id, "user_id": e.user_id, "role": e.role.value,
            "user": _user_out(e.user) if e.user else None,
        })

    return {
        "project_id": project_id,
        "project_name": project.name,
        "items": list(items.values()),
        "raw_entries": [_raci_entry_out(e) for e in entries],
        "total": len(entries),
    }


@router.put("/projects/{project_id}/raci", summary="Guardar/actualizar entradas RACI (batch upsert)",
            tags=["v25 — RACI"])
def upsert_raci(
    project_id: str,
    payload: RACIBatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    created, updated = 0, 0
    for entry_in in payload.entries:
        try:
            role_enum = RACIRole(entry_in.role.upper())
        except ValueError:
            raise HTTPException(422, f"Rol RACI inválido: '{entry_in.role}'. Usa R, A, C o I.")

        user = db.query(User).filter(User.id == entry_in.user_id).first()
        if not user:
            raise HTTPException(404, f"Usuario {entry_in.user_id} no encontrado")

        # Upsert: one entry per (project, item_label, user)
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


@router.delete("/projects/{project_id}/raci/{entry_id}", summary="Eliminar entrada RACI",
               status_code=204, tags=["v25 — RACI"])
def delete_raci_entry(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    entry = db.query(RACIEntry).filter(
        RACIEntry.id == entry_id, RACIEntry.project_id == project_id
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada RACI no encontrada")
    db.delete(entry)
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPRINT RETROSPECTIVE AI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/sprints/{sprint_id}/retrospective",
    summary="Insights de retrospectiva del sprint (AI algorítmico)",
    tags=["v25 — Sprint Retrospective"],
)
def get_sprint_retrospective(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprint = db.query(Sprint).filter(
        Sprint.id == sprint_id, Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise HTTPException(404, "Sprint no encontrado")

    insights = _compute_retro_insights(sprint, db)

    # Load saved notes if exist
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
            "action_items": json.loads(saved.action_items) if saved and saved.action_items else [],
            "updated_at": saved.updated_at.isoformat() if saved and saved.updated_at else None,
        } if saved else None,
    }


class RetroNotesIn(BaseModel):
    manual_notes: Optional[str] = None
    action_items: Optional[List[dict]] = None   # [{text, owner_id}]


@router.put(
    "/projects/{project_id}/sprints/{sprint_id}/retrospective",
    summary="Guardar notas de retrospectiva",
    tags=["v25 — Sprint Retrospective"],
)
def save_sprint_retrospective(
    project_id: str,
    sprint_id: str,
    payload: RetroNotesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprint = db.query(Sprint).filter(
        Sprint.id == sprint_id, Sprint.project_id == project_id
    ).first()
    if not sprint:
        raise HTTPException(404, "Sprint no encontrado")

    insights = _compute_retro_insights(sprint, db)
    m = insights["metrics"]

    saved = db.query(SprintRetroNote).filter(SprintRetroNote.sprint_id == sprint_id).first()
    if saved:
        saved.manual_notes = payload.manual_notes
        if payload.action_items is not None:
            saved.action_items = json.dumps(payload.action_items)
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
            went_well_items=json.dumps(insights["went_well"]),
            improve_items=json.dumps(insights["improve"]),
            action_items=json.dumps(payload.action_items or insights["actions"]),
            risk_flags=json.dumps(insights["risks"]),
            manual_notes=payload.manual_notes,
            facilitated_by_id=current_user.id,
        )
        db.add(saved)

    db.commit()
    db.refresh(saved)
    return {"id": saved.id, "sprint_id": sprint_id, "updated_at": saved.updated_at.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BURNOUT RISK MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_user_burnout_risk(user: User, db: Session, today: date) -> dict:
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
        weeks_data.append({"week_start": week_start, "hours": hours,
                            "capacity": capacity, "load_pct": round(hours / capacity * 100, 1)})

    # Most recent week (index 0 = current week, index 1 = last week, index 7 = 7 weeks ago)
    # week_end for index w is computed as: start-of-current-week + (1 - w) weeks
    current_load    = weeks_data[0]["load_pct"] if weeks_data else 0
    avg_load_4w     = sum(w["load_pct"] for w in weeks_data[:4]) / 4 if len(weeks_data) >= 4 else current_load

    # Consecutive weeks >100%
    streak = 0
    for w in weeks_data:
        if w["load_pct"] > 100:
            streak += 1
        else:
            break

    # Risk score (0-100): weighted combination
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
            {"week_start": w["week_start"].isoformat(), "load_pct": w["load_pct"], "hours": round(w["hours"], 1)}
            for w in weeks_data
        ],
    }


@router.get("/resources/burnout-risk", summary="Monitor de riesgo de burnout del equipo",
            tags=["v25 — Burnout Monitor"])
def get_burnout_risk(
    department: Optional[str] = Query(None),
    min_risk_level: Optional[str] = Query(None, description="green|yellow|orange|red"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    today = date.today()

    q = db.query(User).filter(User.is_active == True, User.status == UserStatus.active)
    if department:
        q = q.filter(User.department == department)

    users = q.all()
    results = [_compute_user_burnout_risk(u, db, today) for u in users]

    # Apply risk level filter
    if min_risk_level:
        order = [BurnoutRiskLevel.green.value, BurnoutRiskLevel.yellow.value,
                 BurnoutRiskLevel.orange.value, BurnoutRiskLevel.red.value]
        try:
            min_idx = order.index(min_risk_level)
            results = [r for r in results if order.index(r["risk_level"]) >= min_idx]
        except ValueError:
            pass

    results.sort(key=lambda r: r["risk_score"], reverse=True)

    # Summary stats
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


@router.post("/resources/burnout-risk/compute", summary="Recalcular y persistir snapshots de burnout",
             tags=["v25 — Burnout Monitor"])
@limiter.limit("10/minute")
def compute_and_save_burnout_snapshots(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    users = db.query(User).filter(User.is_active == True, User.status == UserStatus.active).all()

    saved = 0
    for user in users:
        risk_data = _compute_user_burnout_risk(user, db, today)

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
            existing.factors = json.dumps(risk_data["factors"])
        else:
            db.add(BurnoutRiskSnapshot(
                user_id=user.id,
                week_start=week_start,
                load_pct=risk_data["current_load_pct"],
                overload_weeks_streak=risk_data["overload_weeks_streak"],
                avg_load_4w=risk_data["avg_load_4w"],
                risk_level=level,
                risk_score=risk_data["risk_score"],
                factors=json.dumps(risk_data["factors"]),
            ))
            saved += 1

    db.commit()
    return {"week_start": week_start.isoformat(), "processed": len(users), "new_snapshots": saved}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PROJECT CHANGELOG / RELEASE NOTES
# ═══════════════════════════════════════════════════════════════════════════════

class ChangelogEntryIn(BaseModel):
    version_tag: Optional[str] = None
    entry_date:  date
    entry_type:  str = "feature"   # feature | bugfix | improvement | milestone | breaking
    title:       str
    description: Optional[str] = None


class ChangelogEntryPatch(BaseModel):
    version_tag: Optional[str] = None
    entry_date:  Optional[date] = None
    entry_type:  Optional[str] = None
    title:       Optional[str] = None
    description: Optional[str] = None


@router.get("/projects/{project_id}/changelog", summary="Changelog del proyecto",
            tags=["v25 — Changelog"])
def get_project_changelog(
    project_id: str,
    entry_type: Optional[str] = Query(None),
    since: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    q = db.query(ProjectChangelogEntry).filter(ProjectChangelogEntry.project_id == project_id)
    if entry_type:
        try:
            q = q.filter(ProjectChangelogEntry.entry_type == ChangelogEntryType(entry_type))
        except ValueError:
            pass
    if since:
        q = q.filter(ProjectChangelogEntry.entry_date >= since)
    entries = q.order_by(ProjectChangelogEntry.entry_date.desc()).all()

    return {
        "project_id": project_id,
        "project_name": project.name,
        "total": len(entries),
        "entries": [_entry_out(e) for e in entries],
    }


@router.post("/projects/{project_id}/changelog", summary="Añadir entrada manual al changelog",
             tags=["v25 — Changelog"])
def create_changelog_entry(
    project_id: str,
    payload: ChangelogEntryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    try:
        entry_type = ChangelogEntryType(payload.entry_type)
    except ValueError:
        raise HTTPException(422, f"Tipo de entrada inválido: '{payload.entry_type}'")

    entry = ProjectChangelogEntry(
        project_id=project_id,
        version_tag=payload.version_tag,
        entry_date=payload.entry_date,
        entry_type=entry_type,
        title=payload.title,
        description=payload.description,
        is_auto_generated=False,
        author_id=current_user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # eager-load author
    entry = db.query(ProjectChangelogEntry).filter(ProjectChangelogEntry.id == entry.id).first()
    return _entry_out(entry)


@router.post("/projects/{project_id}/changelog/generate",
             summary="Generar changelog automático desde tareas completadas (últimas N semanas)",
             tags=["v25 — Changelog"])
def generate_changelog(
    project_id: str,
    weeks: int = Body(default=2, embed=True, ge=1, le=52),
    version_tag: Optional[str] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    since = date.today() - timedelta(weeks=weeks)
    since_dt = datetime.combine(since, datetime.min.time())
    completed_tasks = (
        db.query(Task)
        .filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.done,
            # Include tasks updated OR created within the period (updated_at may be NULL)
            (Task.updated_at >= since_dt) | (Task.updated_at == None),
        )
        .order_by(Task.priority, Task.updated_at.desc())
        .limit(100)
        .all()
    )

    if not completed_tasks:
        return {"generated": 0, "message": "No hay tareas completadas en el período indicado"}

    # Map task priority/tags to entry type heuristically
    def _guess_type(task: Task) -> ChangelogEntryType:
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
        # Use JSON list membership check: task ID is a UUID (36 chars), so
        # checking for '"<uuid>"' (quoted) avoids false-positive LIKE matches.
        existing = db.query(ProjectChangelogEntry).filter(
            ProjectChangelogEntry.project_id == project_id,
            ProjectChangelogEntry.source_task_ids.contains(f'"{task.id}"'),
        ).first()
        if existing:
            continue  # Skip already generated

        entry = ProjectChangelogEntry(
            project_id=project_id,
            version_tag=version_tag,
            entry_date=(task.updated_at or task.created_at).date() if (task.updated_at or task.created_at) else date.today(),
            entry_type=_guess_type(task),
            title=task.title,
            description=task.description,
            is_auto_generated=True,
            source_task_ids=json.dumps([task.id]),
            author_id=current_user.id,
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


@router.patch("/projects/{project_id}/changelog/{entry_id}",
              summary="Editar entrada del changelog",
              tags=["v25 — Changelog"])
def update_changelog_entry(
    project_id: str,
    entry_id: str,
    payload: ChangelogEntryPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    entry = db.query(ProjectChangelogEntry).filter(
        ProjectChangelogEntry.id == entry_id,
        ProjectChangelogEntry.project_id == project_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")

    if payload.version_tag is not None:
        entry.version_tag = payload.version_tag
    if payload.entry_date is not None:
        entry.entry_date = payload.entry_date
    if payload.entry_type is not None:
        try:
            entry.entry_type = ChangelogEntryType(payload.entry_type)
        except ValueError:
            raise HTTPException(422, f"Tipo inválido: '{payload.entry_type}'")
    if payload.title is not None:
        entry.title = payload.title
    if payload.description is not None:
        entry.description = payload.description
    entry.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(entry)
    entry = db.query(ProjectChangelogEntry).filter(ProjectChangelogEntry.id == entry.id).first()
    return _entry_out(entry)


@router.delete("/projects/{project_id}/changelog/{entry_id}",
               summary="Eliminar entrada del changelog",
               status_code=204, tags=["v25 — Changelog"])
def delete_changelog_entry(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    entry = db.query(ProjectChangelogEntry).filter(
        ProjectChangelogEntry.id == entry_id,
        ProjectChangelogEntry.project_id == project_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Entrada no encontrada")
    db.delete(entry)
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. UAT CASES
# ═══════════════════════════════════════════════════════════════════════════════

class UATCaseIn(BaseModel):
    title: str
    description: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    status: Optional[str] = "pending"
    priority: Optional[str] = "medium"
    task_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("/projects/{project_id}/uat",
            summary="Lista de casos UAT del proyecto",
            tags=["v25 — UAT"])
def list_uat_cases(
    project_id: str,
    status: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    return {"cases": [_uat_out(c) for c in cases], "stats": stats}


@router.post("/projects/{project_id}/uat",
             summary="Crear caso UAT",
             status_code=201, tags=["v25 — UAT"])
def create_uat_case(
    project_id: str,
    payload: UATCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    return _uat_out(case)


@router.patch("/projects/{project_id}/uat/{case_id}",
              summary="Actualizar caso UAT",
              tags=["v25 — UAT"])
def update_uat_case(
    project_id: str,
    case_id: str,
    payload: UATCaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.query(UATCase).filter(
        UATCase.id == case_id,
        UATCase.project_id == project_id,
    ).first()
    if not case:
        raise HTTPException(404, "Caso UAT no encontrado")
    for field, val in payload.model_dump(exclude_unset=True).items():
        if field == "status" and val:
            setattr(case, field, UATStatus(val))
        elif field == "task_id":
            setattr(case, field, val or None)
        elif field == "assigned_to_id":
            setattr(case, field, val or None)
        else:
            setattr(case, field, val)
    if payload.status in ("passed", "failed", "blocked"):
        from datetime import datetime, timezone
        case.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return _uat_out(case)


@router.delete("/projects/{project_id}/uat/{case_id}",
               summary="Eliminar caso UAT",
               status_code=204, tags=["v25 — UAT"])
def delete_uat_case(
    project_id: str,
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    case = db.query(UATCase).filter(
        UATCase.id == case_id,
        UATCase.project_id == project_id,
    ).first()
    if not case:
        raise HTTPException(404, "Caso UAT no encontrado")
    db.delete(case)
    db.commit()


@router.get("/projects/{project_id}/uat/export",
            summary="Exportar UAT como texto estructurado para cliente",
            tags=["v25 — UAT"])
def export_uat_report(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns a structured summary ready to share with the client."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
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
