"""
activity_service.py — Business logic for activity feeds, mentions, project health,
recurring tasks, CPM critical path, resource demand, vendor scorecard, and what-if
simulation.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.activity import ActivityEvent, ProjectHealthSnapshot, RecurringTask, RecurringFreqType, ResourceDemandForecast, VendorScore
from app.models.alm import ALMVendor
from app.models.bookings import TaskDependency
from app.models.enterprise import Notification
from app.models.enterprise import NotificationType
from app.models.epics import Mention
from app.models.financial import Timesheet, ProjectMilestone
from app.models.imputation import Imputation
from app.models.mfa import Budget
from app.models.nps import ClientHealthSnapshot
from app.models.pipeline import Opportunity, OpportunityStage
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
TaskModel = Task
from fastapi import HTTPException


# ═══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL HELPERS (emit_activity, create_notification, parse_and_store_mentions)
# ═══════════════════════════════════════════════════════════════════════════════

def emit_activity(
    db: Session,
    entity_type: str,
    entity_id: str,
    entity_code: Optional[str],
    actor: User,
    verb: str,
    detail: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_name: Optional[str] = None,
) -> None:
    event = ActivityEvent(
        organization_id=getattr(actor, "organization_id", None),
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=entity_code,
        actor_id=actor.id,
        actor_name=actor.full_name or actor.email,
        verb=verb,
        detail=detail,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
    )
    db.add(event)


def create_notification(
    db: Session,
    user_id: str,
    notif_type,
    title: str,
    body: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
) -> None:
    n = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        resource=resource,
        resource_id=resource_id,
        action_url=action_url,
        icon="💬",
        color="#7c3aed",
    )
    db.add(n)


def parse_and_store_mentions(
    db: Session,
    content: str,
    actor: User,
    entity_type: str,
    entity_id: str,
    action_url: Optional[str] = None,
) -> List[str]:
    """
    Extract @<user_id> or @<username> tags from content, persist Mention rows
    and create Notifications for each mentioned user.
    Returns list of mentioned user_ids found.
    """

    pattern = r"@([A-Za-z0-9_\-\.]+)"
    tokens = re.findall(pattern, content)
    if not tokens:
        return []

    mentioned_ids: List[str] = []
    for token in tokens:
        user = (
            db.query(User).filter(
                (User.id == token) | (User.username == token)
            ).first()
        )
        if not user or user.id == actor.id:
            continue
        if user.id in mentioned_ids:
            continue
        mentioned_ids.append(user.id)

        mention = Mention(
            mentioned_user=user.id,
            mentioned_by=actor.id,
            entity_type=entity_type,
            entity_id=entity_id,
            context_text=content[:500],
        )
        db.add(mention)

        snippet = content[:120] + ("…" if len(content) > 120 else "")
        create_notification(
            db, user.id, NotificationType.mention,
            title=f"{actor.full_name or actor.email} te ha mencionado",
            body=snippet,
            resource=entity_type,
            resource_id=entity_id,
            action_url=action_url,
        )

    if mentioned_ids:
        db.commit()
    return mentioned_ids


# ═══════════════════════════════════════════════════════════════════════════════
# SSE LIVE UPDATES HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_new_notifications(db: Session, user_id: str, since: datetime) -> list:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.created_at > since)
        .order_by(Notification.created_at)
        .all()
    )


def get_new_activity_events(db: Session, user_id: str, since: datetime) -> list:
    return (
        db.query(ActivityEvent)
        .filter(ActivityEvent.created_at > since, ActivityEvent.actor_id != user_id)
        .limit(20)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY FEED
# ═══════════════════════════════════════════════════════════════════════════════

def activity_feed_payload(
    db: Session,
    entity_type: str,
    entity_id: str,
    limit: int,
    before: Optional[str],
) -> list:
    q = db.query(ActivityEvent).filter(
        ActivityEvent.entity_type == entity_type,
        ActivityEvent.entity_id == entity_id,
    )
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
            q = q.filter(ActivityEvent.created_at < before_dt)
        except ValueError:
            pass
    events = q.order_by(ActivityEvent.created_at.desc()).limit(limit).all()
    return [{
        "id": e.id,
        "actor_name": e.actor_name,
        "actor_id": e.actor_id,
        "verb": e.verb,
        "detail": e.detail,
        "target_type": e.target_type,
        "target_name": e.target_name,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


def project_activity_payload(db: Session, project_id: str, limit: int) -> list:
    task_ids = [t.id for t in db.query(Task.id).filter(Task.project_id == project_id).all()]
    q = db.query(ActivityEvent).filter(
        ((ActivityEvent.entity_type == "project") & (ActivityEvent.entity_id == project_id)) |
        ((ActivityEvent.entity_type == "task") & (ActivityEvent.entity_id.in_(task_ids)))
    ).order_by(ActivityEvent.created_at.desc()).limit(limit)
    events = q.all()
    return [{
        "id": e.id,
        "entity_type": e.entity_type,
        "entity_code": e.entity_code,
        "actor_name": e.actor_name,
        "verb": e.verb,
        "detail": e.detail,
        "target_name": e.target_name,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


# ═══════════════════════════════════════════════════════════════════════════════
# MENTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def my_mentions_payload(
    db: Session,
    current_user: User,
    unread_only: bool,
    limit: int,
) -> list:
    q = db.query(Mention).filter(Mention.mentioned_user == current_user.id)
    if unread_only:
        q = q.filter(Mention.is_read == False)
    mentions = q.order_by(Mention.created_at.desc()).limit(limit).all()

    actor_ids = {m.mentioned_by for m in mentions if m.mentioned_by}
    actors = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(actor_ids)).all()}

    return [{
        "id": m.id,
        "entity_type": m.entity_type,
        "entity_id": m.entity_id,
        "mentioned_by_name": actors.get(m.mentioned_by, "—"),
        "context": m.context_text,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in mentions]


def mark_mention_read_record(db: Session, mention_id: str, current_user: User) -> dict:
    m = db.query(Mention).filter(
        Mention.id == mention_id,
        Mention.mentioned_user == current_user.id,
    ).first()
    if not m:
        raise HTTPException(404)
    m.is_read = True
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

def compute_health(db: Session, project_id: str) -> dict:
    """Compute composite health score (0-100) from live signals."""

    today = date.today()

    total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project_id).scalar() or 0
    overdue = db.query(func.count(Task.id)).filter(
        Task.project_id == project_id,
        Task.due_date < today,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).scalar() or 0
    schedule_score = round(max(0, 100 - (overdue / max(total_tasks, 1)) * 100), 1)

    budget_score = 80.0
    budget = db.query(Budget).filter(Budget.project_id == project_id).first()
    if budget and budget.total_amount:
        actual_cost_q = db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == project_id
        ).scalar() or 0
        project = db.query(Project).filter(Project.id == project_id).first()
        estimated_hours = getattr(project, "estimated_hours", None)
        if estimated_hours and estimated_hours > 0:
            from app.core.config import settings as _s
            ratio = actual_cost_q / estimated_hours
            if ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_GOOD:
                budget_score = 100.0
            elif ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_OK:
                budget_score = 80.0
            elif ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_WARN:
                budget_score = 50.0
            else:
                budget_score = 20.0

    open_risks = db.query(func.count(Task.id)).filter(
        Task.project_id == project_id,
        Task.issue_type == "bug",
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).scalar() or 0
    quality_score = round(max(0, 100 - min(open_risks * 10, 100)), 1)

    velocity_score = 70.0

    project_obj = db.query(Project).filter(Project.id == project_id).first()
    client_score = 75.0
    if project_obj and project_obj.client_id:
        latest_nps = db.query(ClientHealthSnapshot).filter(
            ClientHealthSnapshot.client_id == project_obj.client_id
        ).order_by(ClientHealthSnapshot.snapshot_at.desc()).first()
        if latest_nps:
            client_score = min(100.0, latest_nps.health_score)

    from app.core.config import settings as _s
    composite = round(
        schedule_score * _s.PROJECT_HEALTH_WEIGHT_SCHEDULE +
        budget_score   * _s.PROJECT_HEALTH_WEIGHT_BUDGET +
        quality_score  * _s.PROJECT_HEALTH_WEIGHT_QUALITY +
        velocity_score * _s.PROJECT_HEALTH_WEIGHT_VELOCITY +
        client_score   * _s.PROJECT_HEALTH_WEIGHT_CLIENT,
        1
    )

    return {
        "score": composite,
        "schedule_score": schedule_score,
        "budget_score": budget_score,
        "quality_score": quality_score,
        "velocity_score": velocity_score,
        "client_score": client_score,
        "traffic_light": "green" if composite >= _s.PROJECT_HEALTH_TRAFFIC_GREEN else ("yellow" if composite >= _s.PROJECT_HEALTH_TRAFFIC_YELLOW else "red"),
        "overdue_tasks": overdue,
        "total_tasks": total_tasks,
        "open_bugs": open_risks,
    }


def project_health_payload(db: Session, project_id: str) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    data = compute_health(db, project_id)
    history = db.query(ProjectHealthSnapshot).filter(
        ProjectHealthSnapshot.project_id == project_id
    ).order_by(ProjectHealthSnapshot.snapshot_at.desc()).limit(30).all()
    return {
        "project_id": project_id,
        "project_name": project.name,
        "current": data,
        "history": [{
            "score": h.score,
            "traffic_light": "green" if h.score >= 70 else ("yellow" if h.score >= 45 else "red"),
            "snapshot_at": h.snapshot_at.isoformat() if h.snapshot_at else None,
        } for h in history],
    }


def save_health_snapshot_record(db: Session, project_id: str) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    data = compute_health(db, project_id)
    snap = ProjectHealthSnapshot(
        project_id=project_id,
        score=data["score"],
        schedule_score=data["schedule_score"],
        budget_score=data["budget_score"],
        quality_score=data["quality_score"],
        velocity_score=data["velocity_score"],
        client_score=data["client_score"],
        detail=json.dumps({k: v for k, v in data.items() if k not in ("score",)}),
    )
    db.add(snap)
    db.commit()
    return {"id": snap.id, **data}


def portfolio_health_payload(db: Session) -> list:
    projects = db.query(Project).filter(
        Project.status.in_([ProjectStatus.active, ProjectStatus.planning])
    ).all()
    result = []
    for p in projects:
        data = compute_health(db, p.id)
        result.append({
            "project_id": p.id,
            "project_code": p.code,
            "project_name": p.name,
            "score": data["score"],
            "traffic_light": data["traffic_light"],
            "overdue_tasks": data["overdue_tasks"],
        })
    result.sort(key=lambda x: x["score"])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# RECURRING TASKS
# ═══════════════════════════════════════════════════════════════════════════════

def list_recurring_tasks_payload(
    db: Session,
    project_id: Optional[str],
    is_active: Optional[bool],
) -> list:
    q = db.query(RecurringTask)
    if project_id:
        q = q.filter(RecurringTask.project_id == project_id)
    if is_active is not None:
        q = q.filter(RecurringTask.is_active == is_active)
    rts = q.order_by(RecurringTask.start_date).all()
    return [{
        "id": r.id, "project_id": r.project_id, "title": r.title,
        "freq": r.freq, "interval_days": r.interval_days,
        "start_date": str(r.start_date), "end_date": str(r.end_date) if r.end_date else None,
        "last_generated": str(r.last_generated) if r.last_generated else None,
        "is_active": r.is_active, "priority": r.priority,
        "assignee_id": r.assignee_id, "due_offset_days": r.due_offset_days,
    } for r in rts]


def create_recurring_task_record(db: Session, payload, current_user: User) -> dict:
    try:
        RecurringFreqType(payload.freq)
    except ValueError:
        raise HTTPException(400, f"Invalid freq: {payload.freq}. Use: daily, weekly, monthly, custom")
    try:
        start = date.fromisoformat(payload.start_date)
    except ValueError:
        raise HTTPException(400, "start_date must be YYYY-MM-DD")
    end = date.fromisoformat(payload.end_date) if payload.end_date else None
    rt = RecurringTask(
        **{k: v for k, v in payload.model_dump().items() if k not in ("start_date", "end_date")},
        start_date=start,
        end_date=end,
        created_by=current_user.id,
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return {"id": rt.id, "title": rt.title}


def update_recurring_task_record(db: Session, rt_id: str, payload) -> dict:
    rt = db.query(RecurringTask).filter(RecurringTask.id == rt_id).first()
    if not rt:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k in ("start_date", "end_date"):
            v = date.fromisoformat(v) if v else None
        setattr(rt, k, v)
    db.commit()
    return {"ok": True}


def delete_recurring_task_record(db: Session, rt_id: str) -> dict:
    rt = db.query(RecurringTask).filter(RecurringTask.id == rt_id).first()
    if not rt:
        raise HTTPException(404)
    db.delete(rt)
    db.commit()
    return {"ok": True}


def materialize_recurring_tasks_cmd(db: Session, dry_run: bool, current_user: User) -> dict:
    import re as _re

    def _next_task_code(session) -> str:
        max_code = session.query(func.max(TaskModel.code)).scalar()
        if max_code:
            m = _re.search(r"(\d+)$", max_code)
            n = (int(m.group(1)) + 1) if m else 1
        else:
            n = 1
        return f"TSK-{n:05d}"

    today = date.today()
    active = db.query(RecurringTask).filter(
        RecurringTask.is_active == True,
        RecurringTask.start_date <= today,
    ).all()

    created = 0
    for rt in active:
        if rt.end_date and rt.end_date < today:
            rt.is_active = False
            continue

        last = rt.last_generated or (rt.start_date - timedelta(days=1))
        next_occ = last + timedelta(days=1)
        occurrences = []
        while next_occ <= today:
            should_fire = False
            if rt.freq == RecurringFreqType.daily:
                should_fire = True
            elif rt.freq == RecurringFreqType.weekly:
                should_fire = (next_occ - rt.start_date).days % 7 == 0
            elif rt.freq == RecurringFreqType.monthly:
                should_fire = next_occ.day == rt.start_date.day
            elif rt.freq == RecurringFreqType.custom:
                should_fire = (next_occ - rt.start_date).days % max(rt.interval_days, 1) == 0

            if should_fire:
                if rt.weekday_mask:
                    day_bit = 1 << next_occ.weekday()
                    if not (rt.weekday_mask & day_bit):
                        next_occ += timedelta(days=1)
                        continue
                occurrences.append(next_occ)
            next_occ += timedelta(days=1)

        for occ_date in occurrences:
            if dry_run:
                created += 1
                continue
            code = _next_task_code(db)
            due = occ_date + timedelta(days=rt.due_offset_days)
            task = TaskModel(
                code=code,
                project_id=rt.project_id,
                title=f"{rt.title} [{occ_date.strftime('%d/%m/%Y')}]",
                description=rt.description,
                priority=rt.priority,
                assignee_id=rt.assignee_id,
                estimated_hours=rt.estimated_hours,
                story_points=rt.story_points,
                start_date=occ_date,
                due_date=due,
                created_by=current_user.id,
            )
            db.add(task)
            db.flush()
            rt.last_generated = occ_date
            created += 1

    if not dry_run:
        db.commit()
    return {"ok": True, "dry_run": dry_run, "tasks_created": created}


# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL PATH (CPM)
# ═══════════════════════════════════════════════════════════════════════════════

def critical_path_payload(db: Session, project_id: str) -> dict:

    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status != TaskStatus.cancelled,
    ).all()
    if not tasks:
        raise HTTPException(404, "No tasks found for this project")

    task_map = {t.id: t for t in tasks}
    deps = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id.in_(task_map.keys()),
        TaskDependency.successor_id.in_(task_map.keys()),
    ).all()

    successors: dict = {tid: [] for tid in task_map}
    predecessors: dict = {tid: [] for tid in task_map}
    for d in deps:
        successors[d.predecessor_id].append((d.successor_id, d.lag_days or 0))
        predecessors[d.successor_id].append((d.predecessor_id, d.lag_days or 0))

    def dur(t: Task) -> float:
        if t.estimated_hours:
            return max(1, t.estimated_hours / 8)
        if t.start_date and t.due_date:
            return max(1, (t.due_date - t.start_date).days + 1)
        return 1.0

    in_degree = {tid: len(predecessors[tid]) for tid in task_map}
    queue = [tid for tid, d in in_degree.items() if d == 0]
    topo_order = []
    while queue:
        n = queue.pop(0)
        topo_order.append(n)
        for (succ, _) in successors[n]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    for tid in task_map:
        if tid not in topo_order:
            topo_order.append(tid)

    ES: dict = {tid: 0.0 for tid in task_map}
    EF: dict = {}
    for tid in topo_order:
        if predecessors[tid]:
            ES[tid] = max(EF[pid] + lag for pid, lag in predecessors[tid] if pid in EF)
        EF[tid] = ES[tid] + dur(task_map[tid])

    project_duration = max(EF.values()) if EF else 0

    LF: dict = {tid: project_duration for tid in task_map}
    LS: dict = {}
    for tid in reversed(topo_order):
        if successors[tid]:
            LF[tid] = min(LS[sid] - lag for sid, lag in successors[tid] if sid in LS)
        LS[tid] = LF[tid] - dur(task_map[tid])

    nodes = []
    for tid in topo_order:
        t = task_map[tid]
        float_val = round(LS[tid] - ES[tid], 2)
        nodes.append({
            "id": t.id,
            "code": t.code,
            "title": t.title,
            "duration_days": round(dur(t), 1),
            "early_start": round(ES[tid], 2),
            "early_finish": round(EF[tid], 2),
            "late_start": round(LS[tid], 2),
            "late_finish": round(LF[tid], 2),
            "total_float": float_val,
            "is_critical": float_val <= 0,
            "status": t.status.value,
            "assignee_id": t.assignee_id,
        })

    critical_path = [n["code"] for n in nodes if n["is_critical"]]
    nodes.sort(key=lambda x: x["early_start"])

    return {
        "project_id": project_id,
        "project_duration_days": round(project_duration, 1),
        "critical_path": critical_path,
        "nodes": nodes,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE DEMAND
# ═══════════════════════════════════════════════════════════════════════════════

def resource_demand_payload(db: Session, horizon_months: int, min_probability: float) -> dict:

    today = date.today()
    horizon_end = date(
        today.year + (today.month + horizon_months - 1) // 12,
        (today.month + horizon_months - 1) % 12 + 1,
        1,
    )

    active_opps = db.query(Opportunity).filter(
        Opportunity.stage.not_in([OpportunityStage.won, OpportunityStage.lost, OpportunityStage.cancelled]),
        Opportunity.probability >= min_probability,
    ).all()

    opp_ids = [o.id for o in active_opps]
    lines = db.query(ResourceDemandForecast).filter(
        ResourceDemandForecast.opportunity_id.in_(opp_ids)
    ).all() if opp_ids else []

    prob_map = {o.id: o.probability / 100 for o in active_opps}

    by_role: dict = {}
    for line in lines:
        prob = prob_map.get(line.opportunity_id, 1.0)
        weighted = round(line.hours_required * prob, 1)
        role = line.role_or_skill
        if role not in by_role:
            by_role[role] = {"total_hours": 0, "weighted_hours": 0, "opportunities": 0}
        by_role[role]["total_hours"] += line.hours_required
        by_role[role]["weighted_hours"] += weighted
        by_role[role]["opportunities"] += 1

    opp_detail = [{
        "id": o.id, "name": o.name, "probability": o.probability,
        "expected_start": str(o.expected_start_date) if o.expected_start_date else None,
        "expected_hours": o.expected_hours,
        "expected_revenue": o.expected_revenue,
        "demand_lines": [{
            "role": l.role_or_skill, "hours": l.hours_required,
            "weighted_hours": round(l.hours_required * prob_map.get(o.id, 1.0), 1),
        } for l in lines if l.opportunity_id == o.id],
    } for o in active_opps if any(l.opportunity_id == o.id for l in lines)]

    return {
        "horizon_months": horizon_months,
        "min_probability": min_probability,
        "opportunities_in_scope": len(active_opps),
        "demand_by_role": [
            {"role": role, **data}
            for role, data in sorted(by_role.items(), key=lambda x: -x[1]["weighted_hours"])
        ],
        "opportunity_breakdown": opp_detail,
    }


def create_demand_line_record(db: Session, payload) -> dict:
    opp = db.query(Opportunity).filter(Opportunity.id == payload.opportunity_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    d = payload.model_dump()
    if d.get("start_date"):
        d["start_date"] = date.fromisoformat(d["start_date"])
    if d.get("end_date"):
        d["end_date"] = date.fromisoformat(d["end_date"])
    d["weighted_hours"] = round(d["hours_required"] * opp.probability / 100, 1)
    line = ResourceDemandForecast(**d)
    db.add(line)
    db.commit()
    return {"id": line.id}


def delete_demand_line_record(db: Session, line_id: str) -> dict:
    line = db.query(ResourceDemandForecast).filter(ResourceDemandForecast.id == line_id).first()
    if not line:
        raise HTTPException(404)
    db.delete(line)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# VENDOR SCORECARD
# ═══════════════════════════════════════════════════════════════════════════════

def score_composite(s) -> float:
    scores = [
        s.sla_score, s.quality_score, s.support_score,
        s.price_score, s.innovation_score, s.compliance_score,
    ]
    weights = [0.25, 0.20, 0.20, 0.15, 0.10, 0.10]
    total_w = 0.0
    total = 0.0
    for sc, w in zip(scores, weights):
        if sc is not None:
            total += sc * w
            total_w += w
    return round(total / total_w, 2) if total_w > 0 else 0.0


def vendor_scorecard_payload(db: Session, vendor_id: str) -> dict:
    vendor = db.query(ALMVendor).filter(ALMVendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(404)
    scores = db.query(VendorScore).filter(
        VendorScore.vendor_id == vendor_id
    ).order_by(VendorScore.evaluated_at.desc()).all()
    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "category": vendor.category.value if vendor.category else None,
        "evaluations": [{
            "id": s.id,
            "period": s.period,
            "composite_score": s.composite_score,
            "rating": ("Excelente" if (s.composite_score or 0) >= 8 else
                       "Bueno" if (s.composite_score or 0) >= 6 else
                       "Regular" if (s.composite_score or 0) >= 4 else "Deficiente"),
            "sla_score": s.sla_score,
            "quality_score": s.quality_score,
            "support_score": s.support_score,
            "price_score": s.price_score,
            "innovation_score": s.innovation_score,
            "compliance_score": s.compliance_score,
            "incidents_count": s.incidents_count,
            "notes": s.notes,
            "evaluated_at": s.evaluated_at.isoformat() if s.evaluated_at else None,
        } for s in scores],
        "latest_composite": scores[0].composite_score if scores else None,
        "trend": [{"period": s.period, "score": s.composite_score} for s in reversed(scores[-6:])],
    }


def add_vendor_score_record(db: Session, vendor_id: str, payload, current_user: User) -> dict:
    vendor = db.query(ALMVendor).filter(ALMVendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(404)
    for field in ["sla_score", "quality_score", "support_score", "price_score", "innovation_score", "compliance_score"]:
        v = getattr(payload, field, None)
        if v is not None and not (0 <= v <= 10):
            raise HTTPException(400, f"{field} must be 0-10")
    composite = score_composite(payload)
    score = VendorScore(
        vendor_id=vendor_id,
        evaluator_id=current_user.id,
        composite_score=composite,
        **payload.model_dump(),
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return {"id": score.id, "composite_score": composite}


def vendor_scorecard_ranking_payload(db: Session) -> list:
    subq = (
        db.query(VendorScore.vendor_id, func.max(VendorScore.evaluated_at).label("last_eval"))
        .group_by(VendorScore.vendor_id)
        .subquery()
    )
    latest = (
        db.query(VendorScore, ALMVendor)
        .join(ALMVendor, VendorScore.vendor_id == ALMVendor.id)
        .join(subq, (VendorScore.vendor_id == subq.c.vendor_id) & (VendorScore.evaluated_at == subq.c.last_eval))
        .all()
    )
    result = [{
        "vendor_id": vs.vendor_id,
        "vendor_name": v.name,
        "category": v.category.value if v.category else None,
        "period": vs.period,
        "composite_score": vs.composite_score,
        "rating": ("Excelente" if (vs.composite_score or 0) >= 8 else
                   "Bueno" if (vs.composite_score or 0) >= 6 else
                   "Regular" if (vs.composite_score or 0) >= 4 else "Deficiente"),
        "incidents_count": vs.incidents_count,
    } for vs, v in latest]
    result.sort(key=lambda x: -(x["composite_score"] or 0))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# WHAT-IF SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_project_payload(db: Session, project_id: str, payload) -> dict:

    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).all()
    if not tasks:
        raise HTTPException(404, "No open tasks found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)

    defer_ids = set(payload.defer_task_ids or [])
    cut_ids = set(payload.cut_task_ids or [])

    remaining_tasks = [t for t in tasks if t.id not in cut_ids and t.id not in defer_ids]
    total_hours = sum((t.estimated_hours or 0) for t in remaining_tasks)
    overdue = [t for t in remaining_tasks if t.due_date and t.due_date < date.today()]

    due_dates = [t.due_date for t in remaining_tasks if t.due_date]
    base_end = max(due_dates) if due_dates else date.today()

    sim_end = base_end
    notes = []

    if payload.delay_days:
        sim_end = sim_end + timedelta(days=payload.delay_days)
        notes.append(f"All remaining tasks delayed by {payload.delay_days} days")

    effective_compression = 1.0
    if payload.compress_pct and payload.compress_pct > 0:
        effective_compression = 1 - (payload.compress_pct / 100)
        remaining_days = (sim_end - date.today()).days
        new_days = int(remaining_days * effective_compression)
        sim_end = date.today() + timedelta(days=new_days)
        notes.append(
            f"Team expansion at {payload.compress_pct}% → duration compressed "
            f"from {remaining_days}d to {new_days}d"
        )

    if payload.add_resources:
        extra_hours_week = sum(r.get("hours_per_week", 40) for r in payload.add_resources)
        remaining_hours = total_hours * effective_compression
        saved_weeks = (remaining_hours * 0.7) / max(extra_hours_week, 1)
        saved_days = int(saved_weeks * 5)
        sim_end = sim_end - timedelta(days=saved_days)
        notes.append(f"{len(payload.add_resources)} extra resource(s) added → ~{saved_days} days saved")

    deferred_detail = [{
        "id": t.id, "code": t.code, "title": t.title,
        "estimated_hours": t.estimated_hours,
    } for t in tasks if t.id in defer_ids]

    cut_detail = [{
        "id": t.id, "code": t.code, "title": t.title,
        "estimated_hours": t.estimated_hours,
    } for t in tasks if t.id in cut_ids]

    avg_rate = 80.0
    cost_delta = -sum((t.estimated_hours or 0) * avg_rate for t in tasks if t.id in cut_ids)
    if payload.add_resources:
        cost_delta += sum(
            r.get("hours_per_week", 40) * r.get("rate_per_hour", avg_rate)
            for r in payload.add_resources
        ) * ((sim_end - date.today()).days / 5)

    at_risk = [{
        "id": t.id, "code": t.code, "title": t.title,
        "due_date": str(t.due_date),
    } for t in overdue if t.id not in cut_ids and t.id not in defer_ids]

    return {
        "project_id": project_id,
        "project_name": project.name,
        "simulation": {
            "base_end_date": str(base_end),
            "simulated_end_date": str(sim_end),
            "days_delta": (sim_end - base_end).days,
            "total_remaining_hours": round(total_hours, 1),
            "effective_remaining_hours": round(total_hours * effective_compression, 1),
            "cost_delta_eur": round(cost_delta, 2),
            "deferred_tasks": len(deferred_detail),
            "cut_tasks": len(cut_detail),
            "at_risk_tasks": len(at_risk),
        },
        "notes": notes,
        "deferred": deferred_detail,
        "cut": cut_detail,
        "at_risk": at_risk,
    }
