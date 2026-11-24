"""BPM: metricas de ejecucion y RGPD de las instancias (docs/BPM.md, «Métricas» y «GRC»).

Revision BPM 2026-11-23.

- `metricas`: instancias por estado, duracion (media, p50, p90), cuellos de
  botella (pasos humanos con mas espera media), instancias atascadas (en curso
  con un paso pendiente desde hace mas de `BPMN_STUCK_HOURS`, o con un
  incidente) y tareas fuera de plazo. Sin N+1: tres consultas acotadas.
- `copia` / `suprimir`: lo de una persona en las instancias (acceso art. 15,
  portabilidad art. 20 y supresion art. 17). Las engancha
  `cab_service/gdpr.py` y `supresion_service.suprimir_persona`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bpmn_process import BPMNInstance, BPMNInstanceStep, BPMNProcess

#: Lo que sustituye a un dato personal suprimido (el mismo marcador que `supresion_service`).
SUPRIMIDO = "[ERASED]"
_MAX_FILAS = 5000


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _percentil(valores: list[float], p: float) -> Optional[float]:
    if not valores:
        return None
    orden = sorted(valores)
    k = max(0, min(len(orden) - 1, int(round(p * (len(orden) - 1)))))
    return round(orden[k], 2)


def metricas(db: Session, user, process_id: Optional[str] = None, dias: int = 30) -> dict:
    from app.services.bpmn_engine import ESPERA_INCIDENTE, ESPERAS_HUMANAS, _de_la_organizacion
    from app.services.settings_service import get_runtime_int

    desde = _ahora() - timedelta(days=max(1, min(dias, 365)))
    base = _de_la_organizacion(db.query(BPMNInstance), BPMNInstance, user)
    if process_id:
        base = base.filter(BPMNInstance.process_id == process_id)

    por_estado = dict(base.with_entities(BPMNInstance.status, func.count(BPMNInstance.id))
                      .filter(BPMNInstance.started_at >= desde).group_by(BPMNInstance.status).all())

    terminadas = (base.with_entities(BPMNInstance.started_at, BPMNInstance.ended_at)
                  .filter(BPMNInstance.status == "completed", BPMNInstance.ended_at >= desde)
                  .limit(_MAX_FILAS).all())
    horas = [(_aware(f) - _aware(i)).total_seconds() / 3600 for i, f in terminadas if i and f]

    pasos = (_de_la_organizacion(db.query(BPMNInstanceStep.element_id, BPMNInstanceStep.name,
                                          BPMNInstanceStep.created_at, BPMNInstanceStep.completed_at),
                                 BPMNInstanceStep, user)
             .join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
             .filter(BPMNInstanceStep.status == "completed", BPMNInstanceStep.completed_at >= desde,
                     BPMNInstanceStep.wait_kind.in_(ESPERAS_HUMANAS | {"approval", "message", "timer"})))
    if process_id:
        pasos = pasos.filter(BPMNInstance.process_id == process_id)
    espera: dict[tuple, list] = {}
    for eid, nombre, ini, fin in pasos.limit(_MAX_FILAS).all():
        if ini and fin:
            espera.setdefault((eid, nombre), []).append((_aware(fin) - _aware(ini)).total_seconds() / 3600)
    cuellos = sorted(({"element_id": e, "name": n, "count": len(v), "avg_hours": round(sum(v) / len(v), 2),
                       "p90_hours": _percentil(v, 0.9)} for (e, n), v in espera.items()),
                     key=lambda x: x["avg_hours"], reverse=True)[:10]

    umbral = get_runtime_int(db, "BPMN_STUCK_HOURS", getattr(user, "organization_id", None)) or 72
    limite = _ahora() - timedelta(hours=umbral)
    activos = (_de_la_organizacion(db.query(BPMNInstanceStep), BPMNInstanceStep, user)
               .join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
               .filter(BPMNInstanceStep.status == "active", BPMNInstance.status == "running"))
    if process_id:
        activos = activos.filter(BPMNInstance.process_id == process_id)
    atascadas: dict[str, dict] = {}
    fuera_de_plazo = 0
    for p in activos.limit(_MAX_FILAS).all():
        vencida = p.sla_due_at is not None and _aware(p.sla_due_at) <= _ahora()
        fuera_de_plazo += 1 if vencida else 0
        motivo = "incident" if p.wait_kind == ESPERA_INCIDENTE else ("overdue" if vencida else (
            "waiting" if p.created_at and _aware(p.created_at) <= limite and p.wait_kind != "timer" else None))
        if motivo and p.instance_id not in atascadas:
            atascadas[p.instance_id] = {"instance_id": p.instance_id, "step": p.name or p.element_id,
                                        "since": p.created_at.isoformat() if p.created_at else None,
                                        "reason": motivo}
    lista = list(atascadas.values())[:50]
    if lista:
        filas = dict(db.query(BPMNInstance.id, BPMNInstance.process_id)
                     .filter(BPMNInstance.id.in_([a["instance_id"] for a in lista])).all())
        nombres = dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(BPMNProcess.id.in_(set(filas.values()))).all())
        for a in lista:
            a["process_name"] = nombres.get(filas.get(a["instance_id"]))
    return {
        "days": dias, "by_status": por_estado, "started": sum(por_estado.values()),
        "duration_hours": {"count": len(horas), "avg": round(sum(horas) / len(horas), 2) if horas else None,
                           "p50": round(median(horas), 2) if horas else None, "p90": _percentil(horas, 0.9)},
        "bottlenecks": cuellos, "stuck": lista, "stuck_count": len(atascadas), "overdue_tasks": fuera_de_plazo,
        "stuck_hours": umbral,
    }


# ── RGPD ─────────────────────────────────────────────────────────────────────

def _personales(db: Session, process_ids: set) -> dict[str, set]:
    """Variables marcadas como dato personal, por proceso (`variables_schema`)."""
    from app.services.bpmn_engine import esquema
    out: dict[str, set] = {}
    for pid, texto in db.query(BPMNProcess.id, BPMNProcess.variables_schema).filter(
            BPMNProcess.id.in_(process_ids or {""})).all():
        out[pid] = {c["name"] for c in esquema(texto) if c.get("personal")}
    return out


def copia(db: Session, user_id: str) -> dict:
    """Las instancias que arranco y los pasos que completo, con lo que aporto."""
    from app.services.bpmn_engine import _json
    propias = db.query(BPMNInstance).filter(BPMNInstance.started_by_user_id == user_id) \
        .order_by(BPMNInstance.started_at).limit(_MAX_FILAS).all()
    pasos = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.completed_by_user_id == user_id) \
        .order_by(BPMNInstanceStep.completed_at).limit(_MAX_FILAS).all()
    nombres = dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(
        BPMNProcess.id.in_({i.process_id for i in propias} or {""})).all())
    return {
        "bpm_instances": [{"process": nombres.get(i.process_id), "status": i.status, "business_key": i.business_key,
                           "started_at": str(i.started_at)[:19] if i.started_at else None,
                           "ended_at": str(i.ended_at)[:19] if i.ended_at else None,
                           "variables": _json(i.variables)} for i in propias],
        "bpm_steps": [{"step": s.name or s.element_id, "instance_id": s.instance_id,
                       "completed_at": str(s.completed_at)[:19] if s.completed_at else None,
                       "contributed": _json(s.result)} for s in pasos],
    }


def suprimir(db: Session, user, valores: Optional[set] = None) -> dict:
    """Tacha sus datos personales en las instancias. No hace commit.

    - En las instancias que arranco: las variables marcadas `personal`.
    - En cualquier instancia de sus empresas: las variables (y lo aportado en
      los pasos) cuyo valor es su correo, nombre, usuario o id.
    - Las instancias bajo bloqueo legal (tipo `bpmn_instances`) no se tocan.
    Quien arranco o completo un paso se queda en NULL al borrar la persona
    (claves ajenas `SET NULL`); aqui solo se tachan los datos.
    """
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    from app.services.bpmn_engine import _json
    identidad = {str(v).strip().lower() for v in (valores or {user.id, user.email, user.full_name, user.username})
                 if v and len(str(v).strip()) >= 3}
    informe = {"instances": 0, "steps": 0, "held": 0}
    bloqueos: dict = {}

    def tachar(datos: dict, nombres: set) -> bool:
        cambio = False
        for k, v in list(datos.items()):
            if k in nombres or (isinstance(v, str) and v.strip().lower() in identidad):
                if v != SUPRIMIDO:
                    datos[k] = SUPRIMIDO
                    cambio = True
        return cambio

    candidatas = db.query(BPMNInstance).filter(
        (BPMNInstance.started_by_user_id == user.id) | BPMNInstance.variables.isnot(None)).limit(_MAX_FILAS * 4).all()
    personales = _personales(db, {i.process_id for i in candidatas})
    retenidas = set()
    for inst in candidatas:
        org = inst.organization_id
        if org not in bloqueos:
            bloqueos[org] = bloqueos_activos(db, org)
        if _bloqueo_de("bpmn_instances", inst, bloqueos[org]) is not None:
            retenidas.add(inst.id)
            continue
        datos = _json(inst.variables)
        nombres = personales.get(inst.process_id, set()) if inst.started_by_user_id == user.id else set()
        if tachar(datos, nombres):
            inst.variables = json.dumps(datos, default=str)
            informe["instances"] += 1
    informe["held"] = len(retenidas)
    for paso in db.query(BPMNInstanceStep).filter(BPMNInstanceStep.result.isnot(None)).limit(_MAX_FILAS * 4).all():
        if paso.instance_id in retenidas:
            continue
        datos = _json(paso.result)
        if tachar(datos, set()):
            paso.result = json.dumps(datos, default=str)
            informe["steps"] += 1
    return informe
