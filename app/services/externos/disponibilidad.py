"""Disponibilidad de un externo: su ventana de contrato y sus horas contratadas.

Un interno no tiene ventana (`ventana` devuelve None): su capacidad es la de
siempre. Un externo (usuario enlazado a un `SubcontractorWorker` activo) solo
esta disponible entre `available_from` y `available_until` y, si sus
asignaciones vigentes tienen horas contratadas, hasta agotarlas.

Lo usan reservas (`bookings_service.reservas.comprobar_capacidad`), carga del
planificador, nivelacion, SmartMatch y prevision de capacidad: todos preguntan
aqui y nadie lee las columnas del trabajador por su cuenta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio


@dataclass(frozen=True)
class Ventana:
    desde: Optional[date]
    hasta: Optional[date]
    #: Horas contratadas que quedan en sus asignaciones vigentes; None = sin tope.
    horas_restantes: Optional[float]

    def contiene(self, dia: date) -> bool:
        return not ((self.desde and dia < self.desde) or (self.hasta and dia > self.hasta))

    def dias_dentro(self, inicio: date, fin: date) -> tuple[Optional[date], Optional[date]]:
        """El tramo de [inicio, fin] dentro de la ventana; (None, None) si no hay."""
        a = max(inicio, self.desde) if self.desde else inicio
        b = min(fin, self.hasta) if self.hasta else fin
        return (a, b) if a <= b else (None, None)


def _horas_restantes(asignaciones) -> Optional[float]:
    contratadas = [a for a in asignaciones if a.hours_contracted]
    if not contratadas:
        return None
    return max(0.0, sum((a.hours_contracted or 0) - (a.hours_logged or 0) for a in contratadas))


def ventanas(db: Session, user_ids: Iterable[str]) -> dict[str, Ventana]:
    """{user_id: Ventana} de los externos de la lista (los internos no salen)."""
    from app.models.enterprise import SubcontractorAssignment, SubcontractorWorker
    ids = [u for u in set(user_ids) if u]
    if not ids:
        return {}
    trabajadores = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.user_id.in_(ids), SubcontractorWorker.is_active == True,  # noqa: E712
    ).all()
    if not trabajadores:
        return {}
    por_trabajador: dict[str, list] = {}
    for a in db.query(SubcontractorAssignment).filter(
        SubcontractorAssignment.worker_id.in_([w.id for w in trabajadores]),
        SubcontractorAssignment.is_active == True,  # noqa: E712
    ).all():
        por_trabajador.setdefault(a.worker_id, []).append(a)
    return {w.user_id: Ventana(w.available_from, w.available_until, _horas_restantes(por_trabajador.get(w.id, [])))
            for w in trabajadores}


def ventana(db: Session, user_id: Optional[str]) -> Optional[Ventana]:
    """La ventana del externo `user_id`; None si es interno (sin limite propio)."""
    return ventanas(db, [user_id]).get(user_id) if user_id else None


def capacidad_en_dia(v: Optional[Ventana], dia: date, capacidad: float) -> float:
    """La capacidad del dia: la normal, o 0 fuera de la ventana del externo."""
    if v is None or v.contiene(dia):
        return capacidad
    return 0.0


def fraccion_de_semana(v: Optional[Ventana], lunes: date) -> float:
    """Que parte (0..1) de los dias laborables de la semana cae en la ventana."""
    if v is None:
        return 1.0
    from datetime import timedelta
    laborables = [lunes + timedelta(days=i) for i in range(5)]
    return sum(1 for d in laborables if v.contiene(d)) / 5.0


def horas_disponibles(v: Optional[Ventana], inicio: date, fin: date, capacidad_semanal: float,
                      horas_por_dia: Optional[dict] = None) -> Optional[float]:
    """Horas que puede dar en [inicio, fin]: capacidad en su ventana, con tope de
    horas contratadas. None si es interno (lo decide quien llama).

    19-11-2026: `horas_por_dia` ({fecha: horas}) es su horario efectivo
    (`horario.efectivo`: su jornada o turno, festivos, ausencias); con él se
    suman esas horas. Sin él, el calculo de antes: L-V × capacidad/5.
    """
    if v is None:
        return None
    a, b = v.dias_dentro(inicio, fin)
    if a is None:
        return 0.0
    from datetime import timedelta
    if horas_por_dia is not None:
        horas = sum(horas_por_dia.get(a + timedelta(days=i), 0.0) for i in range((b - a).days + 1))
    else:
        laborables = sum(1 for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)
        horas = capacidad_semanal / 5.0 * laborables
    if v.horas_restantes is not None:
        horas = min(horas, v.horas_restantes)
    return round(horas, 2)


def comprobar_reserva(db: Session, user_id: str, inicio: date, fin: date, horas: float) -> None:
    """Rechaza (400) reservar a un externo fuera de su ventana o por encima de
    sus horas contratadas restantes. Para un interno no hace nada."""
    v = ventana(db, user_id)
    if v is None:
        return
    if (v.desde and inicio < v.desde) or (v.hasta and fin > v.hasta):
        raise ErrorDeDominio(
            400,
            f"El externo solo está disponible del {v.desde or '—'} al {v.hasta or '—'}.",
            code="externo_fuera_de_ventana",
            params={"desde": str(v.desde or ""), "hasta": str(v.hasta or "")},
        )
    if v.horas_restantes is not None and horas > v.horas_restantes + 1e-6:
        raise ErrorDeDominio(
            400,
            f"Supera las horas contratadas que le quedan al externo ({round(v.horas_restantes, 1)} h).",
            code="externo_sin_horas_contratadas",
            params={"horas": round(v.horas_restantes, 1)},
        )
