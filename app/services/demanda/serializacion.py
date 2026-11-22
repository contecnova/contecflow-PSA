"""Cómo sale un expediente por la API (operador y portal).

`resumen` para listas y `detalle` para la ficha. El cliente del portal no ve
comentarios ni documentos internos, ni campos `client_visible: false`, ni las
versiones de los campos internos. Los nombres de tipos, fases, pasos y campos
salen en el idioma de quien pide (con `*_i18n` aparte).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor, puede_gestionar
from app.services.demanda.motor import (acciones_posibles, datos_de, estado_del_plazo, estados_de_la_ronda,
                                        flujo_de, horas_efectivas, jload)


def _nombres_de_usuario(db: Session, ids: set) -> dict:
    from app.models.user import User
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.query(User).filter(User.id.in_(ids)).all()}


def resumen(db: Session, req, idioma: str = "es", cache: Optional[dict] = None) -> dict:
    from app.models.demanda import DemandRequestType
    from app.models.project import Project
    cache = cache if cache is not None else {}
    defn = flujo_de(req)
    f = D.fase(defn, req.current_phase_key) or {}
    clave_tipo = ("tipo", req.type_id)
    if clave_tipo not in cache:
        t = db.query(DemandRequestType).filter(DemandRequestType.id == req.type_id).first() if req.type_id else None
        cache[clave_tipo] = D.nombre(jload(t.name_i18n, {}), idioma) or (t.name if t else req.type_key) \
            if t else req.type_key
    clave_p = ("proyecto", req.project_id)
    if req.project_id and clave_p not in cache:
        p = db.query(Project.name).filter(Project.id == req.project_id).first()
        cache[clave_p] = p[0] if p else None
    solicitante = None
    if req.client_user_id:
        from app.models.client_portal import ClientUser
        c = db.query(ClientUser.full_name).filter(ClientUser.id == req.client_user_id).first()
        solicitante = c[0] if c else None
    elif req.requester_user_id:
        solicitante = _nombres_de_usuario(db, {req.requester_user_id}).get(req.requester_user_id)
    return {"id": req.id, "code": req.code, "title": req.title, "type_key": req.type_key,
            "type_name": cache[clave_tipo], "origin": req.origin, "status": req.status,
            "current_phase_key": req.current_phase_key, "current_phase_name": D.nombre(f.get("name"), idioma) or None,
            "project_id": req.project_id, "project_name": cache.get(clave_p), "standalone": bool(req.standalone),
            "scope_kind": req.scope_kind, "scope_ref_id": req.scope_ref_id, "requester_name": solicitante,
            "created_at": req.created_at, "submitted_at": req.submitted_at, "sla_due_at": req.sla_due_at,
            "sla_state": estado_del_plazo(req), "closed_at": req.closed_at, "flow_version": req.flow_version}


def _campo_dict(c: dict, idioma: str, editables: list, requeridos: list) -> dict:
    return {"key": c["key"], "label": D.nombre(c.get("label"), idioma), "label_i18n": c.get("label"),
            "type": c.get("type", "text"),
            "options": [{"value": o.get("value"), "label": D.nombre(o.get("label"), idioma)} for o in c.get("options") or []],
            "critical": bool(c.get("critical")), "owner": c.get("owner", "client"),
            "client_visible": c.get("client_visible", True), "editable": c["key"] in editables,
            "required_now": c["key"] in requeridos}


def detalle(db: Session, req, actor: Actor, idioma: str = "es") -> dict:
    from app.models.demanda import DemandComment, DemandDocument, DemandFieldVersion, DemandStepState, DemandTransition
    from app.services.demanda.expediente import campos_editables, es_solicitante, puede_editar_como_solicitante
    cliente = actor.kind == "client"
    defn = flujo_de(req)
    datos = datos_de(req)
    d = resumen(db, req, idioma)
    editables = campos_editables(db, actor, req)
    actual = D.fase(defn, req.current_phase_key) or {}
    if req.status == "draft":
        requeridos = defn.get("submit_required") or []
    else:
        requeridos = actual.get("required_fields") or []
    visibles = [c for c in D.campos(defn) if not cliente or c.get("client_visible", True)]
    d["flow"] = {"id": req.flow_id, "version": req.flow_version}
    d["data"] = {c["key"]: datos.get(c["key"]) for c in visibles}
    d["fields"] = [_campo_dict(c, idioma, editables, requeridos) for c in visibles]
    d["title_editable"] = "title" in editables
    estados = db.query(DemandStepState).filter(DemandStepState.request_id == req.id).all()
    nombres = _nombres_de_usuario(db, {s.decided_by for s in estados})
    actuales = estados_de_la_ronda(db, req) if req.current_phase_key else []
    i_actual = D.indice(defn, req.current_phase_key)
    fases = []
    for i, f in enumerate(D.fases(defn)):
        de_la_fase = [s for s in estados if s.phase_key == f["key"]]
        ronda = max((s.round for s in de_la_fase), default=0)
        ultimos = [s for s in de_la_fase if s.round == ronda]
        if f["key"] == req.current_phase_key and req.status in ("in_progress", "pending_info", "on_hold"):
            estado = "current"
        elif ultimos and all(s.status in ("approved", "done") for s in ultimos):
            estado = "done"
        elif ultimos and any(s.status == "skipped" for s in ultimos):
            estado = "skipped"
        elif ultimos and any(s.status == "rejected" for s in ultimos):
            estado = "rejected"
        elif i_actual >= 0 and i < i_actual and not ultimos:
            estado = "skipped"
        else:
            estado = "pending"
        pasos = []
        for p in D.pasos(f):
            st = next((s for s in ultimos if s.step_key == p["key"]), None)
            puede = acciones_posibles(db, req, actor, f, p, actuales) if (f["key"] == req.current_phase_key
                                                                          and not cliente) else []
            if cliente and (p.get("assignee") or {}).get("type") == "requester" and f["key"] == req.current_phase_key:
                puede = acciones_posibles(db, req, actor, f, p, actuales)
            item = {"key": p["key"], "name": D.nombre(p.get("name"), idioma), "mode": p.get("mode", "approval"),
                    "status": st.status if st else None, "can_decide": bool(puede), "decisions": puede}
            if not cliente:
                item.update({"assignee_label": (p.get("assignee") or {}).get("label")
                             or (p.get("assignee") or {}).get("type"),
                             "assignee": p.get("assignee"), "quorum": p.get("quorum", "any"),
                             "decided_by_name": nombres.get(st.decided_by) if st else None,
                             "decided_at": st.decided_at if st else None, "note": st.note if st else None,
                             "votes": jload(st.votes, []) if st else [],
                             "approval_request_id": st.approval_request_id if st else None})
            pasos.append(item)
        fase = {"key": f["key"], "name": D.nombre(f.get("name"), idioma), "kind": f.get("kind", "approval"),
                "status": estado, "parallel": bool(f.get("parallel"))}
        if not cliente:
            fase.update({"steps": pasos, "return_targets": D.destinos_de_devolucion(defn, f),
                         "entered_at": req.phase_entered_at if f["key"] == req.current_phase_key else None,
                         "sla_due_at": req.sla_due_at if f["key"] == req.current_phase_key else None,
                         "sla_hours": f.get("sla_hours")})
        else:
            fase["steps"] = [x for x in pasos if x["can_decide"]]
        fases.append(fase)
    d["phases"] = fases
    transiciones = db.query(DemandTransition).filter(DemandTransition.request_id == req.id) \
        .order_by(DemandTransition.seq).all()
    d["transitions"] = [{"id": t.id, "seq": t.seq, "from_phase": t.from_phase, "to_phase": t.to_phase,
                         "step_key": t.step_key, "decision": t.decision, "to_status": t.to_status,
                         "actor_name": t.actor_name,
                         "actor_kind": "client" if t.actor_client_id else ("user" if t.actor_user_id else "system"),
                         "actor_role": t.actor_role, "justification": t.justification, "is_bypass": bool(t.is_bypass),
                         "created_at": t.created_at} for t in transiciones
                        if not cliente or not t.decision.startswith("vote_")]
    versiones = db.query(DemandFieldVersion).filter(DemandFieldVersion.request_id == req.id) \
        .order_by(DemandFieldVersion.created_at).all()
    claves_visibles = {c["key"] for c in visibles}
    d["field_versions"] = [{"field": v.field, "value": jload(v.value, None), "source": v.source,
                            "phase_key": v.phase_key, "author_name": v.author_name, "note": v.note,
                            "created_at": v.created_at} for v in versiones if v.field in claves_visibles]
    docs = db.query(DemandDocument).filter(DemandDocument.request_id == req.id) \
        .order_by(DemandDocument.created_at).all()
    d["documents"] = [{"id": x.id, "tag": x.tag, "phase_key": x.phase_key, "file_name": x.file_name, "size": x.size,
                       "mime": x.mime, "uploaded_by_name": x.uploaded_by_name, "is_annex": bool(x.is_annex),
                       "personal_data": bool(x.personal_data), "internal": bool(x.internal),
                       "created_at": x.created_at} for x in docs if not cliente or not x.internal]
    comentarios = db.query(DemandComment).filter(DemandComment.request_id == req.id) \
        .order_by(DemandComment.created_at).all()
    d["comments"] = [{"id": c.id, "body": c.body, "internal": bool(c.internal), "phase_key": c.phase_key,
                      "author_name": c.author_name, "author_kind": "client" if c.author_client_id else "user",
                      "created_at": c.created_at} for c in comentarios if not cliente or not c.internal]
    d["committee"] = {"required": req.committee_required, "date": req.committee_date,
                      "reasons": jload(req.committee_reasons, [])}
    d["result"] = {"kind": req.result_kind, "project_id": req.result_project_id,
                   "change_request_id": req.result_change_request_id, "proposal_id": req.result_proposal_id,
                   "actions": jload(req.executed_actions, [])}
    d["client_locked"] = bool(req.client_locked)
    d["metrics"] = {"effective_hours": horas_efectivas(req), "paused_hours": round((req.paused_seconds or 0) / 3600, 2)}
    solicitante = es_solicitante(actor, req)
    gestiona = puede_gestionar(actor)
    abierto = req.status not in ("approved", "rejected", "withdrawn", "done")
    d["actions"] = {
        "can_edit_fields": bool(editables), "can_submit": (req.status == "draft" and (solicitante or (
            actor.kind == "user" and req.created_by_user_id == actor.id))) or (req.status == "pending_info" and (
                solicitante or gestiona)),
        "can_comment": True, "can_upload": abierto or req.status == "approved", "can_withdraw": solicitante and abierto,
        "can_schedule_committee": (not cliente and gestiona and actual.get("kind") == "committee"
                                   and req.status in ("in_progress", "on_hold")),
        "can_generate_summary": not cliente and gestiona and req.status != "draft",
        "can_execute": not cliente and gestiona and req.status == "approved" and not req.result_kind,
        "execution_modes": defn.get("execution") or list(D.MODOS_DE_EJECUCION),
        "client_editable_phase": puede_editar_como_solicitante(req) if solicitante else False,
    }
    if cliente:
        pedido = next((t for t in reversed(transiciones) if t.decision == "request_info"), None)
        d["info_request"] = pedido.justification if pedido and req.status == "pending_info" else None
    return d


def cargar_json(texto) -> dict:
    try:
        return json.loads(texto) if texto else {}
    except ValueError:
        return {}
