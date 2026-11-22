"""Motor del flujo de demanda: fases, pasos, decisiones, puertas, pausas y plazos.

Cada expediente lleva la foto del flujo con el que nació (`flow_snapshot`): el
motor lee siempre esa foto. Cada vez que se entra en una fase sube la ronda
(`phase_round`) y se crean sus pasos; volver a una fase la abre de nuevo con
pasos nuevos (la ronda anterior queda en el historial).

Todo cambio de estado deja una fila en `demand_transitions` (hash encadenado
con la anterior del mismo expediente) y un `audit_log`. Nadie escribe
`status` ni `current_phase_key` fuera de este módulo.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.demanda.acceso import SISTEMA, Actor, es_responsable, exigir_segregacion, miembros_de_grupo

logger = logging.getLogger(__name__)

ABIERTOS = ("in_progress", "pending_info", "on_hold")
CERRADOS = ("approved", "rejected", "withdrawn", "done")
TIPO_DE_APROBACION = "demand_step"


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def jload(texto, defecto):
    try:
        v = json.loads(texto) if texto else defecto
    except (TypeError, ValueError):
        return defecto
    return v if v is not None else defecto


def flujo_de(req) -> dict:
    return D.cargar(req.flow_snapshot)


def datos_de(req) -> dict:
    return jload(req.data, {})


def fase_actual(req) -> Optional[dict]:
    return D.fase(flujo_de(req), req.current_phase_key)


# ── Log inmutable ────────────────────────────────────────────────────────────

def _hash(previo: Optional[str], fila: dict) -> str:
    base = json.dumps(fila, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(((previo or "") + base).encode("utf-8")).hexdigest()


def registrar(db: Session, req, actor: Actor, decision: str, *, desde: Optional[str] = None,
              hacia: Optional[str] = None, paso: Optional[str] = None, justificacion: Optional[str] = None,
              estado_previo: Optional[str] = None, bypass: bool = False, datos: Optional[dict] = None):
    """Añade una transición al log del expediente (y al registro de auditoría)."""
    from app.models.demanda import DemandTransition
    from app.services.audit import audit_log
    ultima = db.query(DemandTransition).filter(DemandTransition.request_id == req.id) \
        .order_by(DemandTransition.seq.desc()).first()
    seq = (ultima.seq + 1) if ultima else 1
    momento = ahora()
    fila = {"request_id": req.id, "seq": seq, "from_phase": desde, "to_phase": hacia, "step_key": paso,
            "decision": decision, "from_status": estado_previo, "to_status": req.status,
            "actor_user_id": actor.id if actor.kind == "user" else None,
            "actor_client_id": actor.id if actor.kind == "client" else None,
            "actor_role": actor.rol, "justification": justificacion, "is_bypass": bypass,
            "at": momento.isoformat()}
    t = DemandTransition(organization_id=req.organization_id, request_id=req.id, seq=seq, from_phase=desde,
                         to_phase=hacia, step_key=paso, decision=decision, from_status=estado_previo,
                         to_status=req.status, actor_user_id=fila["actor_user_id"],
                         actor_client_id=fila["actor_client_id"], actor_name=actor.nombre[:255] or None,
                         actor_role=actor.rol, justification=justificacion, is_bypass=bypass,
                         payload=json.dumps(datos, ensure_ascii=False, default=str) if datos else None,
                         prev_hash=ultima.hash if ultima else None, created_at=momento)
    t.hash = _hash(t.prev_hash, fila)
    db.add(t)
    audit_log(db, actor.user if actor.kind == "user" else None, f"DEMAND_{decision.upper()}", "demand_request",
              req.id, req.code, new_values={"phase": hacia or desde, "status": req.status, "step": paso},
              metadata={"justification": justificacion, "bypass": bypass, "actor_kind": actor.kind,
                        "client_user_id": actor.id if actor.kind == "client" else None})
    return t


def verificar_cadena(db: Session, req) -> bool:
    """Comprueba el hash encadenado del log de un expediente."""
    from app.models.demanda import DemandTransition
    previo = None
    for t in db.query(DemandTransition).filter(DemandTransition.request_id == req.id) \
            .order_by(DemandTransition.seq).all():
        if t.prev_hash != previo:
            return False
        previo = t.hash
    return True


# ── Pasos ────────────────────────────────────────────────────────────────────

def estados_de_la_ronda(db: Session, req) -> list:
    from app.models.demanda import DemandStepState
    return db.query(DemandStepState).filter(DemandStepState.request_id == req.id,
                                            DemandStepState.phase_key == req.current_phase_key,
                                            DemandStepState.round == req.phase_round).all()


def paso_activo(f: dict, estados: list, clave: str) -> bool:
    """En serie, un paso solo está activo si los anteriores están resueltos."""
    st = next((s for s in estados if s.step_key == clave), None)
    if st is None or st.status != "pending":
        return False
    if f.get("parallel"):
        return True
    for p in D.pasos(f):
        if p.get("key") == clave:
            return True
        previo = next((s for s in estados if s.step_key == p.get("key")), None)
        if previo is not None and previo.status == "pending" and not p.get("optional"):
            return False
    return True


def _abrir_en_bandeja(db: Session, req, f: dict, p: dict, st, actor: Actor) -> None:
    """Paso delegado en un flujo del motor de aprobaciones: abre su solicitud."""
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine import fuentes
    solicitante = req.requester_user_id or (actor.id if actor.kind == "user" else None) or req.created_by_user_id
    if not solicitante:
        return
    datos = datos_de(req)
    fuentes.abrir(db, TIPO_DE_APROBACION, st.id,
                  f"{req.code} — {req.title} · {D.nombre(f.get('name'))} / {D.nombre(p.get('name'))}",
                  solicitante,
                  {"request_code": req.code, "phase": f.get("key"), "step": p.get("key"),
                   "coste": datos.get(D.campo_de_politica(flujo_de(req), "coste") or "coste"),
                   "project_id": req.project_id},
                  workflow_id=(p.get("assignee") or {}).get("value"))
    ar = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == TIPO_DE_APROBACION,
                                          ApprovalRequest.entity_id == st.id).first()
    if ar is not None:
        st.approval_request_id = ar.id


def _activar(db: Session, req, f: dict, actor: Actor) -> None:
    """Abre en la bandeja los pasos recién activos delegados en un flujo de aprobación."""
    estados = estados_de_la_ronda(db, req)
    for p in D.pasos(f):
        if (p.get("assignee") or {}).get("type") != "approval_workflow":
            continue
        st = next((s for s in estados if s.step_key == p.get("key")), None)
        if st is not None and st.approval_request_id is None and paso_activo(f, estados, p.get("key")):
            _abrir_en_bandeja(db, req, f, p, st, actor)


# ── Entrar en fase / cerrar ──────────────────────────────────────────────────

def cumple_condicion(db: Session, req, cond: dict) -> bool:
    """Condición de una fase (`{conditions, match, use_policies}`): datos y políticas."""
    si, _ = D.evaluar_puerta({"gate": cond}, datos_de(req))
    if cond.get("use_policies"):
        try:
            from app.services import politicas
            ev = politicas.evaluar(db, "demanda", req)
            etiqueta = cond.get("policy_tag")
            if ev.get("decision") in ("review", "block") or (etiqueta and etiqueta in
                                                             ((ev.get("resultado") or {}).get("etiquetas") or [])):
                si = True
        except Exception:
            logger.warning("demanda: no se pudo evaluar la condición de %s", req.id, exc_info=True)
    if not (cond.get("conditions") or cond.get("use_policies")):
        return True
    return si


def _evaluar_puerta(db: Session, req, f: dict) -> None:
    datos = datos_de(req)
    requerido, motivos = D.evaluar_puerta(f, datos)
    if (f.get("gate") or {}).get("use_policies"):
        try:
            from app.services import politicas
            ev = politicas.evaluar(db, "demanda", req)
            etiquetas = (ev.get("resultado") or {}).get("etiquetas") or []
            if ev.get("decision") in ("review", "block") or "comite" in etiquetas:
                requerido = True
                motivos.append("policy:" + ",".join(politicas.resumen(ev).get("politicas") or []) or "policy")
        except Exception:
            logger.warning("demanda: no se pudo evaluar la política de %s", req.id, exc_info=True)
    req.committee_required = requerido
    req.committee_reasons = json.dumps(motivos, ensure_ascii=False)


def entrar_en_fase(db: Session, req, clave: str, actor: Actor, decision: str, *,
                   justificacion: Optional[str] = None, paso: Optional[str] = None, bypass: bool = False,
                   datos_extra: Optional[dict] = None) -> None:
    """Mueve el expediente a la fase `clave` (o a un final `end:*`)."""
    from app.models.demanda import DemandStepState
    defn = flujo_de(req)
    desde = req.current_phase_key
    estado_previo = req.status
    if clave in (D.FIN_APROBADA, D.FIN_RECHAZADA):
        cerrar(db, req, actor, "approved" if clave == D.FIN_APROBADA else "rejected", decision,
               justificacion=justificacion, paso=paso, bypass=bypass, datos_extra=datos_extra)
        return
    f = D.fase(defn, clave)
    if f is None:
        raise error(422, "dem_destino_no_valido", destino=clave)
    if f.get("condition") and not cumple_condicion(db, req, f["condition"]):
        # Fase condicional que no aplica: se salta sola y queda en el log.
        registrar(db, req, SISTEMA, "auto_skip", desde=desde, hacia=clave, estado_previo=estado_previo,
                  datos={"condition": f.get("condition")})
        req.current_phase_key = clave
        entrar_en_fase(db, req, D.siguiente(defn, clave), actor, decision, justificacion=justificacion,
                       paso=paso, bypass=bypass, datos_extra=datos_extra)
        return
    momento = ahora()
    req.current_phase_key = clave
    req.phase_round = (req.phase_round or 0) + 1
    req.phase_entered_at = momento
    req.status = "in_progress"
    req.sla_warned = req.sla_breached = False
    horas = f.get("sla_hours")
    try:
        req.sla_due_at = momento + timedelta(hours=float(horas)) if horas not in (None, "", 0) else None
    except (TypeError, ValueError):
        req.sla_due_at = None
    # Desde la primera fase con bloqueo, la ficha queda bloqueada para el cliente.
    i = D.indice(defn, clave)
    if any(x.get("lock_client_from_here") for x in D.fases(defn)[:i + 1]):
        req.client_locked = True
    for p in D.pasos(f):
        db.add(DemandStepState(organization_id=req.organization_id, request_id=req.id, phase_key=clave,
                               round=req.phase_round, step_key=p["key"], status="pending", votes="[]"))
    db.flush()
    if f.get("kind") == "gate":
        _evaluar_puerta(db, req, f)
    registrar(db, req, actor, decision, desde=desde, hacia=clave, paso=paso, justificacion=justificacion,
              estado_previo=estado_previo, bypass=bypass, datos=datos_extra)
    _activar(db, req, f, actor)
    from app.services.demanda import avisos
    avisos.emitir(db, req, "enter", f)


def cerrar(db: Session, req, actor: Actor, estado: str, decision: str, *, justificacion: Optional[str] = None,
           paso: Optional[str] = None, bypass: bool = False, datos_extra: Optional[dict] = None) -> None:
    estado_previo = req.status
    desde = req.current_phase_key
    _cancelar_bandeja(db, req, "cancelled", "Expediente cerrado")
    req.status = estado
    req.sla_due_at = None
    if estado != "approved":
        req.closed_at = ahora()
    registrar(db, req, actor, decision, desde=desde, hacia=None, paso=paso, justificacion=justificacion,
              estado_previo=estado_previo, bypass=bypass, datos=datos_extra)
    if estado in ("approved", "rejected"):
        from app.services.demanda import ejecucion
        ejecucion.acciones_al_cerrar(db, req, actor, estado)
    from app.services.demanda import avisos
    avisos.emitir(db, req, "closed", fase_actual(req))


def _cancelar_bandeja(db: Session, req, estado: str, nota: str) -> None:
    from app.services.approval_engine import fuentes
    for st in estados_de_la_ronda(db, req):
        if st.approval_request_id and st.status == "pending":
            fuentes.cerrar(db, TIPO_DE_APROBACION, st.id, estado, nota)


# ── Decidir ──────────────────────────────────────────────────────────────────

def _exigir_justificacion(decision: str, justificacion: Optional[str], bypass: bool = False) -> None:
    if (decision in D.CON_JUSTIFICACION or bypass) and not (justificacion or "").strip():
        raise error(422, "dem_justificacion_obligatoria", decision=decision)


def _recuento(db: Session, p: dict, votos: list) -> tuple[int, int, int, int]:
    """(aprobaciones necesarias, a favor, en contra, miembros) según el quórum del paso."""
    asignado = p.get("assignee") or {}
    quorum = p.get("quorum") or "any"
    n = len(miembros_de_grupo(db, asignado.get("value"))) if asignado.get("type") in ("group", "committee") else 1
    n = max(n, 1)
    necesarias = 1 if quorum == "any" else (n if quorum == "all" else n // 2 + 1)
    a_favor = sum(1 for v in votos if v.get("decision") == "approve")
    en_contra = sum(1 for v in votos if v.get("decision") == "reject")
    return necesarias, a_favor, en_contra, n


def acciones_posibles(db: Session, req, actor: Actor, f: dict, p: dict, estados: list) -> list[str]:
    """Decisiones que este actor puede tomar ahora sobre el paso (vacío si ninguna)."""
    if req.status not in ("in_progress", "on_hold") or req.current_phase_key != f.get("key"):
        return []
    if not paso_activo(f, estados, p.get("key")):
        return []
    st = next((s for s in estados if s.step_key == p.get("key")), None)
    if st and st.approval_request_id and (p.get("assignee") or {}).get("type") == "approval_workflow":
        from app.services.approval_engine import fuentes
        if fuentes.estado(db, TIPO_DE_APROBACION, st.id) == "pending":
            return []
    if not es_responsable(db, actor, req, p, f):
        return []
    votos = jload(st.votes if st else None, [])
    if actor.id and any(v.get("user_id") == actor.id for v in votos):
        return []
    lista = D.decisiones(f)
    if p.get("mode") == "task":
        lista = ["complete" if d == "approve" else d for d in lista]
    if req.status == "on_hold":
        lista = [d for d in lista if d in ("approve", "complete", "reject")]
    return lista


def decidir(db: Session, req, actor: Actor, paso_clave: str, decision: str, *,
            destino: Optional[str] = None, justificacion: Optional[str] = None,
            desde_bandeja: bool = False) -> None:
    """Una decisión sobre un paso de la fase actual. Commitea."""
    if req.status not in ("in_progress", "on_hold"):
        raise error(409, "dem_estado_no_permite", estado=req.status)
    defn = flujo_de(req)
    f = D.fase(defn, req.current_phase_key)
    p = D.paso(f or {}, paso_clave)
    if f is None or p is None:
        raise error(404, "dem_paso_no_encontrado", paso=paso_clave)
    estados = estados_de_la_ronda(db, req)
    st = next((s for s in estados if s.step_key == paso_clave), None)
    if st is None or st.status != "pending" or not paso_activo(f, estados, paso_clave):
        raise error(409, "dem_paso_ya_decidido", paso=paso_clave)
    if decision == "complete":
        decision = "approve"
    permitidas = ["approve" if d == "complete" else d for d in D.decisiones(f)]
    if decision not in permitidas or (req.status == "on_hold" and decision not in ("approve", "reject")):
        raise error(422, "dem_decision_no_permitida", decision=decision)
    if not desde_bandeja:
        if st.approval_request_id:
            from app.services.approval_engine import fuentes
            if fuentes.estado(db, TIPO_DE_APROBACION, st.id) == "pending":
                raise error(409, "dem_paso_en_bandeja")
        if not es_responsable(db, actor, req, p, f):
            raise error(403, "dem_no_eres_responsable")
    exigir_segregacion(db, actor, req, f)
    es_bypass = decision == "fast_track" and bool(req.committee_required)
    if es_bypass and not (f.get("gate") or {}).get("allow_bypass", True):
        raise error(409, "dem_bypass_no_permitido")
    _exigir_justificacion(decision, justificacion, es_bypass)
    if decision in ("approve", "fast_track", "to_committee"):
        faltan = D.faltan(datos_de(req), f.get("required_fields") or [], req.title)
        if faltan:
            raise error(422, "dem_campos_obligatorios", campos=", ".join(faltan))
    momento = ahora()
    clave_fase = f["key"]

    if decision in ("approve", "reject") and p.get("quorum") in ("all", "majority") \
            and (p.get("assignee") or {}).get("type") in ("group", "committee") and actor.kind == "user":
        votos = jload(st.votes, [])
        if any(v.get("user_id") == actor.id for v in votos):
            raise error(409, "dem_ya_votaste")
        votos.append({"user_id": actor.id, "name": actor.nombre, "decision": decision,
                      "note": justificacion, "at": momento.isoformat()})
        st.votes = json.dumps(votos, ensure_ascii=False)
        necesarias, a_favor, en_contra, n = _recuento(db, p, votos)
        if a_favor < necesarias and en_contra <= n - necesarias:
            registrar(db, req, actor, "vote_" + decision, desde=clave_fase, hacia=clave_fase, paso=paso_clave,
                      justificacion=justificacion, estado_previo=req.status,
                      datos={"a_favor": a_favor, "en_contra": en_contra, "necesarias": necesarias})
            db.commit()
            return
        decision = "approve" if a_favor >= necesarias else "reject"

    st.decided_by = actor.id if actor.kind == "user" else None
    st.decided_at = momento
    st.note = justificacion
    if req.status == "on_hold":
        req.status = "in_progress"

    if decision == "approve":
        st.status = "done" if p.get("mode") == "task" else "approved"
        estados = estados_de_la_ronda(db, req)
        pendientes = [s for s in estados if s.status == "pending"
                      and not (D.paso(f, s.step_key) or {}).get("optional")]
        if pendientes:
            registrar(db, req, actor, "complete" if p.get("mode") == "task" else "approve", desde=clave_fase,
                      hacia=clave_fase, paso=paso_clave, justificacion=justificacion, estado_previo=req.status)
            _activar(db, req, f, actor)
            from app.services.demanda import avisos
            avisos.emitir(db, req, "decision", f)
            db.commit()
            return
        destino_ = D.resolver_destino(defn, clave_fase, (f.get("targets") or {}).get("approve") or f.get("on_approve"),
                                      "next")
        entrar_en_fase(db, req, destino_, actor, "complete" if p.get("mode") == "task" else "approve",
                       justificacion=justificacion, paso=paso_clave)
    elif decision == "reject":
        st.status = "rejected"
        _cancelar_bandeja(db, req, "cancelled", "Fase rechazada")
        destino_ = D.resolver_destino(defn, clave_fase, (f.get("targets") or {}).get("reject") or f.get("on_reject"),
                                      D.FIN_RECHAZADA)
        entrar_en_fase(db, req, destino_, actor, "reject", justificacion=justificacion, paso=paso_clave)
    elif decision == "return":
        posibles = D.destinos_de_devolucion(defn, f)
        if destino not in posibles:
            raise error(422, "dem_destino_no_valido", destino=destino or "")
        st.status = "returned"
        _cancelar_bandeja(db, req, "cancelled", "Devuelta a otra fase")
        entrar_en_fase(db, req, destino, actor, "return", justificacion=justificacion, paso=paso_clave)
    elif decision == "skip":
        st.status = "skipped"
        _cancelar_bandeja(db, req, "cancelled", "Fase saltada")
        destino_ = destino if destino and D.fase(defn, destino) else D.siguiente(defn, clave_fase)
        entrar_en_fase(db, req, destino_, actor, "skip", justificacion=justificacion, paso=paso_clave, bypass=True)
    elif decision == "request_info":
        pedir_informacion(db, req, actor, paso_clave, justificacion)
        st.decided_by = None
        st.decided_at = None
    elif decision == "hold":
        estado_previo = req.status
        req.status = "on_hold"
        st.decided_by = None
        st.decided_at = None
        registrar(db, req, actor, "hold", desde=clave_fase, hacia=clave_fase, paso=paso_clave,
                  justificacion=justificacion, estado_previo=estado_previo)
    elif decision in ("fast_track", "to_committee"):
        st.status = "approved"
        g = f.get("gate") or {}
        destino_ = g.get("if_false") if decision == "fast_track" else g.get("if_true")
        destino_ = D.resolver_destino(defn, clave_fase, destino_, "next")
        entrar_en_fase(db, req, destino_, actor, decision, justificacion=justificacion, paso=paso_clave,
                       bypass=es_bypass,
                       datos_extra={"committee_required": req.committee_required,
                                    "reasons": jload(req.committee_reasons, [])})
    db.commit()


def pedir_informacion(db: Session, req, actor: Actor, paso_clave: Optional[str], justificacion: str) -> None:
    """«Pendiente de información»: vuelve al solicitante y para el reloj si la fase lo dice."""
    f = fase_actual(req) or {}
    estado_previo = req.status
    req.status = "pending_info"
    if f.get("pause_on_info", True):
        req.paused_since = ahora()
    registrar(db, req, actor, "request_info", desde=req.current_phase_key, hacia=req.current_phase_key,
              paso=paso_clave, justificacion=justificacion, estado_previo=estado_previo)
    from app.services.demanda import avisos
    avisos.emitir(db, req, "info_requested", f, {"mensaje": justificacion})


def reanudar(db: Session, req, actor: Actor, nota: Optional[str] = None) -> None:
    """El solicitante aporta la información: vuelve a la fase y corre el reloj (sin contar la pausa)."""
    if req.status != "pending_info":
        raise error(409, "dem_estado_no_permite", estado=req.status)
    pausado = 0.0
    if req.paused_since:
        pausado = max(0.0, (ahora() - _aware(req.paused_since)).total_seconds())
        req.paused_seconds = (req.paused_seconds or 0.0) + pausado
        if req.sla_due_at:
            req.sla_due_at = _aware(req.sla_due_at) + timedelta(seconds=pausado)
        req.paused_since = None
    req.status = "in_progress"
    registrar(db, req, actor, "info_provided", desde=req.current_phase_key, hacia=req.current_phase_key,
              justificacion=nota, estado_previo="pending_info", datos={"paused_seconds": round(pausado)})
    from app.services.demanda import avisos
    avisos.emitir(db, req, "decision", fase_actual(req))


# ── Puente con la bandeja de aprobaciones ────────────────────────────────────

def aplicar_desde_bandeja(req_aprobacion, decision: str, actor_usuario, db: Session) -> None:
    """Decisión final de la bandeja sobre un paso delegado (`fuentes.aplicar`)."""
    from app.models.demanda import DemandRequest, DemandStepState
    st = db.query(DemandStepState).filter(DemandStepState.id == req_aprobacion.entity_id).first()
    if st is None or st.status != "pending":
        return
    req = db.query(DemandRequest).filter(DemandRequest.id == st.request_id).first()
    if req is None or req.current_phase_key != st.phase_key or req.phase_round != st.round:
        return
    from app.services.demanda.acceso import de_usuario
    nota = getattr(req_aprobacion, "final_note", None)
    decidir(db, req, de_usuario(actor_usuario), st.step_key,
            "approve" if decision == "approved" else "reject",
            justificacion=nota or ("Aprobado en la bandeja" if decision == "approved" else "Rechazado en la bandeja"),
            desde_bandeja=True)


# ── Plazos ───────────────────────────────────────────────────────────────────

def estado_del_plazo(req) -> Optional[str]:
    if req.status == "pending_info":
        return "paused"
    if req.status not in ("in_progress", "on_hold") or not req.sla_due_at:
        return None
    vence = _aware(req.sla_due_at)
    momento = ahora()
    if momento >= vence:
        return "breached"
    entrada = _aware(req.phase_entered_at) or momento
    f = fase_actual(req) or {}
    pct = float(f.get("sla_warn_pct") or 80) / 100.0
    total = (vence - entrada).total_seconds()
    if total > 0 and (momento - entrada).total_seconds() >= total * pct:
        return "warning"
    return "ok"


def horas_efectivas(req) -> float:
    """Horas desde el envío, sin contar las pausas por información pendiente."""
    if not req.submitted_at:
        return 0.0
    fin = _aware(req.closed_at) or ahora()
    pausa = (req.paused_seconds or 0.0)
    if req.paused_since:
        pausa += max(0.0, (ahora() - _aware(req.paused_since)).total_seconds())
    return round(max(0.0, (fin - _aware(req.submitted_at)).total_seconds() - pausa) / 3600.0, 2)


def revisar_plazos(db: Session, org_id: Optional[str]) -> dict:
    """Avisa al acercarse y al vencer el plazo de la fase (una vez por fase y ronda)."""
    from app.models.demanda import DemandRequest
    from app.services.demanda import avisos
    q = db.query(DemandRequest).filter(DemandRequest.status.in_(("in_progress", "on_hold")),
                                       DemandRequest.sla_due_at.isnot(None))
    if org_id:
        q = q.filter(DemandRequest.organization_id == org_id)
    avisados = vencidos = 0
    for req in q.all():
        estado = estado_del_plazo(req)
        f = fase_actual(req)
        if estado == "breached" and not req.sla_breached:
            req.sla_breached = req.sla_warned = True
            registrar(db, req, SISTEMA, "sla_breach", desde=req.current_phase_key, hacia=req.current_phase_key,
                      estado_previo=req.status)
            avisos.emitir(db, req, "sla_breach", f)
            vencidos += 1
        elif estado == "warning" and not req.sla_warned:
            req.sla_warned = True
            avisos.emitir(db, req, "sla_warning", f)
            avisados += 1
    db.commit()
    return {"warned": avisados, "breached": vencidos}
