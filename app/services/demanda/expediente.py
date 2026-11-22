"""El expediente: alta desde cualquier canal, edición de la ficha, envío, retirada y comentarios.

- La ficha la edita el solicitante en borrador, con información pendiente o en
  fases `client_editable`, y nunca desde que la ficha está bloqueada
  (`client_locked`). El equipo edita en la fase actual los campos de
  `internal_editable` (vacío = todos) si es responsable de algún paso de esa
  fase, o si gestiona la demanda.
- Cada cambio de un campo `critical` deja versión (valor, origen
  cliente/interno, fase, autor y fecha): el valor original nunca se pierde.
- Los campos `locked` de la fase actual no los edita nadie.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor, es_responsable, puede_gestionar
from app.services.demanda.motor import CERRADOS, ahora, datos_de, entrar_en_fase, flujo_de, jload, reanudar, registrar

CANAL_DE_ORIGEN = {"client_portal": "client_portal", "internal_portal": "internal_portal",
                   "operator": "operator", "supplier_portal": "supplier_portal"}
_MAX_TEXTO = 20000


def _convertir(c: dict, valor: Any):
    if valor is None or valor == "":
        return None
    tipo = c.get("type", "text")
    if tipo in ("number", "money"):
        try:
            return float(valor)
        except (TypeError, ValueError):
            raise error(422, "dem_valor_no_valido", campo=c.get("key"))
    if tipo == "boolean":
        return valor in (True, "true", "1", 1, "si", "sí", "yes", "on")
    if tipo == "select" and c.get("options"):
        valores = [str(o.get("value")) for o in c["options"]]
        if str(valor) not in valores:
            raise error(422, "dem_valor_no_valido", campo=c.get("key"))
        return str(valor)
    return str(valor)[:_MAX_TEXTO]


def obtener(db: Session, org_id: Optional[str], req_id: str):
    from app.models.demanda import DemandRequest
    q = db.query(DemandRequest).filter(DemandRequest.id == req_id)
    if org_id:
        q = q.filter(DemandRequest.organization_id == org_id)
    req = q.first()
    if req is None:
        raise error(404, "dem_expediente_no_encontrado")
    return req


def es_solicitante(actor: Actor, req) -> bool:
    if actor.kind == "client":
        return bool(req.client_user_id and req.client_user_id == actor.id)
    return actor.kind == "user" and bool(req.requester_user_id and req.requester_user_id == actor.id)


def puede_editar_como_solicitante(req) -> bool:
    if req.client_locked or req.status in CERRADOS or req.status == "on_hold":
        return False
    if req.status in ("draft", "pending_info"):
        return True
    f = D.fase(flujo_de(req), req.current_phase_key) or {}
    return req.status == "in_progress" and bool(f.get("client_editable"))


def campos_editables(db: Session, actor: Actor, req) -> list[str]:
    """Claves (y `title`) que este actor puede editar ahora."""
    defn = flujo_de(req)
    f = D.fase(defn, req.current_phase_key) or {}
    bloqueados = set(f.get("locked_fields") or [])
    if req.status in CERRADOS:
        return []
    if es_solicitante(actor, req):
        if not puede_editar_como_solicitante(req):
            return []
        claves = [c["key"] for c in D.campos(defn) if c.get("owner", "client") == "client"
                  and c.get("client_visible", True)]
        return [k for k in ["title"] + claves if k not in bloqueados]
    if actor.kind != "user":
        return []
    gestiona = puede_gestionar(actor)
    responsable = any(es_responsable(db, actor, req, p, f) for p in D.pasos(f)) if f else False
    if req.status == "draft" and gestiona and req.created_by_user_id == actor.id:
        return ["title"] + [c["key"] for c in D.campos(defn)]
    if not (responsable or gestiona) or req.status == "draft":
        return []
    permitidos = f.get("internal_editable") or [c["key"] for c in D.campos(defn)]
    return [k for k in permitidos if k not in bloqueados]


def _versionar(db: Session, req, actor: Actor, clave: str, valor, nota: Optional[str] = None) -> None:
    from app.models.demanda import DemandFieldVersion
    db.add(DemandFieldVersion(organization_id=req.organization_id, request_id=req.id, field=clave,
                              value=json.dumps(valor, ensure_ascii=False, default=str),
                              source="client" if es_solicitante(actor, req) and actor.kind == "client" else (
                                  "requester" if es_solicitante(actor, req) else "internal"),
                              phase_key=req.current_phase_key,
                              author_user_id=actor.id if actor.kind == "user" else None,
                              author_client_id=actor.id if actor.kind == "client" else None,
                              author_name=actor.nombre[:255] or None, note=nota, created_at=ahora()))


def _aplicar_datos(db: Session, req, actor: Actor, datos: dict, permitidos: list[str],
                   nota: Optional[str] = None) -> list[str]:
    defn = flujo_de(req)
    actuales = datos_de(req)
    cambiados = []
    for clave, valor in (datos or {}).items():
        c = D.campo(defn, clave)
        if c is None:
            continue
        if clave not in permitidos:
            raise error(403, "dem_campo_no_editable", campo=clave)
        nuevo = _convertir(c, valor)
        if actuales.get(clave) == nuevo:
            continue
        actuales[clave] = nuevo
        cambiados.append(clave)
        if c.get("critical"):
            _versionar(db, req, actor, clave, nuevo, nota)
    req.data = json.dumps(actuales, ensure_ascii=False, default=str)
    return cambiados


def _tipo(db: Session, org_id: Optional[str], clave: str):
    from app.models.demanda import DemandFlow, DemandRequestType
    t = db.query(DemandRequestType).filter(DemandRequestType.organization_id == org_id,
                                           DemandRequestType.key == clave,
                                           DemandRequestType.is_active.is_(True)).first()
    if t is None:
        raise error(404, "dem_tipo_no_encontrado")
    f = db.query(DemandFlow).filter(DemandFlow.id == t.flow_id, DemandFlow.is_active.is_(True)).first() \
        if t.flow_id else None
    if f is None:
        raise error(409, "dem_tipo_sin_flujo")
    return t, f


def crear(db: Session, actor: Actor, origen: str, datos: dict, *, org_id: Optional[str],
          proyectos_permitidos: Optional[list] = None) -> object:
    """Alta de un expediente desde un canal. Commitea. Devuelve el expediente."""
    from app.models.demanda import DemandRequest
    from app.models.project import Project
    from app.services.numbering import next_numbered_code
    t, flujo = _tipo(db, org_id, datos.get("type_key") or "")
    canales = jload(t.channels, [])
    if CANAL_DE_ORIGEN.get(origen) not in canales:
        raise error(403, "dem_canal_no_disponible", canal=origen)
    titulo = (datos.get("title") or "").strip()
    if len(titulo) < 3:
        raise error(422, "campo_obligatorio", campo="title")
    proyecto_id = datos.get("project_id") or None
    alcances = jload(t.scopes, []) or (["project"] if t.requires_project else ["project", "none"])
    alcance = datos.get("scope_kind") or ("project" if proyecto_id else "none")
    if alcance not in alcances and not (alcance == "none" and t.allows_standalone):
        raise error(422, "dem_alcance_no_permitido", alcance=alcance)
    if (t.requires_project or alcance == "project") and not proyecto_id:
        raise error(422, "dem_tipo_exige_proyecto")
    if proyecto_id:
        if proyectos_permitidos is not None and proyecto_id not in proyectos_permitidos:
            raise error(403, "dem_sin_acceso_proyecto")
        p = db.query(Project).filter(Project.id == proyecto_id).first()
        if p is None or (org_id and p.organization_id not in (org_id, None)):
            raise error(403, "dem_sin_acceso_proyecto")
    solicitante_id = None
    if actor.kind == "user":
        solicitante_id = actor.id
        if datos.get("requester_user_id") and datos["requester_user_id"] != actor.id:
            if not puede_gestionar(actor):
                raise error(403, "capacidad_requerida", capacidad="demanda.gestionar")
            solicitante_id = datos["requester_user_id"]
    with db.no_autoflush:
        codigo = next_numbered_code(db, "demand_request", prefix="DEM", padding=4)
    req = DemandRequest(
        organization_id=org_id, code=codigo, type_id=t.id, type_key=t.key, flow_id=flujo.id,
        flow_version=flujo.version, flow_snapshot=flujo.definition, origin=origen, title=titulo[:255],
        project_id=proyecto_id, standalone=not proyecto_id and alcance == "none", scope_kind=alcance,
        scope_ref_id=datos.get("scope_ref_id") or None,
        client_user_id=actor.id if actor.kind == "client" else None,
        client_id=getattr(actor.client, "client_org_id", None) if actor.kind == "client" else datos.get("client_id"),
        requester_user_id=solicitante_id, created_by_user_id=actor.id if actor.kind == "user" else None,
        status="draft", data="{}")
    db.add(req)
    db.flush()
    permitidos = ["title"] + [c["key"] for c in D.campos(D.cargar(flujo.definition))
                              if actor.kind == "user" or c.get("owner", "client") == "client"]
    _aplicar_datos(db, req, actor, datos.get("data") or {}, permitidos, "alta")
    registrar(db, req, actor, "create", estado_previo=None)
    db.commit()
    if datos.get("submit"):
        enviar(db, actor, req)
    return req


def editar(db: Session, actor: Actor, req, titulo: Optional[str], datos: dict, nota: Optional[str] = None) -> list:
    """Cambia la ficha. Commitea. Devuelve los campos cambiados."""
    permitidos = campos_editables(db, actor, req)
    if not permitidos:
        if es_solicitante(actor, req) and req.client_locked:
            raise error(409, "dem_ficha_bloqueada")
        raise error(403, "dem_campo_no_editable", campo="*")
    cambiados = []
    if titulo is not None and titulo.strip() and titulo.strip() != req.title:
        if "title" not in permitidos:
            raise error(403, "dem_campo_no_editable", campo="title")
        req.title = titulo.strip()[:255]
        cambiados.append("title")
    cambiados += _aplicar_datos(db, req, actor, datos or {}, permitidos, nota)
    if cambiados:
        from app.services.audit import audit_log
        audit_log(db, actor.user if actor.kind == "user" else None, "UPDATE_FIELDS", "demand_request", req.id,
                  req.code, new_values={"fields": cambiados, "phase": req.current_phase_key},
                  metadata={"actor_kind": actor.kind, "client_user_id": actor.id if actor.kind == "client" else None})
    db.commit()
    return cambiados


def enviar(db: Session, actor: Actor, req, nota: Optional[str] = None) -> None:
    """Envía un borrador (entra en la primera fase) o devuelve la información pedida."""
    if req.status == "pending_info":
        if not (es_solicitante(actor, req) or puede_gestionar(actor)):
            raise error(403, "dem_solo_solicitante")
        reanudar(db, req, actor, nota)
        db.commit()
        return
    if req.status != "draft":
        raise error(409, "dem_estado_no_permite", estado=req.status)
    if not (es_solicitante(actor, req) or (actor.kind == "user" and req.created_by_user_id == actor.id)):
        raise error(403, "dem_solo_solicitante")
    defn = flujo_de(req)
    faltan = D.faltan(datos_de(req), defn.get("submit_required") or [], req.title)
    if faltan:
        raise error(422, "dem_campos_obligatorios", campos=", ".join(faltan))
    if not D.fases(defn):
        raise error(409, "dem_tipo_sin_flujo")
    req.submitted_at = ahora()
    registrar(db, req, actor, "submit", estado_previo="draft")
    from app.services.demanda import avisos
    avisos.emitir(db, req, "submitted", None)
    entrar_en_fase(db, req, D.fases(defn)[0]["key"], actor, "enter")
    db.commit()


def retirar(db: Session, actor: Actor, req, motivo: Optional[str]) -> None:
    from app.services.demanda.motor import cerrar
    if req.status in CERRADOS:
        raise error(409, "dem_estado_no_permite", estado=req.status)
    if not es_solicitante(actor, req):
        raise error(403, "dem_solo_solicitante")
    cerrar(db, req, actor, "withdrawn", "withdraw", justificacion=(motivo or "").strip() or None)
    db.commit()


def comentar(db: Session, actor: Actor, req, cuerpo: str, interno: bool = False):
    from app.models.demanda import DemandComment
    from app.services.audit import audit_log
    cuerpo = (cuerpo or "").strip()
    if not cuerpo:
        raise error(422, "dem_comentario_vacio")
    if actor.kind == "client":
        interno = False
    c = DemandComment(organization_id=req.organization_id, request_id=req.id, phase_key=req.current_phase_key,
                      body=cuerpo[:10000], internal=bool(interno),
                      author_user_id=actor.id if actor.kind == "user" else None,
                      author_client_id=actor.id if actor.kind == "client" else None,
                      author_name=actor.nombre[:255] or None, created_at=ahora())
    db.add(c)
    audit_log(db, actor.user if actor.kind == "user" else None, "COMMENT", "demand_request", req.id, req.code,
              metadata={"internal": bool(interno), "actor_kind": actor.kind,
                        "client_user_id": actor.id if actor.kind == "client" else None})
    db.commit()
    return c
