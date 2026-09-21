"""Conflictos de reservas y nivelado de carga en el Gantt.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `v238_service.py`, un
fichero de 784 lineas nombrado por NUMERO DE VERSION y con SEIS dominios sin
relacion dentro: etapas del embudo, planificacion de capacidad, analitica
ad-hoc, pagos, instantaneas de colaboracion y SCIM.

Agrupar por version en lugar de por dominio tiene un coste concreto: nadie sabe
donde buscar, y un fichero con seis dominios no tiene revisor natural — quien
entra a tocar los pagos no revisa la analitica que hay 300 lineas mas abajo. Fue
esa misma mala ubicacion la que oculto el P0 numero 1 de la auditoria, escondido
en un fichero llamado `mfa_service`.

El reparto se pudo hacer mecanicamente porque los seis dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.bookings import ResourceBooking as Booking
from collections import defaultdict


def get_booking_conflicts(
    user_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    threshold_pct: float,
    db: Session,
) -> dict:

    q = db.query(Booking)
    if user_id:
        q = q.filter(Booking.user_id == user_id)
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    bookings = q.all()
    user_bookings: dict = defaultdict(list)
    for b in bookings:
        user_bookings[b.user_id].append(b)

    conflicts = []
    capacity_per_day = settings.DEFAULT_WORKING_HOURS_PER_DAY

    for uid, user_bks in user_bookings.items():
        daily: dict = defaultdict(float)
        for b in user_bks:
            d = b.start_date
            while d <= b.end_date:
                daily[d] += (b.hours_per_day or settings.DEFAULT_WORKING_HOURS_PER_DAY)
                d += timedelta(days=1)

        overloaded_days = [
            {"date": str(d), "hours": round(h, 1), "utilization_pct": round(h / capacity_per_day * 100, 1)}
            for d, h in daily.items()
            if h / capacity_per_day * 100 > threshold_pct
        ]
        if overloaded_days:
            user_obj = db.query(User).filter(User.id == uid).first()
            conflicts.append({
                "user_id": uid,
                "user_name": user_obj.full_name if user_obj else uid,
                "overloaded_days": sorted(overloaded_days, key=lambda x: x["date"]),
                "max_utilization_pct": max(d["utilization_pct"] for d in overloaded_days),
                "bookings_count": len(user_bks),
            })

    return {
        "threshold_pct": threshold_pct,
        "conflicts_count": len(conflicts),
        "conflicts": sorted(conflicts, key=lambda x: x["max_utilization_pct"], reverse=True),
    }


def _dias_de(reserva) -> set:
    """Los días que ocupa una reserva, los dos extremos incluidos."""
    dias = set()
    d = reserva.start_date
    while d <= reserva.end_date:
        dias.add(d)
        d += timedelta(days=1)
    return dias


def _dias_sobrecargados(reservas, capacidad: float) -> set:
    """Días en los que la suma de horas reservadas supera la capacidad diaria.

    Se suma **por día y por persona**: dos reservas de media jornada no
    sobrecargan, dos de jornada completa sí.
    """
    por_dia: dict = defaultdict(float)
    for reserva in reservas:
        horas = reserva.hours_per_day or settings.DEFAULT_WORKING_HOURS_PER_DAY
        for dia in _dias_de(reserva):
            por_dia[dia] += horas
    return {dia for dia, horas in por_dia.items() if horas > capacidad}


def _propuestas_para(reservas, sobrecargados: set, uid, nombre: str) -> list[dict]:
    """Mover cada reserva en conflicto justo después del último día sobrecargado.

    Se conserva la duración: la reserva se desplaza, no se estira. Y se toma el
    último día de conflicto y no el primero, porque mover hasta el primero
    dejaría la reserva pisando los demás.
    """
    propuestas = []
    for reserva in reservas:
        conflictos = _dias_de(reserva) & sobrecargados
        if not conflictos:
            continue
        nuevo_inicio = max(conflictos) + timedelta(days=1)
        duracion = (reserva.end_date - reserva.start_date).days
        propuestas.append({
            "booking_id": reserva.id,
            "user_id": uid,
            "user_name": nombre,
            "project_id": reserva.project_id,
            "current_start": str(reserva.start_date),
            "current_end": str(reserva.end_date),
            "suggested_start": str(nuevo_inicio),
            "suggested_end": str(nuevo_inicio + timedelta(days=duracion)),
            "conflict_days_count": len(conflictos),
            "reason": f"Resource overloaded on {len(conflictos)} day(s)",
        })
    return propuestas


def get_gantt_leveling(
    project_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    db: Session,
) -> dict:
    """Propuestas de nivelación: qué reservas mover para quitar sobrecargas.

    **No cambia nada**: devuelve propuestas para que alguien decida.
    """
    q = db.query(Booking)
    if project_id:
        q = q.filter(Booking.project_id == project_id)
    # Solape con el periodo, no contención: una reserva que empieza antes y
    # acaba dentro también carga días del periodo.
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    por_usuario: dict = defaultdict(list)
    for reserva in q.order_by(Booking.start_date).all():
        por_usuario[reserva.user_id].append(reserva)

    capacidad = settings.DEFAULT_WORKING_HOURS_PER_DAY
    propuestas: list[dict] = []
    for uid, reservas in por_usuario.items():
        reservas = sorted(reservas, key=lambda r: r.start_date)
        sobrecargados = _dias_sobrecargados(reservas, capacidad)
        if not sobrecargados:
            continue
        usuario = db.query(User).filter(User.id == uid).first()
        propuestas += _propuestas_para(
            reservas, sobrecargados, uid, usuario.full_name if usuario else uid,
        )

    return {
        "analysis_period": {
            "start": str(start_date or "all"),
            "end": str(end_date or "all"),
        },
        "overloaded_users": len({p["user_id"] for p in propuestas}),
        "proposals_count": len(propuestas),
        "proposals": propuestas,
    }
