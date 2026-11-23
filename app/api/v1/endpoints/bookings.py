
"""
bookings.py router — thin delegates to bookings_service.
"""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.db.session import get_db
from app.core.deps import (
    get_current_user,
    requiere_capacidad,
)
from app.core.abac_enforce import enforce_abac
from app.core.periodo import SEMANA, Periodo, periodo
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.schemas.bookings import (
    BookingCreate,
    BookingUpdate,
    SLAScheduleCreate,
    ApiKeyCreate,
    RecurringCreate,
)
from app.services import bookings_service as svc

# Auditoría 2026-08 (hallazgo 22): antes `v238_service`, nombrado por número de
# versión. Los conflictos de reserva y el nivelado del Gantt son planificación de
# capacidad y viven en su propio módulo.
from app.services import capacity_planning_service
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


# ── Capacity: Conflicts & Gantt Leveling (v238) ─────────────────────────────
@router.get("/conflicts")
def get_booking_conflicts(
    user_id: Optional[str] = None,
    start_date: Optional[date] = None,  # barrido final 2026-11: era str + fromisoformat (500)
    end_date: Optional[date] = None,  # barrido final 2026-11: era str + fromisoformat (500)
    threshold_pct: float = Query(100.0, ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("reservas.gestionar")),
):
    sd = start_date
    ed = end_date
    return APIResponse.ok(data=capacity_planning_service.get_booking_conflicts(user_id, sd, ed, threshold_pct, db))

@router.get("/gantt-leveling")
def get_gantt_leveling(
    project_id: Optional[str] = None,
    start_date: Optional[date] = None,  # barrido final 2026-11: era str + fromisoformat (500)
    end_date: Optional[date] = None,  # barrido final 2026-11: era str + fromisoformat (500)
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("reservas.gestionar")),
):
    sd = start_date
    ed = end_date
    return APIResponse.ok(data=capacity_planning_service.get_gantt_leveling(project_id, sd, ed, db))





# ── Resource Bookings ─────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[dict])
def list_bookings(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    booking_type: Optional[str] = None,
    # Ventana visible del planificador: reservas que solapan con [date_from, date_to]
    # (SQL). ResourceSchedulerPage pide solo lo que se ve y vuelve a pedir al mover
    # la ventana, en vez de cargar todas las reservas.
    date_from: Optional[date] = Query(None, description="Solo reservas que acaban en o despues de esta fecha"),
    date_to: Optional[date] = Query(None, description="Solo reservas que empiezan en o antes de esta fecha"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("reservas.gestionar")),
):
    items = svc.list_bookings_records(user_id, project_id, start_date, end_date,
                                      booking_type, current_user.organization_id, db,
                                      date_from=date_from, date_to=date_to)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.get("/heatmap")
def bookings_heatmap(weeks: Optional[int] = Query(None, ge=1, le=52, description="Compatibilidad: próximas N semanas (12). `desde`/`hasta` mandan."),
                     p: Periodo = Depends(periodo(dias_por_defecto=12 * 7, granularidades=(SEMANA,),
                                                  sentido="futuro")),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    """Mapa de reservas por persona y semana. Periodo libre (16-11-2026):
    horizonte hacia delante con ``desde``/``hasta`` (por semanas, máx. 52);
    sin ellos, las próximas ``weeks`` semanas como antes."""
    from app.services.resource_analytics import semanas_del_periodo
    semanas = semanas_del_periodo(p) if p.origen != "defecto" else None
    datos = svc.get_bookings_heatmap(weeks or 12, current_user.organization_id, db, semanas=semanas)
    datos["periodo"] = p.a_dict() if semanas else None
    return APIResponse.ok(data=datos)


@router.post("")
def create_booking(payload: BookingCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.create_booking_record(payload, current_user.id, db))


@router.patch("/{booking_id}")
def update_booking(booking_id: str, payload: BookingUpdate,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.update_booking_record(booking_id, payload, db))


@router.delete("/{booking_id}")
def delete_booking(booking_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    enforce_abac(db, current_user, "resource_booking", booking_id, action="delete")
    return APIResponse.ok(data=svc.delete_booking_record(booking_id, db))


# ── SLA Schedules ─────────────────────────────────────────────────────────────

@router.get("/sla-schedules", response_model=APIListResponse[dict])
def list_sla_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = svc.list_sla_schedules_records(db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/sla-schedules")
def create_sla_schedule(payload: SLAScheduleCreate, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("reservas.administrar"))):
    return APIResponse.ok(data=svc.create_sla_schedule_record(payload, db))


@router.post("/sla-schedules/calculate-deadline")
def calculate_sla_deadline(payload: dict = Body(...), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("reservas.usar")),  # auditoria 2026-09: excepcion revisada: calcula una fecha
                           current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.calculate_sla_deadline_record(payload, db))


@router.post("/sla-schedules/{schedule_id}/holidays")
def add_holidays(schedule_id: str, payload: dict = Body(...),
                 db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("reservas.administrar"))):
    return APIResponse.ok(data=svc.add_holidays_record(schedule_id, payload, db))


@router.delete("/sla-schedules/{schedule_id}/holidays/{holiday_id}")
def delete_holiday(schedule_id: str, holiday_id: str,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("reservas.administrar"))):
    enforce_abac(db, current_user, "booking_sla_holiday", holiday_id, action="delete")
    return APIResponse.ok(data=svc.delete_holiday_record(schedule_id, holiday_id, db))


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/api-keys", response_model=APIListResponse[dict])
def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 18-11-2026: solo el superadmin real (flag) ve las claves de todos; antes el
    # rol `admin` contaba como superadmin y un admin de empresa veía las ajenas.
    is_superadmin = bool(getattr(current_user, "is_superadmin", False))
    items = svc.list_api_keys_records(current_user.id, is_superadmin, db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/api-keys")
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("reservas.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                   current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.create_api_key_record(payload, current_user.id, db))


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    enforce_abac(db, current_user, "booking_api_key", key_id, action="delete")
    return APIResponse.ok(data=svc.revoke_api_key_record(key_id, current_user.id, db))


# Auditoria 2026-11: se quito `POST /api-keys/verify` (sin autenticar). Era un
# oraculo de claves y sobraba: la clave ya autentica (`GET /auth/me` con ella).


# ── Recurring Invoices ────────────────────────────────────────────────────────

@router.get("/recurring", response_model=APIListResponse[dict])
def list_recurring(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("reservas.gestionar")),
):
    items = svc.list_recurring_records(db)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/recurring")
def create_recurring(payload: RecurringCreate, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.create_recurring_record(payload, current_user.id, db))


@router.patch("/recurring/{rec_id}")
def update_recurring(rec_id: str, payload: dict = Body(...),
                     db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.update_recurring_record(rec_id, payload, db))


@router.post("/recurring/process-due")
def process_due_recurring(db: Session = Depends(get_db),
                          current_user: User = Depends(requiere_capacidad("reservas.administrar"))):
    return APIResponse.ok(data=svc.process_due_recurring_records(db, current_user))


@router.post("/recurring/{rec_id}/generate-now")
def generate_recurring_now(rec_id: str, db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.generate_recurring_now_record(rec_id, db, current_user))


# ── Pipeline Ops ──────────────────────────────────────────────────────────────

@router.post("/pipeline/convert/{opportunity_id}")
def convert_opportunity_to_project(opportunity_id: str, payload: dict = Body(default={}),
                                   db: Session = Depends(get_db),
                                   current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.convert_opportunity_to_project_record(opportunity_id, payload, current_user, db))


@router.get("/pipeline/revenue-forecast")
def pipeline_revenue_forecast(db: Session = Depends(get_db),
                              current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.get_pipeline_revenue_forecast(db))


# ── ITSM Aging ────────────────────────────────────────────────────────────────

@router.get("/itsm/aging")
def ticket_aging_report(db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.get_ticket_aging_report(db))


@router.get("/itsm/wallboard")
def get_wallboard(db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("reservas.gestionar"))):
    return APIResponse.ok(data=svc.get_wallboard_data(db))


# ── SSO ───────────────────────────────────────────────────────────────────────
# Auditoria 2026-11: aqui habia un segundo SSO (/bookings/sso/initiate,
# /oidc/callback, /saml/callback) sin autenticar y roto: leia columnas que no
# existen (issuer, jwks_uri, client_id), toda vuelta acababa en 401, y SAML
# devolvia 503. El SSO de la aplicacion es /auth/sso/* (routers/auth_sso.py).


# ── Workflow Engine ───────────────────────────────────────────────────────────

@router.post("/workflows/enqueue")
def enqueue_workflow(payload: dict = Body(...), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("reservas.gestionar")),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
                     current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.enqueue_workflow_record(payload, current_user.id, db))


@router.post("/workflows/process-queue")
def process_workflow_queue(db: Session = Depends(get_db),
                           current_user: User = Depends(requiere_capacidad("reservas.administrar"))):
    # Segunda auditoria 2026-11 (n.º 20): cada elemento puede mandar correos o
    # llamar webhooks; la pasada va al worker. Con cola: 202 `{status: "queued"}`.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    resultado = encolar(svc.process_workflow_queue_record, _sesion=db)
    if resultado is EN_COLA:
        return respuesta_en_cola()
    return APIResponse.ok(data=resultado)
