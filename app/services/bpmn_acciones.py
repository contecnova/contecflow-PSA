"""Acciones automaticas de las tareas de servicio BPMN (lista cerrada, sin codigo).

Revision BPM 2026-11-23 (docs/BPM.md, «Tareas automáticas»). Una
`serviceTask` (o `sendTask`, `businessRuleTask`, `scriptTask`) con el atributo
`contecflow:action` se ejecuta sola, en la cola del motor
(`bpmn_engine.ejecutar_trabajos`), con reintentos e incidente. Sin `action`
sigue esperando confirmacion humana, como desde la auditoria 22-11-2026.

**No se ejecuta codigo del diagrama, nunca.** Las acciones son estas y solo
estas; su configuracion (`contecflow:actionConfig`, objeto JSON) admite
`${variable}` como sustitucion de texto, no como expresion:

- `set`: `{"variables": {"x": "valor o ${otra}"}}` → fija variables.
- `notify`: `{"to": "initiator" | "${var}" | id o correo, "message": "…"}` →
  aviso en la campana (en el idioma del destinatario).
- `ticket`: `{"title", "description"?, "project_id"?}` → peticion de servicio
  en el service desk a nombre de quien arranco la instancia (exige
  `sd.trabajar`); deja `ticket_id` y `ticket_number`.
- `change`: `{"title", "description"?, "project_id", "justification"?}` →
  solicitud de cambio de proyecto en borrador (exige `cambios.responsables`);
  deja `change_request_id` y `change_request_code`.
- `demand`: `{"title", "description"?, "type_key"?}` → expediente del flujo de
  demanda en borrador; deja `demand_id` y `demand_code`.
- `approval`: `{"summary"?}` → solicitud en el motor de aprobaciones (tipo
  `bpmn_step`, con las variables como contexto de sus reglas). Si la empresa
  no tiene flujo para `bpmn_step`, la tarea pasa a la bandeja de BPM como
  aprobacion humana. La decision deja `aprobado` (o `resultVariable`) y
  `approval_status`.
- `policy`: `{"domain": "<dominio>", "resultVariable"?}` → evalua las
  politicas publicadas del dominio con las variables como contexto; deja la
  decision (`block`, `review`, `auto_approve`, `allow`) en `policy_decision`.

Cada accion actua con la identidad de quien arranco la instancia y con sus
capacidades; lo que crea queda en la auditoria de su modulo.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

#: Devuelta por `ejecutar` cuando el paso queda esperando (aprobacion abierta).
ESPERAR = object()

ACCIONES = ("set", "notify", "ticket", "change", "demand", "approval", "policy")

#: Capacidad que necesita quien arranco la instancia para cada accion.
_CAPACIDAD = {"ticket": "sd.trabajar", "change": "cambios.responsables"}


def _config(n) -> dict:
    try:
        datos = json.loads(n.ext.get("actionConfig") or "{}")
        return datos if isinstance(datos, dict) else {}
    except ValueError:
        return {}


def _texto(valor, variables: dict, tope: int = 500) -> str:
    from app.services.bpmn_engine import _interpolar
    return _interpolar(str(valor or ""), variables)[:tope]


def _iniciador(db: Session, inst):
    from app.models.user import User
    u = db.query(User).filter(User.id == inst.started_by_user_id).first() if inst.started_by_user_id else None
    if u is None or not u.is_active:
        raise error(409, "bpm_accion_sin_iniciador")
    return u


def _exigir(db: Session, user, accion: str) -> None:
    cap = _CAPACIDAD.get(accion)
    if not cap or getattr(user, "is_superadmin", False):
        return
    from app.core import capacidades
    if not capacidades.tiene(db, user, cap):
        raise error(403, "capacidad_requerida", capacidad=cap)


def ejecutar(db: Session, inst, paso, n) -> Optional[dict]:
    """Ejecuta la accion del paso. Devuelve las variables que aporta o `ESPERAR`."""
    from app.services.bpmn_engine import _variables
    accion = n.accion
    if accion not in ACCIONES:
        raise error(422, "bpm_accion_desconocida", accion=accion or "")
    cfg = _config(n)
    variables = _variables(inst)
    if accion == "set":
        crudas = cfg.get("variables") or {}
        if not isinstance(crudas, dict):
            raise error(422, "bpm_accion_config_no_valida", accion=accion)
        return {k: (_texto(v, variables, 2000) if isinstance(v, str) else v) for k, v in crudas.items()}
    usuario = _iniciador(db, inst)
    _exigir(db, usuario, accion)
    if accion == "notify":
        return _avisar(db, inst, cfg, variables, usuario)
    if accion == "ticket":
        return _ticket(db, inst, n, cfg, variables, usuario)
    if accion == "change":
        return _cambio(db, inst, n, cfg, variables, usuario)
    if accion == "demand":
        return _demanda(db, inst, n, cfg, variables, usuario)
    if accion == "approval":
        return _aprobacion(db, inst, paso, n, cfg, variables, usuario)
    return _politica(db, inst, cfg, variables)


def _destinatario(db: Session, inst, valor, variables: dict) -> Optional[str]:
    from app.services.bpmn_engine import _Resolutor, _valor_de
    v = (valor or "initiator").strip()
    if v in ("initiator", "starter"):
        return inst.started_by_user_id
    return _Resolutor(db, inst.organization_id).usuario(_valor_de(v, inst, variables))


def _avisar(db: Session, inst, cfg: dict, variables: dict, usuario) -> dict:
    from app.services.notifications import notify_user
    uid = _destinatario(db, inst, cfg.get("to"), variables)
    if not uid:
        raise error(422, "bpm_accion_config_no_valida", accion="notify")
    mensaje = _texto(cfg.get("message"), variables)
    notify_user(db, uid, "task_assigned", mensaje or "BPM", None, "bpmn_instance", inst.id, "/bpm",
                aviso={"titulo": "bpm.aviso_de_proceso", "params": {"mensaje": mensaje}})
    return {}


def _titulo(n, cfg: dict, variables: dict) -> str:
    return _texto(cfg.get("title") or n.nombre or n.id, variables, 255) or n.id


def _ticket(db: Session, inst, n, cfg: dict, variables: dict, usuario) -> dict:
    from app.models.service_desk import Ticket, TicketPriority, TicketType
    from app.services.sla_service import next_ticket_number
    proyecto = _texto(cfg.get("project_id"), variables, 36) or None
    t = Ticket(organization_id=inst.organization_id, number=next_ticket_number(TicketType.service_request.value, db),
               ticket_type=TicketType.service_request, title=_titulo(n, cfg, variables),
               description=_texto(cfg.get("description"), variables, 5000) or None,
               status="new", priority=TicketPriority.p3_medium, source="bpm", project_id=proyecto,
               requester_user_id=usuario.id, requester_name=usuario.full_name, created_by_user_id=usuario.id)
    db.add(t)
    db.flush()
    return {"ticket_id": t.id, "ticket_number": t.number}


def _cambio(db: Session, inst, n, cfg: dict, variables: dict, usuario) -> dict:
    from app.models.project import Project
    from app.models.resources import ChangeRequest
    from app.services.change_service import _next_code
    proyecto = _texto(cfg.get("project_id"), variables, 36)
    q = db.query(Project.id).filter(Project.id == proyecto)
    if inst.organization_id:
        q = q.filter(Project.organization_id == inst.organization_id)
    if not proyecto or q.first() is None:
        raise error(404, "proyecto_no_encontrado")
    cr = ChangeRequest(organization_id=inst.organization_id, project_id=proyecto, code=_next_code(db),
                       requested_by=usuario.id, title=_titulo(n, cfg, variables),
                       description=_texto(cfg.get("description"), variables, 5000) or _titulo(n, cfg, variables),
                       justification=_texto(cfg.get("justification"), variables, 5000) or None)
    db.add(cr)
    db.flush()
    return {"change_request_id": cr.id, "change_request_code": cr.code}


def _demanda(db: Session, inst, n, cfg: dict, variables: dict, usuario) -> dict:
    from app.services.demanda import entrada
    s = entrada.Solicitante(kind="employee", user=usuario)
    r = entrada.crear(db, s, {"title": _titulo(n, cfg, variables),
                              "description": _texto(cfg.get("description"), variables, 5000),
                              "submit": False, "type_key": cfg.get("type_key") or None},
                      org_id=inst.organization_id)
    return {"demand_id": r["id"], "demand_code": r.get("code")}


def _aprobacion(db: Session, inst, paso, n, cfg: dict, variables: dict, usuario):
    from app.services.approval_engine import fuentes
    from app.services.bpmn_engine import ESPERA_APROBACION, ESPERA_TAREA, TIPO_DE_APROBACION, _json
    resumen = _texto(cfg.get("summary") or n.nombre or n.id, variables, 500)
    contexto = {k: v for k, v in variables.items() if isinstance(v, (str, int, float, bool)) or v is None}
    fuentes.abrir(db, TIPO_DE_APROBACION, paso.id, resumen, usuario.id, contexto=contexto, propagar=True)
    estado = fuentes.estado(db, TIPO_DE_APROBACION, paso.id)
    var = (n.ext.get("resultVariable") or "aprobado").strip()
    if estado in ("approved", "rejected"):
        # Auto-aprobacion (o rechazo) de las reglas del flujo al abrirla.
        return {var: estado == "approved", "approval_status": estado}
    if estado == "pending":
        paso.wait_kind = ESPERA_APROBACION
    else:
        # Sin flujo de aprobacion para `bpmn_step`: aprobacion humana en la bandeja de BPM.
        paso.wait_kind = ESPERA_TAREA
        paso.result = json.dumps({**_json(paso.result), "approval": True})
        from app.services.bpmn_engine import _Resolutor, _asignar
        for k, v in _asignar(_Resolutor(db, inst.organization_id), inst, n, variables).items():
            setattr(paso, k, v)
    return ESPERAR


def _politica(db: Session, inst, cfg: dict, variables: dict) -> dict:
    from app.services.politicas.motor import evaluar
    dominio = str(cfg.get("domain") or "").strip()
    if not dominio:
        raise error(422, "bpm_accion_config_no_valida", accion="policy")
    salida = evaluar(db, dominio, contexto=dict(variables), organization_id=inst.organization_id)
    var = str(cfg.get("resultVariable") or "policy_decision").strip()
    return {var: salida.get("decision")}
