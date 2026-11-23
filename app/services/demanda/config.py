"""Configuración del flujo de demanda: tipos de solicitud, flujos y catálogo de opciones.

Todo por empresa. Guardar un flujo con otra definición sube su `version`; los
expedientes en curso siguen con la foto de la versión con la que empezaron.
Cada cambio queda en el registro de auditoría (valores anteriores y nuevos).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.models.demanda import DemandRequestType
from app.models.project import Project


def _org(usuario) -> Optional[str]:
    return getattr(usuario, "organization_id", None)


def _jl(texto, defecto):
    try:
        return json.loads(texto) if texto else defecto
    except (TypeError, ValueError):
        return defecto


# ── Tipos ────────────────────────────────────────────────────────────────────

def tipo_dict(t, idioma: str = "es", flujos: Optional[dict] = None) -> dict:
    nombres = _jl(t.name_i18n, {})
    return {"id": t.id, "key": t.key, "name": D.nombre(nombres, idioma) or t.name, "name_i18n": nombres,
            "description": t.description, "channels": _jl(t.channels, []), "scopes": _jl(t.scopes, []),
            "requires_project": bool(t.requires_project), "allows_standalone": bool(t.allows_standalone),
            "flow_id": t.flow_id, "flow_name": (flujos or {}).get(t.flow_id), "sort_order": t.sort_order,
            "is_active": bool(t.is_active)}


def tipos(db: Session, usuario, idioma: str = "es", solo_activos: bool = False) -> list[dict]:
    from app.models.demanda import DemandFlow, DemandRequestType
    q = db.query(DemandRequestType).filter(DemandRequestType.organization_id == _org(usuario))
    if solo_activos:
        q = q.filter(DemandRequestType.is_active.is_(True))
    flujos = {f.id: f.name for f in db.query(DemandFlow).filter(DemandFlow.organization_id == _org(usuario)).all()}
    return [tipo_dict(t, idioma, flujos) for t in q.order_by(DemandRequestType.sort_order, DemandRequestType.name)]


def guardar_tipo(db: Session, usuario, datos: dict, tipo_id: Optional[str] = None) -> dict:
    from app.models.demanda import DemandFlow, DemandRequestType
    from app.services.audit import audit_log
    org = _org(usuario)
    if tipo_id:
        t = db.query(DemandRequestType).filter(DemandRequestType.id == tipo_id,
                                               DemandRequestType.organization_id == org).first()
        if t is None:
            raise error(404, "dem_tipo_no_encontrado")
        previo = tipo_dict(t)
    else:
        if not datos.get("key"):
            raise error(422, "campo_obligatorio", campo="key")
        t = DemandRequestType(organization_id=org)
        previo = None
    if "key" in datos and datos["key"] != t.key:
        if db.query(DemandRequestType.id).filter(DemandRequestType.organization_id == org,
                                                 DemandRequestType.key == datos["key"],
                                                 DemandRequestType.id != (t.id or "")).first():
            raise error(409, "dem_tipo_clave_duplicada", clave=datos["key"])
        t.key = datos["key"]
    if datos.get("flow_id") and not db.query(DemandFlow.id).filter(DemandFlow.id == datos["flow_id"],
                                                                    DemandFlow.organization_id == org).first():
        raise error(404, "dem_flujo_no_encontrado")
    for campo in ("description", "requires_project", "allows_standalone", "flow_id", "sort_order", "is_active"):
        if campo in datos:
            setattr(t, campo, datos[campo])
    if "name_i18n" in datos and isinstance(datos["name_i18n"], dict):
        t.name_i18n = json.dumps(datos["name_i18n"], ensure_ascii=False)
    if datos.get("name") or (isinstance(datos.get("name_i18n"), dict) and datos["name_i18n"].get(IDIOMA_DE_RESPALDO)):
        t.name = (datos.get("name") or datos["name_i18n"][IDIOMA_DE_RESPALDO])[:200]
    if not t.name:
        t.name = t.key
    if "channels" in datos:
        t.channels = json.dumps([c for c in datos["channels"] or [] if c in D.CANALES])
    if "scopes" in datos:
        t.scopes = json.dumps([c for c in datos["scopes"] or [] if c in D.ALCANCES])
    if t.id is None:
        db.add(t)
    db.flush()
    audit_log(db, usuario, "UPDATE" if previo else "CREATE", "demand_request_type", t.id, t.key,
              old_values=previo, new_values=tipo_dict(t))
    db.commit()
    return tipo_dict(t)


# ── Flujos ───────────────────────────────────────────────────────────────────

def flujo_dict(f, con_definicion: bool = False) -> dict:
    d = {"id": f.id, "key": f.key, "name": f.name, "description": f.description, "version": f.version,
         "is_active": bool(f.is_active), "updated_at": f.updated_at or f.created_at}
    if con_definicion:
        d["definition"] = D.cargar(f.definition)
    return d


def flujos(db: Session, usuario) -> list[dict]:
    from app.models.demanda import DemandFlow
    return [flujo_dict(f) for f in db.query(DemandFlow).filter(DemandFlow.organization_id == _org(usuario))
            .order_by(DemandFlow.name).all()]


def flujo(db: Session, usuario, flujo_id: str):
    from app.models.demanda import DemandFlow
    f = db.query(DemandFlow).filter(DemandFlow.id == flujo_id, DemandFlow.organization_id == _org(usuario)).first()
    if f is None:
        raise error(404, "dem_flujo_no_encontrado")
    return f


def guardar_flujo(db: Session, usuario, datos: dict, flujo_id: Optional[str] = None) -> dict:
    from app.models.demanda import DemandFlow
    from app.services.audit import audit_log
    if "definition" in datos:
        errores = D.validar(datos["definition"])
        if errores:
            raise error(422, "dem_definicion_invalida", n=len(errores), errors=json.dumps(errores[:50]))
    if flujo_id:
        f = flujo(db, usuario, flujo_id)
        previo = {"version": f.version, "name": f.name, "is_active": f.is_active}
    else:
        if "definition" not in datos:
            raise error(422, "campo_obligatorio", campo="definition")
        f = DemandFlow(organization_id=_org(usuario), version=0, created_by=usuario.id)
        db.add(f)
        previo = None
    for campo in ("name", "description", "is_active", "key"):
        if campo in datos and datos[campo] is not None:
            setattr(f, campo, datos[campo])
    if not f.name:
        raise error(422, "campo_obligatorio", campo="name")
    if "definition" in datos:
        nueva = json.dumps(datos["definition"], ensure_ascii=False, sort_keys=True)
        if f.definition is None or json.dumps(D.cargar(f.definition), ensure_ascii=False, sort_keys=True) != nueva:
            f.definition = json.dumps(datos["definition"], ensure_ascii=False)
            f.version = (f.version or 0) + 1
    f.updated_by = usuario.id
    db.flush()
    audit_log(db, usuario, "UPDATE" if previo else "CREATE", "demand_flow", f.id, f.name, old_values=previo,
              new_values={"version": f.version, "name": f.name, "is_active": f.is_active})
    db.commit()
    return flujo_dict(f, True)


# ── Catálogo para el configurador ────────────────────────────────────────────

def catalogo(db: Session, usuario, idioma: str = "es") -> dict:
    from app.core.capacidades import ETIQUETAS_DE_ROL, ROLES
    from app.models.billing_reports import ApprovalGroup, ApprovalWorkflow
    from app.models.user import User
    org = _org(usuario)
    grupos = db.query(ApprovalGroup).filter(ApprovalGroup.organization_id == org).order_by(ApprovalGroup.name).all()
    flujos_ = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.organization_id == org,
                                                ApprovalWorkflow.is_active.is_(True)).order_by(ApprovalWorkflow.name)
    usuarios = db.query(User).filter(User.organization_id == org, User.is_active.is_(True)).order_by(User.full_name)
    from app.services.demanda import biblioteca
    return {
        "assignee_types": list(D.TIPOS_DE_ASIGNADO), "decisions": list(D.DECISIONES),
        "phase_kinds": list(D.FASES_KIND), "field_types": list(D.TIPOS_DE_CAMPO),
        "document_tags": list(D.ETIQUETAS_DE_DOCUMENTO), "notify_events": list(D.EVENTOS),
        "notify_targets": list(D.DESTINOS_DE_AVISO), "condition_ops": list(D.OPERADORES),
        "quorums": list(D.QUORUMS), "step_modes": list(D.MODOS_DE_PASO),
        "execution_modes": list(D.MODOS_DE_EJECUCION), "close_actions": list(D.ACCIONES),
        "channels": list(D.CANALES), "scopes": list(D.ALCANCES),
        "roles": [{"value": r, "label": ETIQUETAS_DE_ROL.get(r, {}).get(idioma, r)} for r in ROLES],
        "groups": [{"value": g.id, "label": g.name} for g in grupos],
        "users": [{"value": u.id, "label": u.full_name or u.email} for u in usuarios.limit(500)],
        "approval_workflows": [{"value": w.id, "label": w.name} for w in flujos_],
        "templates": biblioteca.listar(idioma),
    }


def tipos_de_flujo(db: Session, flujo) -> list:
    """Tipos de solicitud que cuelgan de un flujo."""
    return db.query(DemandRequestType).filter(DemandRequestType.flow_id == flujo.id).all()


def proyectos_de_la_organizacion(db: Session, org_id, limite: int = 500) -> list:
    """Proyectos de la empresa (id y nombre) para el selector de la solicitud."""
    return [{"id": p.id, "name": p.name} for p in db.query(Project).filter(
        Project.organization_id == org_id).order_by(Project.name).limit(limite).all()]


def proyecto_por_id(db: Session, project_id: str):
    return db.query(Project).filter(Project.id == project_id).first()
