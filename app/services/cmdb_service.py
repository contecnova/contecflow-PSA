"""
CMDB Service — Business logic extracted from cmdb.py router.
Covers: wiki tags, internal comments, CMDB CRUD + changelog,
agent dashboard, wiki export, kanban, sprint planning, SLA calendars.
"""
from datetime import date, timedelta
from typing import Optional, List
import json
import logging

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from fastapi import HTTPException

from app.models.project import Project
from app.models.task import Task
from app.models.epics import WikiSpace, WikiPage
from app.models.cmdb import (
    WikiTag, WikiPageTag, TicketInternalComment,
    CMDBCategory, CMDBItem, CMDBRelation, CMDBChangelog,
    AgentMetricSnapshot, WikiExportJob,
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

def list_internal_comments(ticket_id: str, db: Session) -> list:
    cs = db.query(TicketInternalComment).filter(
        TicketInternalComment.ticket_id == ticket_id
    ).order_by(TicketInternalComment.created_at).all()
    return [{"id": c.id, "content": c.content, "is_internal": c.is_internal,
             "created_by": c.created_by,
             "created_at": c.created_at.isoformat() if c.created_at else None,
             "updated_at": c.updated_at.isoformat() if c.updated_at else None}
            for c in cs]


def add_internal_comment(ticket_id: str, content: str, user_id: str, db: Session) -> dict:
    c = TicketInternalComment(ticket_id=ticket_id, content=content,
                              is_internal=True, created_by=user_id)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content, "is_internal": True}


def update_internal_comment(ticket_id: str, comment_id: str, content: str, user_id: str, db: Session) -> dict:
    c = db.query(TicketInternalComment).filter(
        TicketInternalComment.id == comment_id,
        TicketInternalComment.ticket_id == ticket_id,
        TicketInternalComment.created_by == user_id).first()
    if not c: _404("Comentario")
    c.content = content; db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content}


def delete_internal_comment(ticket_id: str, comment_id: str, user_id: str, db: Session) -> dict:
    c = db.query(TicketInternalComment).filter(
        TicketInternalComment.id == comment_id,
        TicketInternalComment.ticket_id == ticket_id,
        TicketInternalComment.created_by == user_id).first()
    if not c: _404("Comentario")
    db.delete(c); db.commit()
    return {"deleted": True}


# ──────────────────────────────────────────────────────────────────────────────
# CMDB
# ──────────────────────────────────────────────────────────────────────────────

def serialize_cmdb_item(i: CMDBItem) -> dict:
    return {
        "id": i.id, "name": i.name, "ci_type": i.ci_type,
        "category_id": i.category_id,
        "category_name": i.category.name if i.category else None,
        "status": i.status, "environment": i.environment,
        "description": i.description,
        "ip_address": i.ip_address, "hostname": i.hostname, "version": i.version,
        "attributes": json.loads(i.attributes) if i.attributes else {},
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


def merge_ci_attrs(payload) -> str:
    attrs = dict(getattr(payload, 'attributes', None) or {})
    for f in _CI_SPECIFIC:
        v = getattr(payload, f, None)
        if v is not None:
            attrs[f] = str(v)
    return json.dumps(attrs)


def list_cmdb_categories(db: Session) -> list:
    cats = db.query(CMDBCategory).all()
    counts = dict(db.query(CMDBItem.category_id, func.count(CMDBItem.id))
                   .filter(CMDBItem.category_id.in_([c.id for c in cats]), CMDBItem.is_active == True)
                   .group_by(CMDBItem.category_id).all())
    return [{"id": c.id, "name": c.name, "icon": c.icon, "color": c.color,
             "item_count": counts.get(c.id, 0)} for c in cats]


def create_cmdb_category(name: str, icon: Optional[str], color: str, db: Session) -> dict:
    cat = CMDBCategory(name=name, icon=icon, color=color)
    db.add(cat); db.commit(); db.refresh(cat)
    return {"id": cat.id, "name": cat.name}


def list_cmdb_items(
    ci_type: Optional[str], status: Optional[str],
    category_id: Optional[str], q: Optional[str],
    organization_id: Optional[str], db: Session,
) -> list:
    query = db.query(CMDBItem).options(joinedload(CMDBItem.category))
    if organization_id:
        # Auditoria 2026-08 (hallazgo 22). Esto era un `hasattr` **correcto**
        # sobre una columna que **no existe**: `CMDBItem` no tiene `project_id`.
        # Asi que se tomaba siempre la rama `else`, que registra un aviso y
        # **se salta el filtro de organizacion por completo**. Un agujero de
        # aislamiento escondido detras de una defensa bien escrita — la peor
        # combinacion, porque el aviso en el log parece que informa de una
        # limitacion temporal y lo que describe es la ausencia del filtro.
        #
        # `CMDBItem` **si** tiene `organization_id`, que es el filtro directo y
        # no necesita pasar por los proyectos de la organizacion.
        query = query.filter(CMDBItem.organization_id == organization_id)
    if ci_type:     query = query.filter(CMDBItem.ci_type == ci_type)
    if status:      query = query.filter(CMDBItem.status == status)
    if category_id: query = query.filter(CMDBItem.category_id == category_id)
    if q:           query = query.filter(or_(
        CMDBItem.name.ilike(f"%{q}%"),
        CMDBItem.hostname.ilike(f"%{q}%"),
        CMDBItem.ip_address.ilike(f"%{q}%")))
    query = query.filter(CMDBItem.is_active == True)
    return [serialize_cmdb_item(i) for i in query.order_by(CMDBItem.name).all()]


def create_cmdb_item(payload, user_id: str, db: Session) -> dict:
    i = CMDBItem(
        name=payload.name, ci_type=payload.ci_type, category_id=payload.category_id,
        status=payload.status, environment=payload.environment,
        description=payload.description, ip_address=payload.ip_address,
        hostname=payload.hostname, version=payload.version,
        owner_id=user_id, attributes=merge_ci_attrs(payload),
    )
    db.add(i); db.commit(); db.refresh(i)
    return serialize_cmdb_item(i)


def update_cmdb_item(item_id: str, payload, user_id: str, db: Session) -> dict:
    i = db.query(CMDBItem).filter(CMDBItem.id == item_id, CMDBItem.is_active == True).first()
    if not i: _404("Activo")
    update_data = payload.model_dump(exclude_unset=True)
    existing_attrs = json.loads(i.attributes or '{}')
    for f in _CI_SPECIFIC:
        if f in update_data:
            val = update_data.pop(f)
            if val is not None:
                existing_attrs[f] = str(val)
    if 'attributes' in update_data:
        existing_attrs.update(update_data.pop('attributes') or {})
    update_data['attributes'] = json.dumps(existing_attrs)
    changed_fields = [k for k in update_data if k != 'attributes']
    summary = f"Campos actualizados: {', '.join(changed_fields)}" if changed_fields else "Atributos actualizados"
    for k, v in update_data.items():
        setattr(i, k, v)
    _log_cmdb_change(db, i.id, user_id, "updated", summary=summary)
    db.commit(); db.refresh(i)
    return serialize_cmdb_item(i)


def delete_cmdb_item(item_id: str, db: Session) -> dict:
    i = db.query(CMDBItem).filter(CMDBItem.id == item_id, CMDBItem.is_active == True).first()
    if not i: _404("Activo")
    outgoing = db.query(func.count(CMDBRelation.id)).filter(
        CMDBRelation.from_item_id == item_id,
        CMDBRelation.is_active == True,
    ).scalar() or 0
    incoming = db.query(func.count(CMDBRelation.id)).filter(
        CMDBRelation.to_item_id == item_id,
        CMDBRelation.is_active == True,
    ).scalar() or 0
    if outgoing > 0 or incoming > 0:
        raise HTTPException(400, f"No se puede eliminar: relaciones activas salientes={outgoing}, entrantes={incoming}")
    i.is_active = False
    i.status = "decommissioned"
    _log_cmdb_change(db, i.id, None, "deleted", summary="Activo eliminado")
    db.commit()
    return {"ok": True, "message": "Activo eliminado correctamente"}


def _log_cmdb_change(
    db: Session, item_id: str, user_id: str, action: str,
    field: str = None, old_val=None, new_val=None, summary: str = None,
):
    import uuid as _uuid
    entry = CMDBChangelog(
        id=str(_uuid.uuid4()),
        item_id=item_id, user_id=user_id, action=action,
        field=field,
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None,
        summary=summary,
    )
    db.add(entry)


def get_cmdb_changelog(item_id: str, limit: int, db: Session) -> list:
    item = db.query(CMDBItem).filter(CMDBItem.id == item_id, CMDBItem.is_active == True).first()
    if not item: _404("Activo")
    entries = (
        db.query(CMDBChangelog)
        .filter(CMDBChangelog.item_id == item_id)
        .order_by(CMDBChangelog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id, "action": e.action, "field": e.field,
            "old_value": e.old_value, "new_value": e.new_value,
            "summary": e.summary,
            "user_name": e.user.full_name if e.user else "Sistema",
            "created_at": str(e.created_at)[:19] if e.created_at else None,
        }
        for e in entries
    ]


def get_item_relations(item_id: str, db: Session) -> dict:
    item = db.query(CMDBItem).filter(CMDBItem.id == item_id, CMDBItem.is_active == True).first()
    if not item:
        _404("Activo")
    rels_from = db.query(CMDBRelation).options(
        joinedload(CMDBRelation.to_item)).filter(
        CMDBRelation.from_item_id == item_id,
        CMDBRelation.is_active == True,
    ).all()
    rels_to = db.query(CMDBRelation).options(
        joinedload(CMDBRelation.from_item)).filter(
        CMDBRelation.to_item_id == item_id,
        CMDBRelation.is_active == True,
    ).all()
    return {
        "outgoing": [{"id": r.id, "rel_type": r.rel_type,
                      "to_item": serialize_cmdb_item(r.to_item)} for r in rels_from],
        "incoming": [{"id": r.id, "rel_type": r.rel_type,
                      "from_item": serialize_cmdb_item(r.from_item)} for r in rels_to],
    }


def create_cmdb_relation(from_item_id: str, to_item_id: str, rel_type: str, db: Session) -> dict:
    if from_item_id == to_item_id:
        raise HTTPException(400, "Un activo no puede relacionarse consigo mismo")
    for iid in [from_item_id, to_item_id]:
        if not db.query(CMDBItem).filter(CMDBItem.id == iid, CMDBItem.is_active == True).first():
            raise HTTPException(404, f"Activo {iid} no encontrado")
    r = CMDBRelation(from_item_id=from_item_id, to_item_id=to_item_id, rel_type=rel_type)
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "rel_type": r.rel_type}


def delete_cmdb_relation(relation_id: str, db: Session) -> dict:
    r = db.query(CMDBRelation).filter(CMDBRelation.id == relation_id, CMDBRelation.is_active == True).first()
    if not r: _404("Relación")
    r.is_active = False
    db.commit()
    return {"ok": True, "message": "Relacion eliminada correctamente"}


# ──────────────────────────────────────────────────────────────────────────────
# AGENT DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

def get_agent_dashboard(agent_id: str, days: int, db: Session) -> dict:
    since = (timeutil.today() - timedelta(days=days)).isoformat()
    snaps = db.query(AgentMetricSnapshot).filter(
        AgentMetricSnapshot.agent_id == agent_id,
        AgentMetricSnapshot.snap_date >= since
    ).order_by(AgentMetricSnapshot.snap_date).all()

    total_resolved = sum(s.resolved_today for s in snaps)
    avg_resolution = sum(s.avg_resolution_h for s in snaps) / len(snaps) if snaps else 0
    sla_ok   = sum(s.sla_compliant for s in snaps)
    sla_fail = sum(s.sla_breached for s in snaps)
    sla_rate = round(sla_ok / (sla_ok + sla_fail) * 100) if (sla_ok + sla_fail) > 0 else 0
    csat_vals = [s.csat_score for s in snaps if s.csat_score is not None]
    avg_csat  = round(sum(csat_vals) / len(csat_vals), 2) if csat_vals else None
    latest = snaps[-1] if snaps else None

    return {
        "agent_id": agent_id,
        "period_days": days,
        "current": {"open_tickets": latest.open_tickets if latest else 0},
        "kpis": {
            "total_resolved": total_resolved,
            "avg_resolution_hours": round(avg_resolution, 1),
            "sla_compliance_pct": sla_rate,
            "avg_csat": avg_csat,
        },
        "trend": [
            {"date": s.snap_date, "resolved": s.resolved_today,
             "sla_ok": s.sla_compliant, "sla_fail": s.sla_breached,
             "csat": s.csat_score}
            for s in snaps
        ],
    }


def create_agent_snapshot(agent_id: str, db: Session) -> dict:
    today_str = timeutil.today().isoformat()
    open_tickets = 0
    try:
        from app.models.service_desk import Ticket
        open_tickets = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == agent_id,
            Ticket.status.notin_(["resolved", "closed"])
        ).count()
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("create_agent_snapshot: fallo best-effort ignorado", exc_info=True)

    db.query(AgentMetricSnapshot).filter(
        AgentMetricSnapshot.agent_id == agent_id,
        AgentMetricSnapshot.snap_date == today_str
    ).delete()
    snap = AgentMetricSnapshot(
        agent_id=agent_id, snap_date=today_str,
        open_tickets=open_tickets, resolved_today=0,
        avg_resolution_h=0.0, sla_compliant=0, sla_breached=0,
    )
    db.add(snap); db.commit()
    return {"snapshot_created": True, "date": today_str, "open_tickets": open_tickets}


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
