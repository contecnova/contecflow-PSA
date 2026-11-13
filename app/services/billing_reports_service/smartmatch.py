"""SmartMatch: puntuacion de candidatos por habilidades y disponibilidad.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.models.task import ESTADOS_DE_TAREA_TERMINADOS
from app.core.config import settings
from app.models.user import User
from app.models.task import Task
from app.models.resources import UserSkill
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# SMARTMATCH
# ═══════════════════════════════════════════════════════════════════════════════

#: Nivel de habilidad a número, para poder promediarlos.
_NIVEL_A_NUMERO = {"basic": 1, "intermediate": 2, "advanced": 3, "expert": 4}

#: Peso de cada factor en la puntuación final. Suman 1, y el orden dice la
#: prioridad del negocio: la habilidad manda, el coste desempata.
#:
#: Auditoría 2026-09 (hallazgo 18): estos cuatro números estaban en línea, en
#: una sola expresión. Aquí se pueden discutir sin leer el algoritmo.
_PESOS_DE_SMARTMATCH = {
    "skills": 0.4, "availability": 0.3, "workload": 0.2, "cost": 0.1,
}

#: Corte de puntuación → recomendación, de mejor a peor. Gana el primero que
#: alcance.
_RECOMENDACIONES_SMARTMATCH = (
    (0.75, "🟢 Excelente"),
    (0.50, "🟡 Buena opción"),
    (0.25, "🟠 Posible"),
    (0.00, "🔴 No recomendado"),
)


def _nivel_numerico(valor) -> int:
    """El nivel de una habilidad como número, venga como entero, enum o texto."""
    if isinstance(valor, int):
        return valor
    if hasattr(valor, "value"):
        return _NIVEL_A_NUMERO.get(valor.value, 1)
    return _NIVEL_A_NUMERO.get(str(valor), 1)


def _semanas_del_periodo(start_date, end_date) -> float:
    """Cuántas semanas cubre el periodo pedido. Dos por defecto.

    El suelo de media semana evita que un periodo de un día dé una
    disponibilidad casi nula y descarte a todo el mundo.
    """
    if not (start_date and end_date):
        return 2.0
    try:
        d1 = date.fromisoformat(start_date)
        d2 = date.fromisoformat(end_date)
    except ValueError:
        raise ErrorDeDominio(
            400, "Formato de fecha inválido en start_date/end_date, se espera YYYY-MM-DD",
        )
    return max((d2 - d1).days / 7, 0.5)


def _mapas_de_habilidades(db: Session) -> tuple[dict, dict]:
    """Habilidades por usuario y nivel de cada par (usuario, habilidad).

    Se cargan de una vez para todos los usuarios: preguntando por usuario, una
    plantilla de cien personas son cien consultas para puntuar una búsqueda.
    """
    por_usuario: dict = {}
    niveles: dict = {}
    for us in db.query(UserSkill).options(joinedload(UserSkill.skill)).all():
        if not us.skill:
            continue
        nombre = us.skill.name.lower()
        por_usuario.setdefault(us.user_id, []).append(nombre)
        niveles[(us.user_id, nombre)] = us.level
    return por_usuario, niveles


def _puntuar_candidato(user, *, habilidades_pedidas: list, sus_habilidades: list,
                       niveles: dict, tareas_activas: int, semanas: float,
                       horas_necesarias: float) -> dict:
    """Puntúa a una persona para un encargo, con los cuatro factores."""
    coincidentes = [h for h in habilidades_pedidas if h in sus_habilidades]
    p_habilidad = (
        len(coincidentes) / max(len(habilidades_pedidas), 1) if habilidades_pedidas else 1.0
    )
    nivel_medio = (
        sum(_nivel_numerico(niveles.get((user.id, h), 1)) for h in coincidentes)
        / max(len(coincidentes), 1)
    ) if coincidentes else 1.0

    capacidad = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    disponibles = capacidad * semanas
    p_disponibilidad = min(disponibles / max(horas_necesarias, 1), 1.0)

    tarifa = user.hourly_rate or 0
    # Sin tarifa declarada se puntúa como la mejor: es un recurso interno sin
    # coste imputable, no uno gratis.
    p_coste = 1.0 if tarifa == 0 else min(1.0, 1 - (tarifa / 200))
    # Veinte tareas activas es la saturación: a partir de ahí no suma nada.
    p_carga = max(0, 1 - tareas_activas / 20)

    total = (
        p_habilidad * _PESOS_DE_SMARTMATCH["skills"]
        + p_disponibilidad * _PESOS_DE_SMARTMATCH["availability"]
        + p_carga * _PESOS_DE_SMARTMATCH["workload"]
        + p_coste * _PESOS_DE_SMARTMATCH["cost"]
    )

    return {
        "user_id": user.id,
        "user_name": user.full_name,
        "role": user.role,
        "department": user.department,
        "job_title": user.job_title,
        "hourly_rate": tarifa,
        "weekly_capacity": capacidad,
        "active_tasks": tareas_activas,
        "matched_skills": coincidentes,
        "missing_skills": [h for h in habilidades_pedidas if h not in sus_habilidades],
        "avg_skill_level": round(nivel_medio, 1),
        "availability_hours": round(disponibles, 1),
        "scores": {
            "overall": round(total * 100, 1),
            "skills": round(p_habilidad * 100, 1),
            "availability": round(p_disponibilidad * 100, 1),
            "workload": round(p_carga * 100, 1),
            "cost": round(p_coste * 100, 1),
        },
        "recommendation": next(
            texto for corte, texto in _RECOMENDACIONES_SMARTMATCH if total > corte or corte == 0.0
        ),
    }


def smartmatch(payload: dict, db: Session) -> dict:
    """Recomienda personas para un encargo: habilidad, disponibilidad, coste y carga."""
    habilidades_pedidas = [h.lower() for h in payload.get("skills", [])]
    rol = payload.get("role")
    horas_necesarias = payload.get("hours_needed", 40)
    tarifa_maxima = payload.get("max_hourly_rate")
    semanas = _semanas_del_periodo(payload.get("start_date"), payload.get("end_date"))

    usuarios_q = db.query(User).options(
        joinedload(User.task_assignments),
    ).filter(User.is_active == True)  # noqa: E712
    if rol:
        usuarios_q = usuarios_q.filter(User.role == rol)

    por_usuario, niveles = _mapas_de_habilidades(db)
    tareas_por_usuario = {
        fila.assignee_id: fila.count
        for fila in db.query(Task.assignee_id, func.count(Task.id).label("count"))
        .filter(Task.status.notin_(ESTADOS_DE_TAREA_TERMINADOS))
        .group_by(Task.assignee_id).all()
    }

    resultados = [
        _puntuar_candidato(
            user,
            habilidades_pedidas=habilidades_pedidas,
            sus_habilidades=por_usuario.get(user.id, []),
            niveles=niveles,
            tareas_activas=tareas_por_usuario.get(user.id, 0),
            semanas=semanas,
            horas_necesarias=horas_necesarias,
        )
        for user in usuarios_q.all()
        # La tarifa máxima descarta, no penaliza: es un límite de presupuesto.
        if not (tarifa_maxima and (user.hourly_rate or 0) > tarifa_maxima)
    ]
    resultados.sort(key=lambda r: -r["scores"]["overall"])
    top = resultados[:5]

    return {
        "query": {
            "skills": payload.get("skills", []), "role": rol,
            "hours_needed": horas_necesarias,
            "start_date": payload.get("start_date"), "end_date": payload.get("end_date"),
        },
        "candidates": top,
        "total_evaluated": len(resultados),
        "message": (
            f"Se evaluaron {len(resultados)} recursos. Top {len(top)} recomendados."
            if resultados else "No se encontraron recursos con los criterios indicados."
        ),
    }
