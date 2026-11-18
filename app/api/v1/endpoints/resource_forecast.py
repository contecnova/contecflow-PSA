"""
resource_forecast.py — Proyección de capacidad de recursos a 6-12 meses.

Cruza:
  - ResourceBooking (reservas confirmadas)
  - CapacityPlan (planificación semanal)
  - Absences (vacaciones y ausencias aprobadas)
  - Pipeline (proyectos en won/negotiation con fecha probable de inicio)
  - User.weekly_capacity_hours (capacidad máxima)

Endpoints:
  Periodo libre (16-11-2026): /weeks, /users/{id} y /summary aceptan
  desde/hasta (horizonte hacia delante, por semanas, máx. 52); `weeks` y
  `from_date` siguen valiendo cuando no llegan.

  GET /resource-forecast/weeks?weeks=26&department=...
      → heatmap semanal por persona: % carga + horas por semana
  GET /resource-forecast/users/{user_id}?weeks=26
      → detalle de un recurso: breakdown por proyecto semana a semana
  GET /resource-forecast/availability?role=...&hours=40&from=...
      → qué personas tienen disponibilidad para X horas en un rango
  GET /resource-forecast/summary?weeks=12
      → resumen ejecutivo: carga media equipo, semanas de riesgo, personas saturadas
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta

from app.services.settings_service.por_empresa import capacidad_semanal
from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.responses import APIResponse
from app.models.user import User
from app.services.resource_analytics import (
    get_user_week_hours as _svc_user_week_hours,
    get_forecast_active_users,
    get_forecast_user_by_id,
    get_forecast_project_names,
    get_forecast_past_imputations,
)
from app.core import timeutil
from app.core.periodo import SEMANA, Periodo, periodo

router = APIRouter(tags=["resource-forecast"])


# ── Helpers ────────────────────────────────────────────────────────────────────
from app.services.resource_analytics import (
    monday as _monday,
    weeks_range as _weeks_range,
    week_label as _week_label,
    semanas_del_periodo,
)


def _horizonte(sem_defecto: int):
    """Periodo de un horizonte de previsión (periodo libre, 16-11-2026).

    Hacia delante (``sentido="futuro"``), por semanas. ``desde``/``hasta``
    mandan (también ``days``: los próximos N días); si no llegan, valen
    ``weeks`` y ``from_date`` como antes.
    """
    return periodo(dias_por_defecto=sem_defecto * 7, granularidades=(SEMANA,), sentido="futuro")


def _semanas(p: Periodo, weeks: Optional[int], defecto: int, from_date: Optional[date] = None) -> list:
    if p.origen != "defecto":  # desde/hasta o `days` (accesos rápidos del selector)
        return semanas_del_periodo(p)
    return _weeks_range(_monday(from_date or timeutil.today()), weeks or defecto)


def _periodo_dict(p: Periodo, semanas: list) -> dict:
    """El periodo calculado: el pedido, o el que equivale a ``weeks``."""
    if p.origen != "defecto":
        return p.a_dict()
    return {"desde": str(semanas[0]) if semanas else None,
            "hasta": str(semanas[-1] + timedelta(days=7)) if semanas else None,
            "granularidad": SEMANA, "origen": "weeks"}


def _compute_user_week_hours(user_id: str, week_start: "date", db) -> dict:
    return _svc_user_week_hours(db, user_id, week_start)


def _capacidad(base: float, hw: dict) -> float:
    """Capacidad de esa semana: la del usuario menos sus ausencias aprobadas.

    Auditoria 2026-11: las ausencias se calculaban y no se restaban; una semana
    de vacaciones salia libre.
    """
    # Revisión 2026-11: también los festivos de la empresa.
    # Rev. 180: la base es el horario efectivo de esa semana (turnos, jornada), no la semanal fija.
    from app.services.resource_analytics import capacidad_de_semana
    return capacidad_de_semana(hw, base)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/weeks", summary="Heatmap de carga por persona y semana (6-52 semanas)")
def forecast_heatmap(
    weeks:       Optional[int] = Query(None, ge=4, le=52, description="Compatibilidad: N semanas desde `from_date` (26). `desde`/`hasta` mandan."),
    department:  Optional[str] = Query(None),
    from_date:   Optional[date] = Query(None),   # YYYY-MM-DD, default hoy
    p: Periodo = Depends(_horizonte(26)),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Devuelve una matriz:
      rows → usuarios activos
      cols → semanas (desde hoy hasta +N semanas)
      cell → { load_pct, committed_hours, available_hours, status }
    """
    week_dates = _semanas(p, weeks, 26, from_date)
    start = week_dates[0]

    # Usuarios activos
    users = get_forecast_active_users(db, department=department)

    result_users = []
    for u in users:
        capacity = capacidad_semanal(db, u)
        weeks_data = []
        total_load = 0.0

        for w in week_dates:
            hw = _compute_user_week_hours(u.id, w, db)
            committed = hw["committed_hours"]
            cap = _capacidad(capacity, hw)
            load_pct  = round((committed / cap) * 100, 1) if cap > 0 else (100.0 if committed > 0 else 0)
            available = max(0, round(cap - committed, 1))
            total_load += load_pct

            status = (
                "overloaded"  if load_pct > 100 else
                "high"        if load_pct > 85  else
                "medium"      if load_pct > 50  else
                "low"         if load_pct > 10  else
                "available"
            )

            weeks_data.append({
                "week":            _week_label(w),
                "week_start":      str(w),
                "load_pct":        load_pct,
                "committed_hours": committed,
                "available_hours": available,
                "absence_hours":   hw["absence_hours"],
                "holiday_hours":   hw["holiday_hours"],
                "tentative_hours": hw["tentative_hours"],
                "status":          status,
                "projects":        hw["projects"],
            })

        avg_load = round(total_load / len(week_dates), 1) if week_dates else 0
        overloaded_weeks = sum(1 for wd in weeks_data if wd["load_pct"] > 100)

        result_users.append({
            "user_id":         u.id,
            "user_name":       u.full_name,
            "department":      u.department or "",
            "role":            u.role.value if hasattr(u.role, "value") else str(u.role),
            "capacity_hours":  capacity,
            "avg_load_pct":    avg_load,
            "overloaded_weeks": overloaded_weeks,
            "weeks":           weeks_data,
        })

    return APIResponse.ok(data={
        "from_date":   str(start),
        "weeks":       len(week_dates),
        "week_labels": [_week_label(w) for w in week_dates],
        "users":       result_users,
        "periodo":     _periodo_dict(p, week_dates),
    })


@router.get("/users/{user_id}", summary="Detalle de proyección de un recurso")
def forecast_user_detail(
    user_id:   str,
    weeks:     Optional[int] = Query(None, ge=4, le=52, description="Compatibilidad: N semanas desde `from_date` (13). `desde`/`hasta` mandan."),
    from_date: Optional[date] = Query(None),
    p: Periodo = Depends(_horizonte(13)),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auditoria 2026-11: la ve un responsable (como el resto de la proyeccion)
    # o la propia persona; antes cualquiera leia la carga de cualquiera.
    from app.models.user import UserRole
    if current_user.id != user_id and current_user.role not in (
            UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr):
        from fastapi import HTTPException
        raise HTTPException(403, "Solo responsables o la propia persona")
    u = get_forecast_user_by_id(db, user_id)
    if not u:
        from fastapi import HTTPException
        raise HTTPException(404)

    week_dates = _semanas(p, weeks, 13, from_date)
    capacity   = capacidad_semanal(db, u)

    # Nombres de proyectos
    project_names = get_forecast_project_names(db)

    weeks_detail = []
    for w in week_dates:
        hw       = _compute_user_week_hours(u.id, w, db)
        committed = hw["committed_hours"]
        cap       = _capacidad(capacity, hw)
        load_pct  = round((committed / cap) * 100, 1) if cap > 0 else (100.0 if committed > 0 else 0)

        # Breakdown por proyecto con nombre
        breakdown = []
        for pid, hours in hw["projects"].items():
            breakdown.append({
                "project_id":   pid,
                "project_name": project_names.get(pid, "Sin proyecto"),
                "hours":        hours,
                "pct_of_week":  round((hours / cap) * 100, 1) if cap > 0 else 0,
            })
        breakdown.sort(key=lambda x: x["hours"], reverse=True)

        weeks_detail.append({
            "week":            _week_label(w),
            "week_start":      str(w),
            "load_pct":        load_pct,
            "committed_hours": committed,
            "available_hours": max(0, round(cap - committed, 1)),
            "absence_hours":   hw["absence_hours"],
            "breakdown":       breakdown,
        })

    return APIResponse.ok(data={
        "user_id":        u.id,
        "user_name":      u.full_name,
        "department":     u.department,
        "capacity_hours": capacity,
        "weeks":          weeks_detail,
        "periodo":        _periodo_dict(p, week_dates),
    })


@router.get("/availability", summary="Encontrar personas disponibles para un rango y horas requeridas")
def find_available(
    hours_needed: float         = Query(..., description="Horas requeridas por semana"),
    from_date:    Optional[date] = Query(None),
    to_date:      Optional[date] = Query(None),
    department:   Optional[str] = Query(None),
    role:         Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Devuelve personas con suficiente disponibilidad media en el rango dado."""
    start = _monday(from_date or timeutil.today())
    end   = to_date or start + timedelta(weeks=4)
    week_dates = []
    w = start
    while w <= end:
        week_dates.append(w)
        w += timedelta(weeks=1)

    users = get_forecast_active_users(db, department=department, role=role)

    result = []
    for u in users:
        capacity = capacidad_semanal(db, u)
        availabilities = []
        for w in week_dates:
            hw        = _compute_user_week_hours(u.id, w, db)
            available = max(0, _capacidad(capacity, hw) - hw["committed_hours"])
            availabilities.append(available)

        avg_available = round(sum(availabilities) / len(availabilities), 1) if availabilities else 0
        min_available = min(availabilities) if availabilities else 0
        fits = avg_available >= hours_needed

        result.append({
            "user_id":           u.id,
            "user_name":         u.full_name,
            "department":        u.department or "",
            "avg_available_hrs": avg_available,
            "min_available_hrs": round(min_available, 1),
            "fits_requirement":  fits,
            "availability_pct":  round((avg_available / capacity) * 100, 1) if capacity > 0 else 0,
        })

    result.sort(key=lambda x: x["avg_available_hrs"], reverse=True)
    return APIResponse.ok(data={
        "from_date":      str(start),
        "to_date":        str(end),
        "hours_needed":   hours_needed,
        "candidates":     [r for r in result if r["fits_requirement"]],
        "insufficient":   [r for r in result if not r["fits_requirement"]],
    })


@router.get("/summary", summary="Resumen ejecutivo de capacidad del equipo")
def forecast_summary(
    weeks:      Optional[int] = Query(None, ge=4, le=52, description="Compatibilidad: próximas N semanas (12). `desde`/`hasta` mandan."),
    department: Optional[str] = Query(None),
    p: Periodo = Depends(_horizonte(12)),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """KPIs ejecutivos: carga media, semanas de riesgo, personas saturadas, capacidad libre."""
    week_dates = _semanas(p, weeks, 12)
    weeks = len(week_dates)

    users = get_forecast_active_users(db, department=department)

    if not users:
        return APIResponse.ok(data={
            "total_users": 0,
            "weeks": weeks,
            "avg_team_load_pct": 0,
            "total_capacity_hrs": 0,
            "total_committed_hrs": 0,
            "total_available_hrs": 0,
            "risk_weeks_count": 0,
            "overloaded_users_count": 0,
            "week_trend": [],
            "risk_weeks": [],
            "periodo": _periodo_dict(p, week_dates),
        })

    total_capacity_hrs  = 0.0
    total_committed_hrs = 0.0
    risk_weeks          = set()
    overloaded_users    = set()
    week_loads          = []

    for w in week_dates:
        week_committed = 0.0
        week_capacity  = 0.0
        for u in users:
            hw  = _compute_user_week_hours(u.id, w, db)
            cap = _capacidad(capacidad_semanal(db, u), hw)
            committed = hw["committed_hours"]
            week_committed += committed
            week_capacity  += cap
            if committed > cap * 1.0:
                overloaded_users.add(u.id)
        total_committed_hrs += week_committed
        total_capacity_hrs  += week_capacity
        load = round((week_committed / week_capacity) * 100, 1) if week_capacity > 0 else 0
        week_loads.append({"week": _week_label(w), "load_pct": load})
        if load > 85:
            risk_weeks.add(_week_label(w))

    avg_load = round(total_committed_hrs / total_capacity_hrs * 100, 1) if total_capacity_hrs > 0 else 0

    return APIResponse.ok(data={
        "total_users":          len(users),
        "weeks":                weeks,
        "avg_team_load_pct":    avg_load,
        "total_capacity_hrs":   round(total_capacity_hrs, 0),
        "total_committed_hrs":  round(total_committed_hrs, 1),
        "total_available_hrs":  round(total_capacity_hrs - total_committed_hrs, 1),
        "risk_weeks_count":     len(risk_weeks),
        "overloaded_users_count": len(overloaded_users),
        "week_trend":           week_loads,
        "risk_weeks":           sorted(list(risk_weeks)),
        "periodo":              _periodo_dict(p, week_dates),
    })


# ── Utilization trend (historical actuals + forward projection) ────────────────

@router.get("/utilization-trend", summary="Tendencia de utilización histórica y proyectada")
def utilization_trend(
    weeks_past:   int = Query(12, ge=1, le=52, description="Semanas pasadas con datos reales"),
    weeks_future: int = Query(8,  ge=0, le=52, description="Semanas futuras (bookings + capacity)"),
    user_id:      Optional[str] = Query(None),
    department:   Optional[str] = Query(None),
    p: Periodo = Depends(periodo(dias_por_defecto=84, granularidades=(SEMANA,), alias_dias=())),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    """
    Periodo libre (16-11-2026): con ``desde``/``hasta`` la serie cubre las
    semanas (lunes) de ese intervalo, pasado y futuro a la vez; sin ellos sigue
    valiendo ``weeks_past``/``weeks_future`` como antes. La serie es semanal
    (solo ``granularidad=week``).

    Returns a unified weekly utilization series combining:
    - Past weeks: actual hours from Imputation table (what people really worked)
    - Future weeks: projected hours from ResourceBookings + CapacityPlans

    Response shape:
    {
        weeks: [...],          # ISO week labels "2025-W22"
        team: [{week, actual_pct, planned_pct, is_future}],
        users: [{user_id, user_name, series: [{week, pct, hours, capacity, is_future}]}]
    }
    """
    today = timeutil.today()
    if p.origen == "rango":
        past_start = _monday(p.fecha_desde)
        future_end = _monday(p.fecha_hasta)
    else:
        past_start  = _monday(today) - timedelta(weeks=weeks_past)
        future_end  = _monday(today) + timedelta(weeks=weeks_future)
    periodo_dict = p.a_dict() if p.origen == "rango" else None

    def _t(wk: date) -> str:
        return p.instante_de_clave(wk.strftime("%Y-%m-%dT00:00"))

    # All weeks in range (past + current + future)
    all_weeks: List[date] = []
    w = past_start
    while w <= future_end:
        all_weeks.append(w)
        w += timedelta(weeks=1)

    # Resolve users
    users = get_forecast_active_users(db, department=department, user_id=user_id)

    if not users:
        return APIResponse.ok(data={"weeks": [_week_label(w) for w in all_weeks], "team": [], "users": [],
                                    "periodo": periodo_dict})

    user_ids = [u.id for u in users]

    # ── Past: aggregate actual hours from Imputation per user per week ─────────
    #   We bucket each imputation date into its ISO week (monday).
    #   SQLite/Postgres agnostic: fetch raw rows and group in Python for portability.
    # Fin exclusivo de lo real: hoy (o el domingo de la última semana del periodo si es anterior).
    past_end = min(today, future_end + timedelta(weeks=1))
    past_imputations = get_forecast_past_imputations(db, user_ids, past_start, past_end)

    # {user_id: {week_monday: actual_hours}}
    actual: dict = {}
    for row in past_imputations:
        uid  = row.user_id
        wmon = _monday(row.date)
        if uid not in actual:
            actual[uid] = {}
        actual[uid][wmon] = actual[uid].get(wmon, 0.0) + float(row.hours or 0)

    # ── Build per-user series ──────────────────────────────────────────────────
    user_series = []
    team_by_week: dict = {w: {"actual_h": 0.0, "planned_h": 0.0, "cap_h": 0.0} for w in all_weeks}

    for user in users:
        cap_h = float(capacidad_semanal(db, user))
        series = []
        for wk in all_weeks:
            is_future = wk >= _monday(today)
            cap_w = cap_h
            if is_future:
                fw = _compute_user_week_hours(user.id, wk, db)
                planned_h  = float(fw.get("committed_hours", 0) + fw.get("booking_hours", 0))
                actual_h   = None
                # Rev. 180: la capacidad de la semana sale de su horario efectivo.
                cap_w      = _capacidad(cap_h, fw)
                pct        = round(planned_h / cap_w * 100, 1) if cap_w > 0 else 0
                team_by_week[wk]["planned_h"] += planned_h
            else:
                actual_h   = actual.get(user.id, {}).get(wk, 0.0)
                planned_h  = None
                pct        = round(actual_h / cap_h * 100, 1) if cap_h > 0 else 0
                team_by_week[wk]["actual_h"] += actual_h

            team_by_week[wk]["cap_h"] += cap_w
            series.append({
                "week":      _week_label(wk),
                "pct":       pct,
                "hours":     actual_h if not is_future else planned_h,
                "capacity":  cap_w,
                "is_future": is_future,
            })

        user_series.append({
            "user_id":   user.id,
            "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email,
            "series":    series,
        })

    # ── Team aggregate series ─────────────────────────────────────────────────
    team_series = []
    for wk in all_weeks:
        is_future = wk >= _monday(today)
        cap = team_by_week[wk]["cap_h"]
        if is_future:
            pct = round(team_by_week[wk]["planned_h"] / cap * 100, 1) if cap > 0 else 0
            team_series.append({"week": _week_label(wk), "t": _t(wk), "actual_pct": None, "planned_pct": pct, "is_future": True})
        else:
            pct = round(team_by_week[wk]["actual_h"] / cap * 100, 1) if cap > 0 else 0
            team_series.append({"week": _week_label(wk), "t": _t(wk), "actual_pct": pct, "planned_pct": None, "is_future": False})

    return APIResponse.ok(data={
        "weeks":  [_week_label(w) for w in all_weeks],
        "team":   team_series,
        "users":  user_series,
        "periodo": periodo_dict,
    })
