"""Contecflow v21 — Wiki tags, comentarios internos, CMDB, dashboard agente,
   wiki PDF, Kanban avanzado, sprint planning, SLA avanzado. Thin delegate router."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_admin_or_pm, require_any_manager
from app.models.user import User
import app.services.cmdb_service as svc

router = APIRouter()
sd_router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# 1. WIKI TAGS
# ══════════════════════════════════════════════════════════════════════════════

class WikiTagIn(BaseModel):
    name: str
    color: str = "#7a8aaa"


@router.get("/wiki-tags/{space_id}")
def list_tags(space_id: str, db: Session = Depends(get_db),
              cu: User = Depends(get_current_user)):
    return svc.list_wiki_tags(space_id, db)


@router.post("/wiki-tags/{space_id}")
def create_tag(space_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.create_wiki_tag(space_id, p.name, p.color, cu.id, db)


@router.patch("/wiki-tags/{tag_id}")
def update_tag(tag_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.update_wiki_tag(tag_id, p.name, p.color, db)


@router.delete("/wiki-tags/{tag_id}")
def delete_tag(tag_id: str, db: Session = Depends(get_db),
               cu: User = Depends(require_admin_or_pm)):
    return svc.delete_wiki_tag(tag_id, db)


@router.post("/wiki-pages/{page_id}/tags/{tag_id}")
def add_page_tag(page_id: str, tag_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.add_page_tag(page_id, tag_id, db)


@router.delete("/wiki-pages/{page_id}/tags/{tag_id}")
def remove_page_tag(page_id: str, tag_id: str,
                    db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.remove_page_tag(page_id, tag_id, db)


@router.get("/wiki-pages/{page_id}/tags")
def get_page_tags(page_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    return svc.get_page_tags(page_id, db)


@router.get("/wiki-tags/{space_id}/pages")
def pages_by_tag(space_id: str, tag_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.get_pages_by_tag(space_id, tag_id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERNAL TICKET COMMENTS
# ══════════════════════════════════════════════════════════════════════════════

class InternalCommentIn(BaseModel):
    content: str


@sd_router.get("/tickets/{ticket_id}/internal-comments")
def list_internal_comments_route(ticket_id: str, db: Session = Depends(get_db),
                                 cu: User = Depends(require_any_manager)):
    return svc.list_internal_comments(ticket_id, db)


@sd_router.post("/tickets/{ticket_id}/internal-comments")
def add_internal_comment_route(ticket_id: str, p: InternalCommentIn,
                                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.add_internal_comment(ticket_id, p.content, cu.id, db)


@sd_router.patch("/tickets/{ticket_id}/internal-comments/{comment_id}")
def update_internal_comment_route(ticket_id: str, comment_id: str, p: InternalCommentIn,
                                   db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.update_internal_comment(ticket_id, comment_id, p.content, cu.id, db)


@sd_router.delete("/tickets/{ticket_id}/internal-comments/{comment_id}")
def delete_internal_comment_route(ticket_id: str, comment_id: str,
                                   db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.delete_internal_comment(ticket_id, comment_id, cu.id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 3. CMDB
# ══════════════════════════════════════════════════════════════════════════════

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


@router.get("/categories")
def list_cmdb_categories(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.list_cmdb_categories(db)


@router.post("/categories")
def create_cmdb_category(p: CMDBCategoryIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.create_cmdb_category(p.name, p.icon, p.color, db)


@router.get("/items")
def list_cmdb_items(
    ci_type: Optional[str] = None, status: Optional[str] = None,
    category_id: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), cu: User = Depends(get_current_user),
):
    return svc.list_cmdb_items(ci_type, status, category_id, q, cu.organization_id, db)


@router.post("/items")
def create_cmdb_item(p: CMDBItemIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    return svc.create_cmdb_item(p, cu.id, db)


@router.patch("/items/{item_id}")
def update_cmdb_item(item_id: str, p: CMDBItemUpdate,
                     db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.update_cmdb_item(item_id, p, cu.id, db)


@router.delete("/items/{item_id}")
def delete_cmdb_item(item_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_admin_or_pm)):
    return svc.delete_cmdb_item(item_id, db)


@router.get("/items/{item_id}/changelog", summary="Historial de cambios del activo")
def get_cmdb_changelog(
    item_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return svc.get_cmdb_changelog(item_id, limit, db)


@router.get("/items/{item_id}/relations")
def item_relations(item_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    return svc.get_item_relations(item_id, db)


@router.post("/relations")
def create_cmdb_relation(p: CMDBRelationIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.create_cmdb_relation(p.from_item_id, p.to_item_id, p.rel_type, db)


@router.delete("/relations/{relation_id}")
def delete_cmdb_relation(relation_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.delete_cmdb_relation(relation_id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 4. AGENT DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/agent-dashboard/{agent_id}")
def agent_dashboard(agent_id: str, days: int = 30,
                    db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.get_agent_dashboard(agent_id, days, db)


@router.post("/agent-dashboard/{agent_id}/snapshot")
def create_agent_snapshot(agent_id: str, db: Session = Depends(get_db),
                          cu: User = Depends(require_admin_or_pm)):
    return svc.create_agent_snapshot(agent_id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 5. WIKI EXPORT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/wiki-export/{page_id}")
def export_wiki_page(page_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(get_current_user)):
    return svc.create_wiki_export_job(page_id, cu.id, db)


@router.get("/wiki-export/jobs")
def list_export_jobs(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.list_wiki_export_jobs(cu.id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 6. KANBAN
# ══════════════════════════════════════════════════════════════════════════════

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
    return svc.get_kanban_config(project_id, db)


@router.post("/kanban/{project_id}")
def upsert_kanban_config(project_id: str, p: KanbanConfigIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.upsert_kanban_config(project_id, p.swimlane_by, p.show_subtasks, p.card_fields, db)


@router.post("/kanban/{project_id}/columns")
def add_kanban_column(project_id: str, p: KanbanColumnIn,
                      db: Session = Depends(get_db),
                      cu: User = Depends(require_admin_or_pm)):
    return svc.add_kanban_column(project_id, p.status, p.label, p.wip_limit, p.color, p.sort_order, db)


@router.patch("/kanban/columns/{column_id}")
def update_kanban_column(column_id: str, p: KanbanColumnIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.update_kanban_column(column_id, p.label, p.wip_limit, p.color, p.sort_order, db)


@router.delete("/kanban/columns/{column_id}")
def delete_kanban_column(column_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.delete_kanban_column(column_id, db)


@router.get("/kanban/{project_id}/board")
def get_kanban_board(project_id: str, sprint_id: Optional[str] = None,
                     swimlane_value: Optional[str] = None,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return svc.get_kanban_board(project_id, sprint_id, swimlane_value, db)


# ══════════════════════════════════════════════════════════════════════════════
# 7. SPRINT PLANNING
# ══════════════════════════════════════════════════════════════════════════════

class SprintPlanIn(BaseModel):
    name: str
    project_id: str
    sprint_id: Optional[str] = None
    team_capacity: int = 40
    priorities: Optional[List[str]] = []


@router.post("/sprint-plans/generate")
def generate_sprint_plan(p: SprintPlanIn, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return svc.generate_sprint_plan(
        p.project_id, p.sprint_id, p.name, p.team_capacity, p.priorities or [], cu.id, db
    )


@router.get("/sprint-plans/{project_id}")
def list_sprint_plans(project_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(get_current_user)):
    return svc.list_sprint_plans(project_id, db)


@router.patch("/sprint-plans/{plan_id}/status")
def update_plan_status(plan_id: str, status: str,
                       db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    return svc.update_sprint_plan_status(plan_id, status, db)


@router.delete("/sprint-plans/{plan_id}")
def delete_sprint_plan(plan_id: str, db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    return svc.delete_sprint_plan(plan_id, db)


# ══════════════════════════════════════════════════════════════════════════════
# 8. SLA CALENDARS
# ══════════════════════════════════════════════════════════════════════════════

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
    return svc.list_sla_calendars(db)


@router.post("/sla-calendars")
def create_sla_calendar(p: SLACalendarIn, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    return svc.create_sla_calendar(p.name, p.timezone, p.work_start, p.work_end, p.work_days, db)


@router.patch("/sla-calendars/{cal_id}")
def update_sla_calendar(cal_id: str, p: SLACalendarIn,
                        db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    return svc.update_sla_calendar(cal_id, p, db)


@router.delete("/sla-calendars/{cal_id}")
def delete_sla_calendar(cal_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    return svc.delete_sla_calendar(cal_id, db)


@router.get("/sla-calendars/{cal_id}/holidays")
def list_holidays(cal_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    return svc.list_sla_holidays(cal_id, db)


@router.post("/sla-calendars/{cal_id}/holidays")
def add_holiday(cal_id: str, p: SLAHolidayIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.add_sla_holiday(cal_id, p.holiday_date, p.name, db)


@router.patch("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def update_holiday(cal_id: str, holiday_id: str, p: SLAHolidayIn,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.update_sla_holiday(cal_id, holiday_id, p.holiday_date, p.name, db)


@router.delete("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def delete_holiday(cal_id: str, holiday_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return svc.delete_sla_holiday(cal_id, holiday_id, db)


@router.get("/sla-calendars/{cal_id}/check-date")
def check_is_business_day(cal_id: str, check_date: str,
                           db: Session = Depends(get_db),
                           cu: User = Depends(get_current_user)):
    return svc.check_is_business_day(cal_id, check_date, db)
