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

18-11-2026: la jornada (capacidad diaria y horas de una reserva sin
`hours_per_day`) es la de la empresa de la reserva (`jornada_de_empresa`), no
`settings.DEFAULT_WORKING_HOURS_PER_DAY` global.
"""

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.services.settings_service.por_empresa import jornada_de_empresa
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

    for uid, user_bks in user_bookings.items():
        capacity_per_day = jornada_de_empresa(db, registro=user_bks[0])
        capacidad = _capacidad_por_dia(db, uid, user_bks, capacity_per_day)
        daily: dict = defaultdict(float)
        for b in user_bks:
            d = b.start_date
            while d <= b.end_date:
                # M35 (auditoría 22-11-2026): solo días que la persona trabaja
                # (su horario: sin fines de semana, festivos ni ausencias).
                if capacidad.get(d, 0) > 0:
                    daily[d] += (b.hours_per_day or capacidad[d])
                d += timedelta(days=1)

        overloaded_days = [
            {"date": str(d), "hours": round(h, 1), "utilization_pct": round(h / capacidad[d] * 100, 1)}
            for d, h in daily.items()
            if capacidad.get(d) and h / capacidad[d] * 100 > threshold_pct
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


def _capacidad_por_dia(db: Session, uid, reservas, defecto: float) -> dict:
    """{día: horas disponibles} de la persona en el rango de sus reservas, por su
    horario efectivo (horario, festivos de empresa y sede, contrato, ausencias).
    M35: antes contaban sábados, domingos y festivos y se dividía por la jornada."""
    from app.services.horario import efectivo as hor
    desde = min(r.start_date for r in reservas)
    hasta = max(r.end_date for r in reservas)
    dias = (hor.horarios(db, [uid], desde, hasta) or {}).get(uid, {})
    if not dias:   # sin horario calculable: lunes a viernes con la jornada de la empresa
        salida, d = {}, desde
        while d <= hasta:
            salida[d] = defecto if d.weekday() < 5 else 0.0
            d += timedelta(days=1)
        return salida
    return {d: float(x.horas or 0) for d, x in dias.items()}


def _dias_de(reserva) -> set:
    """Los días que ocupa una reserva, los dos extremos incluidos."""
    dias = set()
    d = reserva.start_date
    while d <= reserva.end_date:
        dias.add(d)
        d += timedelta(days=1)
    return dias


def _dias_sobrecargados(reservas, capacidad, por_dia_cap: dict | None = None) -> set:
    """Días en los que la suma de horas reservadas supera la capacidad diaria.

    Se suma **por día y por persona**: dos reservas de media jornada no
    sobrecargan, dos de jornada completa sí.
    """
    por_dia: dict = defaultdict(float)
    cap = (lambda d: por_dia_cap.get(d, 0.0)) if por_dia_cap is not None else (lambda d: capacidad)
    for reserva in reservas:
        for dia in _dias_de(reserva):
            if cap(dia) > 0:
                por_dia[dia] += reserva.hours_per_day or cap(dia)
    return {dia for dia, horas in por_dia.items() if horas > cap(dia)}


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
        # M35: el hueco propuesto no puede pisar OTRAS reservas de la persona (antes
        # la propuesta podía crear otra sobrecarga): se avanza hasta un tramo libre.
        otras = [r for r in reservas if r is not reserva]
        for _ in range(366):
            fin = nuevo_inicio + timedelta(days=duracion)
            pisa = [r for r in otras if r.start_date <= fin and r.end_date >= nuevo_inicio]
            if not pisa:
                break
            nuevo_inicio = max(r.end_date for r in pisa) + timedelta(days=1)
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

    propuestas: list[dict] = []
    for uid, reservas in por_usuario.items():
        reservas = sorted(reservas, key=lambda r: r.start_date)
        capacidad = jornada_de_empresa(db, registro=reservas[0])
        sobrecargados = _dias_sobrecargados(reservas, capacidad,
                                            _capacidad_por_dia(db, uid, reservas, capacidad))
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
