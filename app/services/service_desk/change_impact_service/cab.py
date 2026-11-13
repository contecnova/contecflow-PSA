"""Panel del CAB y puntuacion (persistida) de los cambios pendientes.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from app.core.config import settings as _settings
from sqlalchemy.orm import Session
from app.models.service_desk import ChangeStatus as _ChangeStatus
from app.models.service_desk import ITSMChangeRequest, ChangeRisk

from app.services.service_desk.change_impact_service.riesgo import (
    generate_impact_report,
    logger,
    score_change_risk,
    suggest_maintenance_window,
)


# ── Persist scoring back to the Change Request ────────────────────────────────

#: Los estados en los que un cambio esta esperando decision del CAB.
#:
#: Auditoria 2026-08 (hallazgo 22). Esto era `["submitted", "in_approval"]`, y
#: **`in_approval` no existe en el enum del modelo**. Hay DOS enums llamados
#: `ChangeStatus` en el repositorio:
#:
#:   · `app/models/service_desk/_enums.py` -> draft, submitted, **cab_review**,
#:     approved, scheduled, in_progress, implemented, post_review,
#:     closed_success, closed_failed, cancelled. Es el que usa la **columna**.
#:   · `app/services/service_desk/change_management_service.py` -> draft,
#:     submitted, **in_approval**, approved, ... Un enum local del servicio, y
#:     **no lo usaba nadie**: las funciones de su propio modulo importan el del
#:     modelo. Era el unico sitio donde `in_approval` existia.
#:
#: Tres consumidores importaban el del modelo y escribian
#: `ChangeStatus.in_approval`. Medido:
#:
#:   1. **`POST /sd/changes/batch-score`**: la referencia era incondicional, asi
#:      que el endpoint respondia **500 siempre** —`AttributeError: type object
#:      'ChangeStatus' has no attribute 'in_approval'`— y **nunca puntuo un solo
#:      cambio**. La escritura cruzada entre clientes que tenia dentro nunca fue
#:      alcanzable: reventaba antes de llegar a la consulta.
#:   2. **`GET /sd/changes/cab-dashboard`**: el valor por defecto del parametro
#:      era `"submitted,in_approval"`, y `in_approval` se caia del filtro por no
#:      estar en el enum. El panel del CAB listaba **solo `submitted`** y no
#:      mostraba **ninguno** de los cambios que estan de verdad en revision del
#:      CAB, que es `cab_review`. Y si el cliente mandaba un estado inexistente
#:      se llegaba a la rama de respaldo y respondia 500.
#:   3. **La tarea de Celery `change_impact_batch_score`**, cada 10 minutos:
#:      mismo `AttributeError`, atrapado por su `except` exterior, que dejaba una
#:      linea de log y devolvia. **La pasada programada de scoring llevaba
#:      fallando en cada tic**, asi que `auto_risk_score` solo se rellenaba en la
#:      transicion a `submitted` (`change_service.py`) y la auto-aprobacion de
#:      cambios estandar de bajo riesgo no se ejecutaba nunca.
#:
#: Ahora la constante sale del enum, asi que un renombrado revienta aqui y no
#: en un `AttributeError` a mitad de una peticion.
ESTADOS_PENDIENTES_DE_CAB = [
    _ChangeStatus.submitted.value,
    _ChangeStatus.cab_review.value,
]

#: Cuantos cambios puntua como maximo una pasada de `/batch-score`.
#:
#: Auditoria 2026-08 (hallazgo 22). El endpoint cargaba **todos** los cambios
#: pendientes sin puntuar, sin tope, y por cada uno hacia un `score_and_persist`
#: —que consulta elementos de configuracion, sus dependencias, los tickets
#: abiertos sobre ellos y el historial de incidencias— **y un `commit`**. Sin
#: tope, una cola acumulada convierte una peticion HTTP en un trabajo de lote de
#: duracion desconocida.
TOPE_DE_CAMBIOS_POR_PASADA = int(_settings.CHANGE_BATCH_SCORE_MAX)


def _cambios_de_la_organizacion(db: Session, current_user):
    """La consulta base de cambios, acotada de forma EXPLICITA.

    Un superadmin no filtra. Un sujeto sin organizacion ve los cambios sin
    organizacion, no los de todos: el filtro no es condicional.
    """
    from app.models.service_desk import ITSMChangeRequest

    q = db.query(ITSMChangeRequest)
    if getattr(current_user, "is_superadmin", False):
        return q
    return q.filter(
        ITSMChangeRequest.organization_id
        == getattr(current_user, "organization_id", None))


def panel_del_cab(
    db: Session,
    current_user,
    *,
    estados: list[str],
    min_risk_score: int,
    page: int,
    page_size: int,
) -> dict:
    """Los cambios pendientes de decision, ordenados por riesgo."""
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import serialize_change

    q = _cambios_de_la_organizacion(db, current_user).filter(
        ITSMChangeRequest.status.in_(estados))
    if min_risk_score > 0:
        q = q.filter(
            (ITSMChangeRequest.auto_risk_score >= min_risk_score)
            | ITSMChangeRequest.auto_risk_score.is_(None)
        )

    total = q.count()
    cambios = (
        q.order_by(ITSMChangeRequest.auto_risk_score.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "unscored": sum(1 for c in cambios if c.auto_risk_score is None),
        "items": [serialize_change(c) for c in cambios],
    }


def puntuar_cambios_pendientes(db: Session, current_user) -> dict:
    """Puntua los cambios pendientes sin score y auto-aprueba los de bajo riesgo.

    Auditoria 2026-08 (hallazgo 22). Aqui habia dos cosas, y la segunda es
    grave:

    1. **Sin tope.** Ver el comentario de `TOPE_DE_CAMBIOS_POR_PASADA`.
    2. **Sin filtro de organizacion, y esto ESCRIBE.** Un administrador de un
       cliente que llamara a `/batch-score` puntuaba y **auto-aprobaba las
       solicitudes de cambio de todos los demas**. No es una lectura de mas: es
       aprobar un cambio en la infraestructura de otro cliente, y queda firmado
       con el id de quien lanzo la pasada. En produccion el filtro implicito de
       `TenantSession` lo evitaba, pero era la unica capa y esto es una
       escritura, no una lectura.

    El `except Exception` que cuenta errores viene del original y se conserva
    —una pasada no debe abortar por un cambio que falla—, pero ahora el fallo
    se registra con el id del cambio en vez de perderse.
    """
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import _maybe_auto_approve

    consulta = _cambios_de_la_organizacion(db, current_user).filter(
        ITSMChangeRequest.status.in_(ESTADOS_PENDIENTES_DE_CAB),
        ITSMChangeRequest.auto_risk_score.is_(None),
    )
    total_pendientes = consulta.count()
    pendientes = consulta.limit(TOPE_DE_CAMBIOS_POR_PASADA).all()

    puntuados = auto_aprobados = errores = 0
    for cambio in pendientes:
        try:
            score_and_persist(db, cambio.id)
            if _maybe_auto_approve(
                    db, cambio, system_user_id=str(current_user.id)):
                auto_aprobados += 1
            db.commit()
            puntuados += 1
        except Exception:
            db.rollback()
            errores += 1
            logger.warning(
                "batch-score: fallo al puntuar el cambio %s", cambio.id,
                exc_info=True)

    return {
        "ok": True,
        # Se conserva el nombre y el significado: cuantos habia pendientes.
        "total_pending": total_pendientes,
        "scored": puntuados,
        "auto_approved": auto_aprobados,
        "errors": errores,
        "truncated": total_pendientes > len(pendientes),
    }


def score_and_persist(db: Session, change_id: str) -> dict:
    """Compute risk score + impact report and write back to the Change Request.

    Writes:
      - change.auto_risk_score      (int)
      - change.impact_analysis_json (JSON string)
      - change.suggested_window_json (JSON string)

    Only writes to columns that exist on the model (defensive).
    Does NOT commit — caller must commit.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        return {"error": f"Change {change_id} not found"}

    report = generate_impact_report(db, change_id)
    risk_data = score_change_risk(db, change)
    window = suggest_maintenance_window(db, change, risk_data["ci_ids_expanded"])

    if hasattr(change, "auto_risk_score"):
        change.auto_risk_score = risk_data["score"]
    if hasattr(change, "impact_analysis_json"):
        change.impact_analysis_json = json.dumps(report)
    if hasattr(change, "suggested_window_json"):
        change.suggested_window_json = json.dumps(window)

    # Also upgrade the risk field if auto score is higher than current
    risk_labels = {
        ChangeRisk.low: 1,
        ChangeRisk.medium: 2,
        ChangeRisk.high: 3,
        ChangeRisk.critical: 4,
    }
    auto_label_map = {"low": ChangeRisk.low, "medium": ChangeRisk.medium,
                      "high": ChangeRisk.high, "critical": ChangeRisk.critical}
    auto_risk_enum = auto_label_map.get(risk_data["risk_label"], ChangeRisk.medium)

    current_rank = risk_labels.get(change.risk, 2)
    auto_rank = risk_labels.get(auto_risk_enum, 2)
    if auto_rank > current_rank:
        change.risk = auto_risk_enum

    db.flush()

    logger.info(
        "Change %s risk scored: %d/100 (%s)",
        change.number,
        risk_data["score"],
        risk_data["risk_label"],
    )

    return report
