"""Pasos de una solicitud: los del flujo más los que añade el motor de políticas.

Tarea #26 (rev. 165). Antes cada sitio leía `wf.steps` y buscaba EL paso con
`step_order == current_step`. Ahora:

- `pasos_de(db, req, wf)`: los del flujo y los de la solicitud
  (`ApprovalRequestStep`), ordenados. Los añadidos van DESPUÉS de los del flujo:
  más aprobación es más arriba.
- Una ETAPA son todos los pasos con el mismo `step_order`. Con uno, es lo de
  siempre; con varios, son ramas en paralelo (el diseñador gráfico las crea
  con «dividir en paralelo / unir»): cada rama cuenta sus votos (`step_ref`) y
  la etapa termina cuando todas las ramas activas tienen su quórum.
- `kind = inform`: el paso no se decide; al llegar a él se avisa a sus
  destinatarios y el flujo sigue. Una etapa solo de pasos «informar» no se
  detiene nunca.
- `avanzar(db, req, pasos, desde)`: pasa a la siguiente etapa con algún paso
  activo, avisa a quien toca y dice si queda algo por decidir.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing_reports import ApprovalRequestStep, ApprovalStep

logger = logging.getLogger(__name__)


def pasos_de(db: Session, req, wf=None) -> list:
    """Los pasos del flujo de la solicitud más los suyos, por orden."""
    if wf is not None:
        del_flujo = list(wf.steps or [])
    elif req.workflow_id:
        del_flujo = db.query(ApprovalStep).filter(ApprovalStep.workflow_id == req.workflow_id).all()
    else:
        del_flujo = []
    propios = db.query(ApprovalRequestStep).filter(ApprovalRequestStep.request_id == req.id).all() if req.id else []
    return sorted(del_flujo + propios, key=lambda s: (s.step_order, str(s.id)))


def es_informativo(step) -> bool:
    return (getattr(step, "kind", None) or "approve") == "inform"


def etapa(pasos: list, orden: int) -> list:
    return [s for s in pasos if s.step_order == orden]


def ramas_activas(req, etapa_: list) -> list:
    from app.services.approval_engine.requests import _step_condition_met
    return [s for s in etapa_ if not s.is_optional and _step_condition_met(s, req)]


def votos_de(req, step, etapa_: list) -> list:
    """Votos «approved» de esta rama en la etapa actual.

    En una etapa de un solo paso cuentan también los votos sin `step_ref`
    (los de antes de la rev. 165).
    """
    unica = len(etapa_) == 1
    return [d for d in (req.decisions or [])
            if d.step_order == req.current_step and d.decision == "approved"
            and (getattr(d, "step_ref", None) == step.id or (unica and not getattr(d, "step_ref", None)))]


def rama_satisfecha(req, step, etapa_: list) -> bool:
    necesarios = (step.required_approvals or 1) if step.parallel_quorum else 1
    return len(votos_de(req, step, etapa_)) >= necesarios


def etapa_completa(req, etapa_: list) -> bool:
    return all(rama_satisfecha(req, s, etapa_) for s in ramas_activas(req, etapa_) if not es_informativo(s))


def informar(db: Session, req, step) -> None:
    """Paso «informar»: aviso en la aplicación (y correo si lo quiere) a sus destinatarios."""
    from app.services.approval_engine._base import aprobadores_del_paso, log_financial_approval_event
    from app.services.notifications import notify_user
    ids = sorted(i for i in aprobadores_del_paso(req, step, db) if i)
    titulo = f"Para tu información: {req.entity_type}"
    cuerpo = f"{req.entity_summary or req.entity_id} — {step.name}"
    for uid in ids:
        try:
            notify_user(db, uid, "system", titulo, cuerpo, resource="approval_request", resource_id=req.id,
                        aviso={"titulo": "aviso.aprobacion_informar.titulo",   # 18-11-2026: su idioma
                               "cuerpo": "aviso.aprobacion_informar.cuerpo",
                               "params": {"tipo": req.entity_type, "resumen": req.entity_summary or req.entity_id,
                                          "paso": step.name}})
        except Exception:
            logger.warning("no se pudo informar a %s de la solicitud %s", uid, req.id, exc_info=True)
    log_financial_approval_event(db=db, request_id=req.id, entity_type=req.entity_type, entity_id=req.entity_id,
                                 action="informed", actor_user_id=None, step_order=step.step_order,
                                 note=f"{step.name}: {len(ids)} avisados")


def avanzar(db: Session, req, pasos: list, desde: int) -> bool:
    """Lleva la solicitud a la siguiente etapa que haya que decidir.

    Las etapas solo informativas se avisan y se pasan. Devuelve True si queda
    una etapa pendiente (ya avisada) y False si no queda nada: quien llama
    cierra la solicitud como aprobada.
    """
    from app.services.approval_engine._base import notify_approver
    ordenes = sorted({s.step_order for s in pasos if s.step_order > desde})
    for orden in ordenes:
        activas = ramas_activas(req, etapa(pasos, orden))
        if not activas:
            continue
        for s in activas:
            if es_informativo(s):
                informar(db, req, s)
        decidir = [s for s in activas if not es_informativo(s)]
        if not decidir:
            continue
        req.current_step = orden
        req.step_started_at = datetime.now(timezone.utc)
        req.last_reminder_at = None
        for s in decidir:
            notify_approver(req, s, db)
        return True
    return False


def rama_para(req, etapa_: list, usuario, db: Session):
    """La rama de la etapa actual que decide este usuario: activa, sin su
    quórum y para la que está autorizado. None si no hay ninguna."""
    from app.services.approval_engine._base import _is_authorized
    for s in ramas_activas(req, etapa_):
        if es_informativo(s) or rama_satisfecha(req, s, etapa_):
            continue
        if _is_authorized(s, usuario, req.requested_by, db, req=req):
            return s
    return None


# ── Pasos que añade el motor de políticas ────────────────────────────────────

_CAMPOS_DE_PASO = ("approver_type", "approver_role", "approver_user_id", "approver_department",
                   "approver_group_id", "approver_level", "required_approvals")


def nivel_de_responsable_del_flujo(pasos: list) -> int:
    """Hasta qué nivel de la cadena de responsables llega ya el flujo."""
    n = 0
    for s in pasos:
        if s.approver_type == "manager":
            n = max(n, 1)
        elif s.approver_type == "manager_level":
            n = max(n, int(s.approver_level or 1))
    return n


def anadir_por_politicas(db: Session, req, resultado: dict) -> list:
    """Añade a la solicitud los niveles y pasos que pide el resultado combinado.

    - `niveles = n`: n pasos «responsable de nivel k», a partir del primer
      nivel que el flujo no cubre ya (si el flujo tiene «responsable directo»,
      el primero añadido es el responsable del responsable).
    - `pasos`: los concretos, tal cual.
    Van detrás de los del flujo, uno por etapa. No hace commit.
    """
    pasos = pasos_de(db, req)
    siguiente = (max((s.step_order for s in pasos), default=0)) + 1
    base = nivel_de_responsable_del_flujo(pasos)
    nuevos = []
    origen_niveles = (resultado.get("origenes") or {}).get("niveles") or {}
    for k in range(1, int(resultado.get("niveles") or 0) + 1):
        nivel = base + k
        nuevos.append(ApprovalRequestStep(
            id=str(uuid.uuid4()), organization_id=req.organization_id, request_id=req.id,
            step_order=siguiente, name=f"Responsable nivel {nivel}"[:100], kind="approve",
            approver_type="manager_level", approver_level=nivel, required_approvals=1,
            on_timeout="escalate", origen=_origen(origen_niveles)))
        siguiente += 1
    for p in resultado.get("pasos") or []:
        datos = {k: p.get(k) for k in _CAMPOS_DE_PASO if p.get(k) not in (None, "")}
        quorum = int(datos.pop("required_approvals", 1) or 1)
        nuevos.append(ApprovalRequestStep(
            id=str(uuid.uuid4()), organization_id=req.organization_id, request_id=req.id,
            step_order=siguiente, name=(p.get("nombre") or "Aprobación por política")[:100],
            kind=p.get("kind") or "approve", required_approvals=quorum, parallel_quorum=quorum > 1,
            on_timeout="escalate", origen=_origen(p.get("origen") or {}), **datos))
        siguiente += 1
    for s in nuevos:
        db.add(s)
    db.flush()
    return nuevos


def _origen(o: dict) -> Optional[str]:
    if not o:
        return None
    return f"{o.get('politica') or ''} · {o.get('regla') or ''}"[:300]


def contexto_de(req) -> dict:
    try:
        return json.loads(req.contexto) if getattr(req, "contexto", None) else {}
    except ValueError:
        return {}
