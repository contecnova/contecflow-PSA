"""Clarive v21 — Wiki tags, comentarios internos, CMDB, dashboard agente,
   wiki PDF, Kanban avanzado, sprint planning IA, SLA avanzado."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, timedelta
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm, require_any_manager
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.epics import WikiSpace, WikiPage
from app.models.cmdb import (
    WikiTag, WikiPageTag, TicketInternalComment,
    CMDBCategory, CMDBItem, CMDBRelation,
    CMDBChangelog,
    AgentMetricSnapshot, WikiExportJob,
    KanbanConfig, KanbanColumn,
    SprintPlan, SprintPlanTask,
    SLACalendar, V21SLAHoliday,
)
from app.core.config import settings

router = APIRouter()
# Sub-router for service-desk ticket endpoints (mounted under /sd in router.py)
sd_router = APIRouter()

def _404(m): raise HTTPException(404, f"{m} no encontrado")


# ═══════════════════════════════════════════════════════════════
# 1. ETIQUETAS WIKI
# ═══════════════════════════════════════════════════════════════

class WikiTagIn(BaseModel):
    name: str
    color: str = "#7a8aaa"

@router.get("/wiki-tags/{space_id}")
def list_tags(space_id: str, db: Session = Depends(get_db),
              cu: User = Depends(get_current_user)):
    tags = db.query(WikiTag).filter(WikiTag.space_id == space_id).all()
    counts = dict(db.query(WikiPageTag.tag_id, func.count(WikiPageTag.id))
                   .filter(WikiPageTag.tag_id.in_([t.id for t in tags]))
                   .group_by(WikiPageTag.tag_id).all())
    return [{"id": t.id, "name": t.name, "color": t.color,
             "page_count": counts.get(t.id, 0)} for t in tags]

@router.post("/wiki-tags/{space_id}")
def create_tag(space_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    if not db.query(WikiSpace).filter(WikiSpace.id == space_id).first():
        _404("Espacio")
    t = WikiTag(space_id=space_id, name=p.name, color=p.color, created_by=cu.id)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name, "color": t.color}

@router.patch("/wiki-tags/{tag_id}")
def update_tag(tag_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    t = db.query(WikiTag).filter(WikiTag.id == tag_id).first()
    if not t: _404("Etiqueta")
    t.name = p.name; t.color = p.color; db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name, "color": t.color}

@router.delete("/wiki-tags/{tag_id}")
def delete_tag(tag_id: str, db: Session = Depends(get_db),
               cu: User = Depends(require_admin_or_pm)):
    t = db.query(WikiTag).filter(WikiTag.id == tag_id).first()
    if not t: _404("Etiqueta")
    db.delete(t); db.commit()
    return {"deleted": True}

@router.post("/wiki-pages/{page_id}/tags/{tag_id}")
def add_page_tag(page_id: str, tag_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    if not db.query(WikiPageTag).filter(
            WikiPageTag.page_id == page_id, WikiPageTag.tag_id == tag_id).first():
        db.add(WikiPageTag(page_id=page_id, tag_id=tag_id))
        db.commit()
    return {"linked": True}

@router.delete("/wiki-pages/{page_id}/tags/{tag_id}")
def remove_page_tag(page_id: str, tag_id: str,
                    db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    pt = db.query(WikiPageTag).filter(
        WikiPageTag.page_id == page_id, WikiPageTag.tag_id == tag_id).first()
    if pt: db.delete(pt); db.commit()
    return {"unlinked": True}

@router.get("/wiki-pages/{page_id}/tags")
def get_page_tags(page_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    pts = db.query(WikiPageTag).options(joinedload(WikiPageTag.tag)).filter(
        WikiPageTag.page_id == page_id).all()
    return [{"id": pt.tag.id, "name": pt.tag.name, "color": pt.tag.color}
            for pt in pts if pt.tag]

@router.get("/wiki-tags/{space_id}/pages")
def pages_by_tag(space_id: str, tag_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    pts = db.query(WikiPageTag).filter(WikiPageTag.tag_id == tag_id).all()
    page_ids = [p.page_id for p in pts]
    pages = db.query(WikiPage).filter(
        WikiPage.id.in_(page_ids), WikiPage.space_id == space_id).all()
    return [{"id": p.id, "title": p.title, "slug": p.slug} for p in pages]


# ═══════════════════════════════════════════════════════════════
# 2. COMENTARIOS INTERNOS EN TICKETS
# ═══════════════════════════════════════════════════════════════

class InternalCommentIn(BaseModel):
    content: str

@sd_router.get("/tickets/{ticket_id}/internal-comments")
def list_internal_comments(ticket_id: str, db: Session = Depends(get_db),
                           cu: User = Depends(require_any_manager)):
    cs = db.query(TicketInternalComment).filter(
        TicketInternalComment.ticket_id == ticket_id
    ).order_by(TicketInternalComment.created_at).all()
    return [{"id": c.id, "content": c.content, "is_internal": c.is_internal,
             "created_by": c.created_by,
             "created_at": c.created_at.isoformat() if c.created_at else None,
             "updated_at": c.updated_at.isoformat() if c.updated_at else None}
            for c in cs]

@sd_router.post("/tickets/{ticket_id}/internal-comments")
def add_internal_comment(ticket_id: str, p: InternalCommentIn,
                         db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = TicketInternalComment(ticket_id=ticket_id, content=p.content,
                              is_internal=True, created_by=cu.id)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content, "is_internal": True}

@sd_router.patch("/tickets/{ticket_id}/internal-comments/{comment_id}")
def update_internal_comment(ticket_id: str, comment_id: str, p: InternalCommentIn,
                             db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = db.query(TicketInternalComment).filter(
        TicketInternalComment.id == comment_id,
        TicketInternalComment.ticket_id == ticket_id,
        TicketInternalComment.created_by == cu.id).first()
    if not c: _404("Comentario")
    c.content = p.content; db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content}

@sd_router.delete("/tickets/{ticket_id}/internal-comments/{comment_id}")
def delete_internal_comment(ticket_id: str, comment_id: str,
                             db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = db.query(TicketInternalComment).filter(
        TicketInternalComment.id == comment_id,
        TicketInternalComment.ticket_id == ticket_id,
        TicketInternalComment.created_by == cu.id).first()
    if not c: _404("Comentario")
    db.delete(c); db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# 3. CMDB
# ═══════════════════════════════════════════════════════════════

class CMDBCategoryIn(BaseModel):
    name: str
    icon: Optional[str] = None
    color: str = "#7a8aaa"

class CMDBItemIn(BaseModel):
    name: str
    ci_type: str
    category_id: Optional[str] = None
    status: str = "active"
    environment: str = "production"
    description: Optional[str] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    version: Optional[str] = None
    attributes: Optional[dict] = None
    # Campos específicos por tipo (se fusionan en attributes)
    os: Optional[str] = None
    cpu_cores: Optional[str] = None
    ram_gb: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    tech_stack: Optional[str] = None
    repo_url: Optional[str] = None
    owner_team: Optional[str] = None
    sla_tier: Optional[str] = None
    db_engine: Optional[str] = None
    port: Optional[str] = None
    size_gb: Optional[str] = None
    backup_schedule: Optional[str] = None
    vendor: Optional[str] = None
    cluster: Optional[str] = None
    namespace: Optional[str] = None
    replicas: Optional[str] = None
    cloud_provider: Optional[str] = None
    region: Optional[str] = None
    resource_id: Optional[str] = None
    instance_type: Optional[str] = None
    monthly_cost: Optional[str] = None
    image: Optional[str] = None
    assigned_to: Optional[str] = None
    warranty_date: Optional[str] = None
    protocol: Optional[str] = None
    capacity_tb: Optional[str] = None
    used_tb: Optional[str] = None
    model: Optional[str] = None
    dependencies: Optional[str] = None

class CMDBItemUpdate(BaseModel):
    name: Optional[str] = None
    ci_type: Optional[str] = None
    category_id: Optional[str] = None
    status: Optional[str] = None
    environment: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    version: Optional[str] = None
    os: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_gb: Optional[int] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    tech_stack: Optional[str] = None
    repo_url: Optional[str] = None
    owner_team: Optional[str] = None
    sla_tier: Optional[str] = None
    db_engine: Optional[str] = None
    port: Optional[int] = None
    size_gb: Optional[float] = None
    backup_schedule: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    cloud_provider: Optional[str] = None
    region: Optional[str] = None
    resource_id: Optional[str] = None
    instance_type: Optional[str] = None
    monthly_cost: Optional[float] = None
    assigned_to: Optional[str] = None
    warranty_date: Optional[str] = None
    capacity_tb: Optional[float] = None
    used_tb: Optional[float] = None
    protocol: Optional[str] = None
    image: Optional[str] = None
    cluster: Optional[str] = None
    namespace: Optional[str] = None
    replicas: Optional[int] = None
    dependencies: Optional[str] = None
    attributes: Optional[dict] = None

class CMDBRelationIn(BaseModel):
    from_item_id: str
    to_item_id: str
    rel_type: str = "depends_on"

def _ser_item(i: CMDBItem) -> dict:
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


_CI_SPECIFIC = ['os', 'cpu_cores', 'ram_gb', 'serial_number', 'location', 'url', 'tech_stack', 'repo_url', 'owner_team', 'sla_tier', 'db_engine', 'port', 'size_gb', 'backup_schedule', 'vendor', 'cluster', 'namespace', 'replicas', 'cloud_provider', 'region', 'resource_id', 'instance_type', 'monthly_cost', 'image', 'assigned_to', 'warranty_date', 'protocol', 'capacity_tb', 'used_tb', 'model', 'dependencies']

def _merge_attrs(p) -> str:
    attrs = dict(getattr(p, 'attributes', None) or {})
    for f in _CI_SPECIFIC:
        v = getattr(p, f, None)
        if v is not None:
            attrs[f] = str(v)
    return json.dumps(attrs)

@router.get("/cmdb/categories")
def list_cmdb_categories(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    cats = db.query(CMDBCategory).all()
    counts = dict(db.query(CMDBItem.category_id, func.count(CMDBItem.id))
                   .filter(CMDBItem.category_id.in_([c.id for c in cats]))
                   .group_by(CMDBItem.category_id).all())
    return [{"id": c.id, "name": c.name, "icon": c.icon, "color": c.color,
             "item_count": counts.get(c.id, 0)} for c in cats]

@router.post("/cmdb/categories")
def create_cmdb_category(p: CMDBCategoryIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    cat = CMDBCategory(name=p.name, icon=p.icon, color=p.color)
    db.add(cat); db.commit(); db.refresh(cat)
    return {"id": cat.id, "name": cat.name}

@router.get("/cmdb/items")
def list_cmdb_items(ci_type: Optional[str] = None,
                    status: Optional[str] = None,
                    category_id: Optional[str] = None,
                    q: Optional[str] = None,
                    db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    query = db.query(CMDBItem).options(joinedload(CMDBItem.category))
    if cu.organization_id:
        # CMDBItem has no direct organization_id; scope via project when linked.
        # Items with no project_id are excluded for non-admin users in multi-tenant
        # deployments to avoid cross-tenant data exposure.
        org_project_ids = [r.id for r in db.query(Project.id).filter(
            Project.organization_id == cu.organization_id
        ).all()]
        query = query.filter(CMDBItem.project_id.in_(org_project_ids))
    if ci_type:    query = query.filter(CMDBItem.ci_type == ci_type)
    if status:     query = query.filter(CMDBItem.status == status)
    if category_id: query = query.filter(CMDBItem.category_id == category_id)
    if q:          query = query.filter(or_(
        CMDBItem.name.ilike(f"%{q}%"),
        CMDBItem.hostname.ilike(f"%{q}%"),
        CMDBItem.ip_address.ilike(f"%{q}%")))
    return [_ser_item(i) for i in query.order_by(CMDBItem.name).all()]

@router.post("/cmdb/items")
def create_cmdb_item(p: CMDBItemIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    i = CMDBItem(name=p.name, ci_type=p.ci_type, category_id=p.category_id,
                 status=p.status, environment=p.environment,
                 description=p.description, ip_address=p.ip_address,
                 hostname=p.hostname, version=p.version, owner_id=cu.id,
                 attributes=_merge_attrs(p))
    db.add(i); db.commit(); db.refresh(i)
    return _ser_item(i)

@router.patch("/cmdb/items/{item_id}")
def update_cmdb_item(item_id: str, p: CMDBItemUpdate,
                     db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    i = db.query(CMDBItem).filter(CMDBItem.id == item_id).first()
    if not i: _404("Activo")
    update_data = p.model_dump(exclude_unset=True)
    # Fusionar campos específicos en attributes
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
    _log_cmdb_change(db, i.id, cu.id, "updated", summary=summary)
    db.commit(); db.refresh(i)
    return _ser_item(i)

@router.delete("/cmdb/items/{item_id}")
def delete_cmdb_item(item_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    i = db.query(CMDBItem).filter(CMDBItem.id == item_id).first()
    if not i: _404("Activo")
    db.delete(i); db.commit()
    return {"deleted": True}

# ── CMDB Changelog ────────────────────────────────────────────────────────────
def _log_cmdb_change(db, item_id: str, user_id: str, action: str,
                     field: str = None, old_val=None, new_val=None, summary: str = None):
    """Helper: registra un cambio en el historial CMDB."""
    import uuid as _uuid
    entry = CMDBChangelog(
        id=str(_uuid.uuid4()),
        item_id=item_id,
        user_id=user_id,
        action=action,
        field=field,
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None,
        summary=summary,
    )
    db.add(entry)


@router.get("/cmdb/items/{item_id}/changelog", summary="Historial de cambios del activo")
def get_cmdb_changelog(
    item_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    item = db.query(CMDBItem).filter(CMDBItem.id == item_id).first()
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
            "id":         e.id,
            "action":     e.action,
            "field":      e.field,
            "old_value":  e.old_value,
            "new_value":  e.new_value,
            "summary":    e.summary,
            "user_name":  e.user.full_name if e.user else "Sistema",
            "created_at": str(e.created_at)[:19] if e.created_at else None,
        }
        for e in entries
    ]


@router.get("/cmdb/items/{item_id}/relations")
def item_relations(item_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    rels_from = db.query(CMDBRelation).options(
        joinedload(CMDBRelation.to_item)).filter(
        CMDBRelation.from_item_id == item_id).all()
    rels_to = db.query(CMDBRelation).options(
        joinedload(CMDBRelation.from_item)).filter(
        CMDBRelation.to_item_id == item_id).all()
    return {
        "outgoing": [{"id": r.id, "rel_type": r.rel_type,
                      "to_item": _ser_item(r.to_item)} for r in rels_from],
        "incoming": [{"id": r.id, "rel_type": r.rel_type,
                      "from_item": _ser_item(r.from_item)} for r in rels_to],
    }

@router.post("/cmdb/relations")
def create_cmdb_relation(p: CMDBRelationIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    if p.from_item_id == p.to_item_id:
        raise HTTPException(400, "Un activo no puede relacionarse consigo mismo")
    for iid in [p.from_item_id, p.to_item_id]:
        if not db.query(CMDBItem).filter(CMDBItem.id == iid).first():
            raise HTTPException(404, f"Activo {iid} no encontrado")
    r = CMDBRelation(from_item_id=p.from_item_id,
                     to_item_id=p.to_item_id, rel_type=p.rel_type)
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "rel_type": r.rel_type}

@router.delete("/cmdb/relations/{relation_id}")
def delete_cmdb_relation(relation_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    r = db.query(CMDBRelation).filter(CMDBRelation.id == relation_id).first()
    if not r: _404("Relación")
    db.delete(r); db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# 4. DASHBOARD DE AGENTE
# ═══════════════════════════════════════════════════════════════

@router.get("/agent-dashboard/{agent_id}")
def agent_dashboard(agent_id: str, days: int = 30,
                    db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    since = (date.today() - timedelta(days=days)).isoformat()
    snaps = db.query(AgentMetricSnapshot).filter(
        AgentMetricSnapshot.agent_id == agent_id,
        AgentMetricSnapshot.snap_date >= since
    ).order_by(AgentMetricSnapshot.snap_date).all()

    total_resolved = sum(s.resolved_today for s in snaps)
    avg_resolution = sum(s.avg_resolution_h for s in snaps) / len(snaps) if snaps else 0
    sla_ok    = sum(s.sla_compliant for s in snaps)
    sla_fail  = sum(s.sla_breached for s in snaps)
    sla_rate  = round(sla_ok / (sla_ok + sla_fail) * 100) if (sla_ok + sla_fail) > 0 else 0
    csat_vals = [s.csat_score for s in snaps if s.csat_score is not None]
    avg_csat  = round(sum(csat_vals) / len(csat_vals), 2) if csat_vals else None

    latest = snaps[-1] if snaps else None

    return {
        "agent_id": agent_id,
        "period_days": days,
        "current": {
            "open_tickets": latest.open_tickets if latest else 0,
        },
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

@router.post("/agent-dashboard/{agent_id}/snapshot")
def create_agent_snapshot(agent_id: str, db: Session = Depends(get_db),
                          cu: User = Depends(require_admin_or_pm)):
    """Genera snapshot de métricas del agente para hoy."""
    try:
        from app.models.service_desk import Ticket
        today_str = date.today().isoformat()
        open_tickets = db.query(Ticket).filter(
            Ticket.assigned_agent_id == agent_id,
            Ticket.status.notin_(["resolved", "closed"])
        ).count()
    except Exception:
        open_tickets = 0

    today_str = date.today().isoformat()
    db.query(AgentMetricSnapshot).filter(
        AgentMetricSnapshot.agent_id == agent_id,
        AgentMetricSnapshot.snap_date == today_str
    ).delete()
    snap = AgentMetricSnapshot(
        agent_id=agent_id, snap_date=today_str,
        open_tickets=open_tickets, resolved_today=0,
        avg_resolution_h=0.0, sla_compliant=0, sla_breached=0)
    db.add(snap); db.commit()
    return {"snapshot_created": True, "date": today_str, "open_tickets": open_tickets}


# ═══════════════════════════════════════════════════════════════
# 5. WIKI PDF EXPORT
# ═══════════════════════════════════════════════════════════════

@router.post("/wiki-export/{page_id}")
def export_wiki_page(page_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(get_current_user)):
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página wiki")
    job = WikiExportJob(page_id=page_id, status="pending",
                        file_path=None,
                        created_by=cu.id)
    db.add(job); db.commit(); db.refresh(job)
    return {
        "job_id": job.id,
        "status": "pending",
        "page_title": page.title,
        "message": "Trabajo de exportación creado. Procesando en segundo plano."
    }

@router.get("/wiki-export/jobs")
def list_export_jobs(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    jobs = db.query(WikiExportJob).filter(
        WikiExportJob.created_by == cu.id
    ).order_by(WikiExportJob.created_at.desc()).limit(20).all()
    return [{"id": j.id, "page_id": j.page_id, "status": j.status,
             "file_path": j.file_path,
             "created_at": j.created_at.isoformat() if j.created_at else None}
            for j in jobs]


# ═══════════════════════════════════════════════════════════════
# 6. KANBAN AVANZADO
# ═══════════════════════════════════════════════════════════════

class KanbanConfigIn(BaseModel):
    swimlane_by: str = "none"
    show_subtasks: bool = True
    card_fields: Optional[List[str]] = ["priority", "assignee", "story_points"]

class KanbanColumnIn(BaseModel):
    status: str
    label: Optional[str] = None
    wip_limit: Optional[int] = None
    color: Optional[str] = None
    sort_order: int = 0

@router.get("/kanban/{project_id}")
def get_kanban_config(project_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(get_current_user)):
    cfg = db.query(KanbanConfig).options(
        joinedload(KanbanConfig.columns)
    ).filter(KanbanConfig.project_id == project_id).first()
    if not cfg:
        return {"project_id": project_id, "swimlane_by": "none",
                "show_subtasks": True, "card_fields": ["priority", "assignee"],
                "columns": [], "configured": False}
    return {
        "id": cfg.id, "project_id": cfg.project_id,
        "swimlane_by": cfg.swimlane_by,
        "show_subtasks": cfg.show_subtasks,
        "card_fields": json.loads(cfg.card_fields) if cfg.card_fields else [],
        "configured": True,
        "columns": [
            {"id": col.id, "status": col.status, "label": col.label,
             "wip_limit": col.wip_limit, "color": col.color,
             "sort_order": col.sort_order}
            for col in (cfg.columns or [])
        ],
    }

@router.post("/kanban/{project_id}")
def upsert_kanban_config(project_id: str, p: KanbanConfigIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    if not db.query(Project).filter(Project.id == project_id).first():
        _404("Proyecto")
    cfg = db.query(KanbanConfig).filter(KanbanConfig.project_id == project_id).first()
    if cfg:
        cfg.swimlane_by   = p.swimlane_by
        cfg.show_subtasks = p.show_subtasks
        cfg.card_fields   = json.dumps(p.card_fields or [])
    else:
        cfg = KanbanConfig(project_id=project_id,
                           swimlane_by=p.swimlane_by,
                           show_subtasks=p.show_subtasks,
                           card_fields=json.dumps(p.card_fields or []))
        db.add(cfg)
    db.commit(); db.refresh(cfg)
    return {"id": cfg.id, "project_id": project_id, "swimlane_by": cfg.swimlane_by}

@router.post("/kanban/{project_id}/columns")
def add_kanban_column(project_id: str, p: KanbanColumnIn,
                      db: Session = Depends(get_db),
                      cu: User = Depends(require_admin_or_pm)):
    cfg = db.query(KanbanConfig).filter(KanbanConfig.project_id == project_id).first()
    if not cfg: raise HTTPException(400, "Configura el tablero Kanban primero")
    existing = db.query(KanbanColumn).filter(
        KanbanColumn.config_id == cfg.id,
        KanbanColumn.status == p.status).first()
    if existing:
        raise HTTPException(400, f"El estado '{p.status}' ya tiene columna")
    col = KanbanColumn(config_id=cfg.id, status=p.status, label=p.label,
                       wip_limit=p.wip_limit, color=p.color, sort_order=p.sort_order)
    db.add(col); db.commit(); db.refresh(col)
    return {"id": col.id, "status": col.status, "wip_limit": col.wip_limit}

@router.patch("/kanban/columns/{column_id}")
def update_kanban_column(column_id: str, p: KanbanColumnIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    col = db.query(KanbanColumn).filter(KanbanColumn.id == column_id).first()
    if not col: _404("Columna")
    col.label = p.label; col.wip_limit = p.wip_limit
    col.color = p.color; col.sort_order = p.sort_order
    db.commit(); db.refresh(col)
    return {"id": col.id, "status": col.status, "wip_limit": col.wip_limit}

@router.delete("/kanban/columns/{column_id}")
def delete_kanban_column(column_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    col = db.query(KanbanColumn).filter(KanbanColumn.id == column_id).first()
    if not col: _404("Columna")
    db.delete(col); db.commit()
    return {"deleted": True}

@router.get("/kanban/{project_id}/board")
def get_kanban_board(project_id: str, sprint_id: Optional[str] = None,
                     swimlane_value: Optional[str] = None,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    """Tablero completo: configuración + tareas agrupadas por columna."""
    cfg = db.query(KanbanConfig).options(joinedload(KanbanConfig.columns)).filter(
        KanbanConfig.project_id == project_id).first()
    cols = cfg.columns if cfg else []
    statuses = [c.status for c in cols] if cols else []

    q = db.query(Task).filter(Task.project_id == project_id)
    if sprint_id:
        from app.models.sprints import SprintTask
        sids = {st.task_id for st in db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint_id).all()}
        q = q.filter(Task.id.in_(sids))
    tasks = q.all()

    wip = {}
    for col in cols:
        col_tasks = [t for t in tasks if t.status == col.status]
        wip[col.status] = {"count": len(col_tasks), "limit": col.wip_limit,
                           "over_limit": col.wip_limit and len(col_tasks) > col.wip_limit}

    by_status: dict = {}
    for t in tasks:
        by_status.setdefault(t.status, []).append({
            "id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "story_points": t.story_points,
            "issue_type": t.issue_type,
            "assigned_to": t.assignee_id,
        })

    return {
        "project_id": project_id,
        "config": {"swimlane_by": cfg.swimlane_by if cfg else "none",
                   "show_subtasks": cfg.show_subtasks if cfg else True},
        "columns": [{"status": c.status, "label": c.label or c.status,
                     "wip_limit": c.wip_limit, "color": c.color,
                     "tasks": by_status.get(c.status, []),
                     "wip": wip.get(c.status, {})} for c in cols],
        "unconfigured_tasks": {s: ts for s, ts in by_status.items()
                               if s not in statuses} if statuses else by_status,
    }


# ═══════════════════════════════════════════════════════════════
# 7. SPRINT PLANNING IA
# ═══════════════════════════════════════════════════════════════

class SprintPlanIn(BaseModel):
    name: str
    project_id: str
    sprint_id: Optional[str] = None
    team_capacity: int = 40   # capacity in story points for the sprint
    priorities: Optional[List[str]] = []   # ids de tareas que se deben incluir sí o sí

@router.post("/sprint-plans/generate")
def generate_sprint_plan(p: SprintPlanIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    """Genera un plan de sprint basado en backlog, capacidad y prioridades."""
    # Query ALL todo tasks — tasks without story_points get a default of 1
    backlog_raw = db.query(Task).filter(
        Task.project_id == p.project_id,
        Task.status == "todo",
    ).all()

    if not backlog_raw:
        raise HTTPException(400, "No hay tareas en estado 'todo' en este proyecto")

    # Assign default story_points for unestimated tasks (treated as 1 SP = smallest unit)
    unestimated_ids = set()
    for t in backlog_raw:
        if t.story_points is None:
            t.story_points = 1   # in-memory only, not committed
            unestimated_ids.add(t.id)

    # Sort by story_points desc (prioritise bigger chunks), then by priority
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    backlog = sorted(
        backlog_raw,
        key=lambda t: (-t.story_points, PRIORITY_ORDER.get(t.priority or "low", 3))
    )

    selected = []; total = 0
    reasoning_parts = []

    # Primero incluir las tareas marcadas como prioritarias
    must_include = {tid for tid in (p.priorities or [])}
    for t in backlog:
        if t.id in must_include:
            selected.append(t)
            total += t.story_points
            est_note = " (sin estimar — asignado 1p por defecto)" if t.id in unestimated_ids else ""
            reasoning_parts.append(f"• '{t.title}' incluida por prioridad manual ({t.story_points}p){est_note}")

    # Rellenar hasta la capacidad por story points
    for t in backlog:
        if t.id in {s.id for s in selected}:
            continue
        pts = t.story_points
        est_note = " [~1p sin estimación]" if t.id in unestimated_ids else ""
        if total + pts <= p.team_capacity:
            selected.append(t)
            total += pts
            reasoning_parts.append(
                f"• '{t.title}' — {pts}p, prioridad {t.priority or 'normal'}{est_note}")
        else:
            if total >= p.team_capacity * 0.7:
                reason = "capacidad alcanzada"
            else:
                reason = f"añadir {pts}p superaría la capacidad de {p.team_capacity}p"
            reasoning_parts.append(f"  ✗ '{t.title}' ({pts}p) excluida — {reason}")

    unestimated_count = len([t for t in selected if t.id in unestimated_ids])
    unestimated_note = (
        f"\n⚠ {unestimated_count} tarea(s) sin story points estimados — asignado 1p por defecto. "
        "Se recomienda estimar el backlog antes de planificar."
        if unestimated_count else ""
    )

    reasoning = (
        f"Plan generado para capacidad de {p.team_capacity} story points.\n"
        f"Tareas seleccionadas: {len(selected)} ({total}p de {p.team_capacity}p disponibles)."
        f"{unestimated_note}\n\n"
        + "\n".join(reasoning_parts)
    )

    plan = SprintPlan(project_id=p.project_id, sprint_id=p.sprint_id,
                      name=p.name, total_points=total,
                      team_capacity=p.team_capacity,
                      ai_reasoning=reasoning, status="draft",
                      created_by=cu.id)
    db.add(plan); db.flush()
    for i, t in enumerate(selected):
        db.add(SprintPlanTask(plan_id=plan.id, task_id=t.id, priority=i,
                              ai_note=f"{t.story_points}p · {t.priority or 'normal'}"))
    db.commit(); db.refresh(plan)

    # Reset in-memory mutations (story_points) before returning — don't leak
    db.expire_all()

    return {
        "id": plan.id, "name": plan.name, "status": plan.status,
        "total_points": total, "team_capacity": p.team_capacity,
        "utilization_pct": round(total / p.team_capacity * 100) if p.team_capacity else 0,
        "task_count": len(selected),
        "ai_reasoning": reasoning,
        "unestimated_count": unestimated_count,
        "tasks": [{"task_id": t.id, "title": t.title,
                   "story_points": t.story_points,
                   "priority": t.priority,
                   "unestimated": t.id in unestimated_ids}
                  for t in selected],
    }

@router.get("/sprint-plans/{project_id}")
def list_sprint_plans(project_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(get_current_user)):
    plans = db.query(SprintPlan).filter(
        SprintPlan.project_id == project_id
    ).order_by(SprintPlan.created_at.desc()).all()
    return [{"id": p.id, "name": p.name, "status": p.status,
             "total_points": p.total_points, "team_capacity": p.team_capacity,
             "task_count": len(p.tasks),
             "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in plans]

@router.patch("/sprint-plans/{plan_id}/status")
def update_plan_status(plan_id: str, status: str,
                       db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    if status not in ("draft", "accepted", "rejected"):
        raise HTTPException(400, "Estado válido: draft, accepted, rejected")
    plan = db.query(SprintPlan).filter(SprintPlan.id == plan_id).first()
    if not plan: _404("Plan")
    plan.status = status; db.commit()
    return {"id": plan.id, "status": plan.status}

@router.delete("/sprint-plans/{plan_id}")
def delete_sprint_plan(plan_id: str, db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    plan = db.query(SprintPlan).filter(SprintPlan.id == plan_id).first()
    if not plan: _404("Plan")
    db.delete(plan); db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# 8. SLA AVANZADO CON CALENDARIOS DE FESTIVOS
# ═══════════════════════════════════════════════════════════════

class SLACalendarIn(BaseModel):
    name: str
    timezone: str = settings.DEFAULT_TIMEZONE
    work_start: str = "09:00"
    work_end: str = "18:00"
    work_days: str = "1,2,3,4,5"

class SLAHolidayIn(BaseModel):
    holiday_date: str
    name: Optional[str] = None

@router.get("/sla-calendars")
def list_sla_calendars(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    cals = db.query(SLACalendar).options(joinedload(SLACalendar.holidays)).all()
    return [{"id": c.id, "name": c.name, "timezone": c.timezone,
             "work_start": c.work_start, "work_end": c.work_end,
             "work_days": c.work_days,
             "holiday_count": len(c.holidays)} for c in cals]

@router.post("/sla-calendars")
def create_sla_calendar(p: SLACalendarIn, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    c = SLACalendar(name=p.name, timezone=p.timezone,
                    work_start=p.work_start, work_end=p.work_end,
                    work_days=p.work_days)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.patch("/sla-calendars/{cal_id}")
def update_sla_calendar(cal_id: str, p: SLACalendarIn,
                        db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id).first()
    if not c: _404("Calendario")
    for k, v in p.model_dump(exclude_unset=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.delete("/sla-calendars/{cal_id}")
def delete_sla_calendar(cal_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id).first()
    if not c: _404("Calendario")
    db.delete(c); db.commit()
    return {"deleted": True}

@router.get("/sla-calendars/{cal_id}/holidays")
def list_holidays(cal_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    hs = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.calendar_id == cal_id
    ).order_by(V21SLAHoliday.holiday_date).all()
    return [{"id": h.id, "holiday_date": h.holiday_date, "name": h.name} for h in hs]

@router.post("/sla-calendars/{cal_id}/holidays")
def add_holiday(cal_id: str, p: SLAHolidayIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    if not db.query(SLACalendar).filter(SLACalendar.id == cal_id).first():
        _404("Calendario")
    h = V21SLAHoliday(calendar_id=cal_id, holiday_date=p.holiday_date, name=p.name)
    db.add(h); db.commit(); db.refresh(h)
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}


@router.patch("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def update_holiday(cal_id: str, holiday_id: str, p: SLAHolidayIn,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    h = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.id == holiday_id, V21SLAHoliday.calendar_id == cal_id).first()
    if not h: _404("Festivo")
    h.holiday_date = p.holiday_date
    if p.name is not None:
        h.name = p.name
    db.commit(); db.refresh(h)
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name}

@router.delete("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def delete_holiday(cal_id: str, holiday_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    h = db.query(V21SLAHoliday).filter(
        V21SLAHoliday.id == holiday_id, V21SLAHoliday.calendar_id == cal_id).first()
    if not h: _404("Festivo")
    db.delete(h); db.commit()
    return {"deleted": True}

@router.get("/sla-calendars/{cal_id}/check-date")
def check_is_business_day(cal_id: str, check_date: str,
                           db: Session = Depends(get_db),
                           cu: User = Depends(get_current_user)):
    """Comprueba si una fecha es día laborable según el calendario."""
    c = db.query(SLACalendar).filter(SLACalendar.id == cal_id).first()
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
        V21SLAHoliday.holiday_date == check_date).first()
    is_holiday  = holiday_obj is not None
    holiday_name = holiday_obj.name if holiday_obj else None

    return {
        "date": check_date,
        "is_business_day": not is_weekend and not is_holiday,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "day_of_week": d.strftime("%A"),
    }
