"""Contecflow v21 — Wiki tags, comentarios internos, CMDB, dashboard agente,
   wiki PDF, Kanban avanzado, sprint planning, SLA avanzado. Thin delegate router."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
from pydantic import BaseModel, field_validator

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import (
    get_current_user,
    require_admin_or_pm,
    require_internal_user,
)
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
import app.services.cmdb_service as svc
from app.core.constantes import MAX_TAMANO_DE_PAGINA

logger = logging.getLogger(__name__)

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
    return APIListResponse.ok(items=svc.list_wiki_tags(space_id, db))


@router.post("/wiki-tags/{space_id}")
def create_tag(space_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.create_wiki_tag(space_id, p.name, p.color, cu.id, db))


@router.patch("/wiki-tags/{tag_id}")
def update_tag(tag_id: str, p: WikiTagIn,
               db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.update_wiki_tag(tag_id, p.name, p.color, db))


@router.delete("/wiki-tags/{tag_id}")
def delete_tag(tag_id: str, db: Session = Depends(get_db),
               cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "wiki_tag", tag_id, action="delete")
    return APIResponse.ok(data=svc.delete_wiki_tag(tag_id, db))


@router.post("/wiki-pages/{page_id}/tags/{tag_id}")
def add_page_tag(page_id: str, tag_id: str,
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.add_page_tag(page_id, tag_id, db))


@router.delete("/wiki-pages/{page_id}/tags/{tag_id}")
def remove_page_tag(
    page_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada.
    #
    # Aqui NO se copia el `admin_or_pm` dominante del fichero: poner
    # una etiqueta esta abierto a todos y quitarla es su inversa
    # exacta, reversible en un clic. Restringir solo el quitar
    # dejaria etiquetas puestas por error que nadie salvo un PM
    # podria limpiar. Se excluye al subcontratista y ya.
    _: User = Depends(require_internal_user),
):
    enforce_abac(db, cu, "wiki_page_tag", tag_id, action="delete")
    return APIResponse.ok(data=svc.remove_page_tag(page_id, tag_id, db))


@router.get("/wiki-pages/{page_id}/tags")
def get_page_tags(page_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=svc.get_page_tags(page_id, db))


@router.get("/wiki-tags/{space_id}/pages")
def pages_by_tag(space_id: str, tag_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=svc.get_pages_by_tag(space_id, tag_id, db))


# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERNAL TICKET COMMENTS
# ══════════════════════════════════════════════════════════════════════════════











# ══════════════════════════════════════════════════════════════════════════════
# 3. CMDB — vive en /sd/cmdb (endpoints/service_desk/cmdb.py). Auditoria
# 2026-11: aqui habia una segunda CMDB; la migracion 110 la fundio.
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# 4. AGENT DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/agent-dashboard/{agent_id}")
def agent_dashboard(agent_id: str, days: int = 30,
                    db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    # Auditoria 2026-11: admin y PM, como la pantalla (antes cualquier usuario
    # leia el rendimiento de cualquier agente). Se calcula sobre los tickets;
    # la «foto» que habia que pedir a mano ya no hace falta.
    return APIResponse.ok(data=svc.get_agent_dashboard(agent_id, days, db))


# ══════════════════════════════════════════════════════════════════════════════
# 5. WIKI EXPORT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/wiki-export/{page_id}")
def export_wiki_page(page_id: str, db: Session = Depends(get_db),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                     cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.create_wiki_export_job(page_id, cu.id, db))


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
    return APIResponse.ok(data=svc.get_kanban_config(project_id, db))


@router.post("/kanban/{project_id}")
def upsert_kanban_config(project_id: str, p: KanbanConfigIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.upsert_kanban_config(project_id, p.swimlane_by, p.show_subtasks, p.card_fields, db))


@router.post("/kanban/{project_id}/columns")
def add_kanban_column(project_id: str, p: KanbanColumnIn,
                      db: Session = Depends(get_db),
                      cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.add_kanban_column(project_id, p.status, p.label, p.wip_limit, p.color, p.sort_order, db))


@router.patch("/kanban/columns/{column_id}")
def update_kanban_column(column_id: str, p: KanbanColumnIn,
                         db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.update_kanban_column(column_id, p.label, p.wip_limit, p.color, p.sort_order, db))


@router.delete("/kanban/columns/{column_id}")
def delete_kanban_column(column_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "kanban_column", column_id, action="delete")
    return APIResponse.ok(data=svc.delete_kanban_column(column_id, db))


@router.get("/kanban/{project_id}/board")
def get_kanban_board(project_id: str, sprint_id: Optional[str] = None,
                     swimlane_value: Optional[str] = None,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.get_kanban_board(project_id, sprint_id, swimlane_value, db))


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
    return APIResponse.ok(data=svc.generate_sprint_plan(
        p.project_id, p.sprint_id, p.name, p.team_capacity, p.priorities or [], cu.id, db
    ))


@router.get("/sprint-plans/{project_id}")
def list_sprint_plans(project_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=svc.list_sprint_plans(project_id, db))


@router.patch("/sprint-plans/{plan_id}/status")
def update_plan_status(plan_id: str, status: str,
                       db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.update_sprint_plan_status(plan_id, status, db))


@router.delete("/sprint-plans/{plan_id}")
def delete_sprint_plan(plan_id: str, db: Session = Depends(get_db),
                       cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "sprint_plan", plan_id, action="delete")
    return APIResponse.ok(data=svc.delete_sprint_plan(plan_id, db))


# ══════════════════════════════════════════════════════════════════════════════
# 8. SLA CALENDARS
# ══════════════════════════════════════════════════════════════════════════════

class SLACalendarIn(BaseModel):
    """Calendario de servicio. Las politicas de SLA lo usan para contar horas.

    Auditoria 2026-11: se aceptaba cualquier texto. Mientras ningun SLA leia
    el calendario daba igual; ahora una zona o una hora mal escrita romperia el
    calculo de los vencimientos, asi que se rechaza al guardar.
    """
    name: str
    timezone: str = settings.DEFAULT_TIMEZONE
    work_start: str = "09:00"
    work_end: str = "18:00"
    work_days: str = "1,2,3,4,5"

    @field_validator("timezone")
    @classmethod
    def _zona(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"zona horaria desconocida: {v}") from exc
        return v

    @field_validator("work_start", "work_end")
    @classmethod
    def _hora(cls, v: str) -> str:
        from app.services.sla_service import parse_hora
        parse_hora(v)
        return v

    @field_validator("work_days")
    @classmethod
    def _dias(cls, v: str) -> str:
        from app.services.sla_service import parse_dias_laborables
        return ",".join(str(d) for d in sorted(parse_dias_laborables(v)))

    @field_validator("work_end")
    @classmethod
    def _fin_tras_inicio(cls, v: str, info) -> str:
        from app.services.sla_service import parse_hora
        inicio = info.data.get("work_start")
        if inicio and parse_hora(v) <= parse_hora(inicio):
            raise ValueError("la jornada tiene que acabar después de empezar")
        return v


class SLAHolidayIn(BaseModel):
    holiday_date: str
    name: Optional[str] = None

    @field_validator("holiday_date")
    @classmethod
    def _fecha(cls, v: str) -> str:
        from datetime import date as _date
        try:
            return _date.fromisoformat(v).isoformat()
        except ValueError as exc:
            raise ValueError("fecha inválida: usa AAAA-MM-DD") from exc


@router.get("/sla-calendars", response_model=APIListResponse[dict])
def list_sla_calendars(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    items = svc.list_sla_calendars(db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/sla-calendars")
def create_sla_calendar(p: SLACalendarIn, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.create_sla_calendar(p.name, p.timezone, p.work_start, p.work_end, p.work_days, db))


@router.patch("/sla-calendars/{cal_id}")
def update_sla_calendar(cal_id: str, p: SLACalendarIn,
                        db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.update_sla_calendar(cal_id, p, db))


@router.delete("/sla-calendars/{cal_id}")
def delete_sla_calendar(cal_id: str, db: Session = Depends(get_db),
                        cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "sla_calendar", cal_id, action="delete")
    return APIResponse.ok(data=svc.delete_sla_calendar(cal_id, db))


@router.get("/sla-calendars/{cal_id}/holidays", response_model=APIListResponse[dict])
def list_holidays(
    cal_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    items = svc.list_sla_holidays(cal_id, db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/sla-calendars/{cal_id}/holidays")
def add_holiday(cal_id: str, p: SLAHolidayIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.add_sla_holiday(cal_id, p.holiday_date, p.name, db))


@router.patch("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def update_holiday(cal_id: str, holiday_id: str, p: SLAHolidayIn,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.update_sla_holiday(cal_id, holiday_id, p.holiday_date, p.name, db))


@router.delete("/sla-calendars/{cal_id}/holidays/{holiday_id}")
def delete_holiday(cal_id: str, holiday_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "sla_holiday", holiday_id, action="delete")
    return APIResponse.ok(data=svc.delete_sla_holiday(cal_id, holiday_id, db))


@router.get("/sla-calendars/{cal_id}/check-date")
def check_is_business_day(cal_id: str, check_date: str,
                           db: Session = Depends(get_db),
                           cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.check_is_business_day(cal_id, check_date, db))
