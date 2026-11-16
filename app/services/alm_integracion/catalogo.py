"""Pedir licencia o equipo desde el catálogo del service desk.

Un ítem del catálogo es «de ALM» si tiene fila en `alm_items_de_catalogo`
(tipo licencia o equipo y, opcionalmente, la licencia o el tipo de equipo
concretos). Su petición:

1. nace como ticket por el camino normal del service desk (SLA, enrutado y, si
   el ítem la pide, la aprobación del propio catálogo); los datos de la
   petición viajan en los campos dinámicos del ticket (`alm_*`), así que vale
   igual desde «Mis equipos y licencias» que desde el portal;
2. la aprobación es la del catálogo en modo ``engine``: varios niveles en el
   motor común de aprobaciones (tipo ``catalog_request``, flujos diseñados en
   Aprobaciones y el motor de políticas, dominio ``catalogo``). Los ítems que
   crea `crear_items` nacen así; uno marcado a mano usa la aprobación que
   tenga configurada en el catálogo. Rechazada, el catálogo cancela el ticket;
3. cuando el catálogo la da por buena (`fulfillment_service.crear_tareas`:
   aprobada, o sin aprobación), alta automática en ALM con
   `alm_asignaciones.asignar` (de la bolsa del proyecto o del almacén) o, si no
   queda, petición de compra.

Ticket y recurso quedan enlazados en los dos sentidos
(`Ticket.linked_resource_type/_id` y `tickets_del_recurso`).

Los pasos ``assign_license`` / ``revoke_license`` del aprovisionamiento del
catálogo actualizan ALM (`paso_de_catalogo`) y, si el paso trae ``url``,
también llaman al sistema externo como antes.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.alm import ALMAsignacion, ALMLicense
from app.models.alm_integracion import TIPOS_DE_ELEMENTO, ALMItemDeCatalogo, ALMPeticion
from app.models.user import User
from app.services.alm_integracion import _comun as c
from app.services.alm_integracion import _suministro as s

logger = logging.getLogger(__name__)

#: Campos dinámicos del ticket con los datos de la petición.
CAMPOS = ("alm_tipo", "alm_license_id", "alm_asset_type", "alm_beneficiario_id", "alm_project_id",
          "alm_motivo", "alm_hasta")

#: Estados desde los que se puede (re)intentar el cumplimiento.
CUMPLIBLE = ("pendiente", "en_compra", "error")


# ── Ítems del catálogo que son de ALM ─────────────────────────────────────────

def item_de(db: Session, service_item_id: Optional[str]) -> Optional[ALMItemDeCatalogo]:
    if not service_item_id:
        return None
    return db.query(ALMItemDeCatalogo).filter(ALMItemDeCatalogo.service_item_id == service_item_id).first()


def listar_items(db: Session) -> list[dict]:
    from app.models.service_desk import ServiceItem
    salida = []
    for m in db.query(ALMItemDeCatalogo).all():
        item = db.get(ServiceItem, m.service_item_id)
        lic = db.get(ALMLicense, m.license_id) if m.license_id else None
        salida.append({"id": m.id, "service_item_id": m.service_item_id,
                       "service_item_name": item.name if item else None,
                       "service_item_active": bool(item and item.is_active),
                       "requires_catalog_approval": bool(item and item.requires_approval),
                       "approval": ("none" if not (item and item.requires_approval)
                                    else getattr(item, "approval_mode", None) or "single"),
                       "tipo": m.tipo, "license_id": m.license_id, "license_name": lic.name if lic else None,
                       "asset_type": m.asset_type})
    return salida


def guardar_item(db: Session, datos: dict, actor) -> dict:
    from app.models.service_desk import ServiceItem
    from app.services.alm_integracion.kits import TIPOS_DE_EQUIPO
    item = db.get(ServiceItem, datos.get("service_item_id"))
    c.exigir(item is not None, "almint_item_no_encontrado", 404)
    tipo = datos.get("tipo")
    c.exigir(tipo in TIPOS_DE_ELEMENTO, "almint_tipo_invalido")
    license_id = datos.get("license_id") or None
    asset_type = datos.get("asset_type") or None
    if tipo == "licencia":
        asset_type = None
        if license_id:
            c.exigir(db.get(ALMLicense, license_id) is not None, "almint_licencia_no_encontrada", 404)
    else:
        license_id = None
        c.exigir(asset_type is None or asset_type in TIPOS_DE_EQUIPO, "almint_tipo_de_equipo_invalido")
    m = item_de(db, item.id) or ALMItemDeCatalogo(organization_id=item.organization_id, service_item_id=item.id)
    m.tipo, m.license_id, m.asset_type = tipo, license_id, asset_type
    db.add(m)
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "alm_item_de_catalogo", item.id, item.name,
              new_values={"tipo": tipo, "license_id": license_id, "asset_type": asset_type})
    db.commit()
    return next(i for i in listar_items(db) if i["service_item_id"] == item.id)


def borrar_item(db: Session, mapeo_id: str, actor) -> dict:
    m = db.get(ALMItemDeCatalogo, mapeo_id)
    c.exigir(m is not None, "almint_item_no_encontrado", 404)
    db.delete(m)
    from app.services.audit import audit_log
    audit_log(db, actor, "DELETE", "alm_item_de_catalogo", mapeo_id)
    db.commit()
    return {"ok": True}


def crear_items(db: Session, category_id: str, nombres: dict, actor) -> list[dict]:
    """Crea en una categoría los ítems «Pedir licencia» y «Pedir equipo» (con los
    nombres que manda la interfaz, en el idioma de quien los crea) y los marca
    como de ALM. Nacen con la aprobación de varios niveles del motor común
    (modo ``engine`` del catálogo; el flujo se elige por condiciones entre los
    de ``catalog_request``)."""
    from app.models.service_desk import ServiceCategory, ServiceItem
    cat = db.get(ServiceCategory, category_id)
    c.exigir(cat is not None, "almint_categoria_no_encontrada", 404)
    for tipo in TIPOS_DE_ELEMENTO:
        nombre = ((nombres or {}).get(tipo) or "").strip()
        c.exigir(bool(nombre), "almint_nombre_obligatorio")
        item = ServiceItem(organization_id=cat.organization_id, category_id=cat.id, name=nombre[:255],
                           ticket_type="service_request", is_active=True, is_visible_to_clients=False,
                           requires_approval=True, approval_mode="engine")
        db.add(item)
        db.flush()
        db.add(ALMItemDeCatalogo(organization_id=cat.organization_id, service_item_id=item.id, tipo=tipo))
    from app.services.audit import audit_log
    audit_log(db, actor, "CREATE", "alm_item_de_catalogo", category_id, cat.name)
    db.commit()
    return listar_items(db)


# ── La petición ───────────────────────────────────────────────────────────────

def _elegir_item(db: Session, tipo: str, license_id: Optional[str], asset_type: Optional[str]) -> ALMItemDeCatalogo:
    """El ítem más concreto: el de esa licencia o tipo de equipo; si no, el genérico."""
    from app.models.service_desk import ServiceItem
    candidatos = [m for m in db.query(ALMItemDeCatalogo).filter(ALMItemDeCatalogo.tipo == tipo).all()
                  if (lambda i: i is not None and i.is_active)(db.get(ServiceItem, m.service_item_id))]
    for m in candidatos:
        if (tipo == "licencia" and license_id and m.license_id == license_id) or \
           (tipo == "equipo" and asset_type and m.asset_type == asset_type):
            return m
    genericos = [m for m in candidatos if not m.license_id and not m.asset_type]
    c.exigir(bool(genericos), "almint_catalogo_sin_item", 409)
    return genericos[0]


def pedir(db: Session, actor, datos: dict) -> dict:
    """«Pedir licencia» o «Pedir equipo» desde Mis equipos y licencias: crea el
    ticket del ítem del catálogo, que sigue su camino (aprobación y cumplimiento)."""
    from app.services.alm_integracion.kits import TIPOS_DE_EQUIPO
    tipo = datos.get("tipo")
    c.exigir(tipo in TIPOS_DE_ELEMENTO, "almint_tipo_invalido")
    license_id = datos.get("license_id") or None
    asset_type = datos.get("asset_type") or None
    if tipo == "licencia":
        lic = db.query(ALMLicense).filter(ALMLicense.id == license_id, ALMLicense.is_active.is_(True)).first()
        c.exigir(lic is not None, "almint_licencia_no_encontrada", 404)
        que = lic.name
    else:
        c.exigir(asset_type in TIPOS_DE_EQUIPO, "almint_tipo_de_equipo_invalido")
        que = asset_type
    beneficiario_id = datos.get("beneficiario_id") or actor.id
    if beneficiario_id != actor.id:
        # Pedir para otra persona: su responsable o un gestor de ALM.
        otro = db.query(User).filter(User.id == beneficiario_id, User.is_active.is_(True)).first()
        c.exigir(otro is not None, "almint_persona_no_encontrada", 404)
        rol = getattr(actor.role, "value", actor.role)
        c.exigir(otro.manager_id == actor.id or rol in ("admin", "hr") or actor.is_superadmin,
                 "almint_sin_permiso", 403)
    project_id = datos.get("project_id") or None
    if project_id:
        from app.services.politica_de_visibilidad import exigir_proyecto_visible
        exigir_proyecto_visible(db, actor, project_id)
    mapeo = _elegir_item(db, tipo, license_id, asset_type)
    motivo = (datos.get("motivo") or "").strip()
    campos = {"alm_tipo": tipo, "alm_license_id": license_id, "alm_asset_type": asset_type,
              "alm_beneficiario_id": beneficiario_id, "alm_project_id": project_id,
              "alm_motivo": motivo or None, "alm_hasta": datos.get("hasta") or None}
    ticket = c.abrir_ticket(
        db, titulo=f"Petición: {que}", descripcion=motivo or f"Petición de {que}",
        solicitante_id=actor.id, org_id=actor.organization_id, service_item_id=mapeo.service_item_id,
        project_id=project_id, campos={k: v for k, v in campos.items() if v is not None},
        enlace=(c.ENLACE_LICENCIA, license_id) if license_id else None)
    from app.services.traduccion.textos_del_sistema import aplicar
    aplicar(db, ticket, "alm_request", {"item": que, "reason": motivo or None})
    p = registrar(db, ticket, campos)
    db.commit()
    return serializar(db, p)


def registrar(db: Session, ticket, campos: Optional[dict] = None) -> Optional[ALMPeticion]:
    """La petición del ticket (idempotente). Sin datos propios toma los del ítem."""
    existente = db.query(ALMPeticion).filter(ALMPeticion.ticket_id == ticket.id).first()
    if existente is not None:
        return existente
    mapeo = item_de(db, ticket.service_item_id)
    if mapeo is None:
        return None
    if campos is None:
        from app.services.service_desk.dynamic_ticket_fields_service import get_ticket_dynamic_fields
        campos = {k: v for k, v in (get_ticket_dynamic_fields(db, ticket.id) or {}).items() if k in CAMPOS}
    p = ALMPeticion(
        organization_id=ticket.organization_id, ticket_id=ticket.id, tipo=mapeo.tipo,
        beneficiario_id=campos.get("alm_beneficiario_id") or ticket.requester_user_id,
        solicitante_id=ticket.requester_user_id or ticket.created_by_user_id,
        license_id=campos.get("alm_license_id") or mapeo.license_id,
        asset_type=campos.get("alm_asset_type") or mapeo.asset_type,
        project_id=campos.get("alm_project_id") or ticket.project_id,
        motivo=campos.get("alm_motivo") or None,
        detalle=json.dumps({"hasta": campos.get("alm_hasta")}) if campos.get("alm_hasta") else None,
    )
    db.add(p)
    db.flush()
    return p


def al_cumplir_peticion(db: Session, ticket, item) -> None:
    """Gancho de `fulfillment_service.crear_tareas`: el catálogo da la petición
    por buena (aprobada por el motor común, o sin aprobación). Si es de ALM, se
    da de alta en ALM o se pide la compra. No confirma: confirma quien crea o
    decide el ticket."""
    if item is None or item_de(db, item.id) is None:
        return
    p = registrar(db, ticket)
    if p is None or p.estado != "pendiente":
        return
    cumplir(db, p, None)


def resumen(db: Session, p: ALMPeticion) -> str:
    persona = db.get(User, p.beneficiario_id) if p.beneficiario_id else None
    if p.tipo == "licencia":
        lic = db.get(ALMLicense, p.license_id) if p.license_id else None
        que = f"Licencia {lic.name if lic else '—'}"
    else:
        que = f"Equipo {p.asset_type or '—'}"
    return f"{que} para {persona.full_name if persona else '—'}" + (f" — {p.motivo}" if p.motivo else "")


def cumplir(db: Session, p: ALMPeticion, actor) -> dict:
    """Alta en ALM: asignar de la bolsa o del almacén, o pedir compra. No confirma."""
    c.exigir(p.estado in CUMPLIBLE, "almint_peticion_no_cumplible", 409)
    c.exigir(bool(p.beneficiario_id), "almint_persona_no_encontrada", 404)
    hasta = c.json_o(p.detalle, {}).get("hasta") if p.detalle else None
    motivo = f"Catálogo: {p.motivo}" if p.motivo else "Catálogo"
    if p.tipo == "licencia":
        r = s.dar_licencia(db, actor=actor, user_id=p.beneficiario_id, license_id=p.license_id,
                           org_id=p.organization_id, project_id=p.project_id, source="catalog",
                           reason=motivo, origen_ticket_id=p.ticket_id)
    else:
        r = s.dar_equipo(db, actor=actor, user_id=p.beneficiario_id, asset_type=p.asset_type,
                         org_id=p.organization_id, project_id=p.project_id, source="catalog",
                         reason=motivo, origen_ticket_id=p.ticket_id, valid_to=hasta)
    actor_id = getattr(actor, "id", None)
    if r["resultado"] in ("asignada", "asignado"):
        p.estado = "cumplida"
        p.asignacion_id = r["assignment_id"]
        p.asset_id = r.get("asset_id")
        p.cumplida_en = timeutil.utcnow()
        if p.license_id:
            c.enlazar_ticket(db, p.ticket_id, c.ENLACE_LICENCIA, p.license_id)
        c.resolver_ticket(db, p.ticket_id, "Alta automática en el inventario: " + resumen(db, p), actor_id)
    elif r["resultado"] == "compra":
        p.estado = "en_compra"
        p.compra_ticket_id = r["ticket_id"]
    else:
        p.estado = "error"
        p.detalle = json.dumps({**c.json_o(p.detalle, {}), "error": r.get("codigo")})
    return r


def reintentar(db: Session, peticion_id: str, actor) -> dict:
    """Tras recibir la compra (o corregir un error): vuelve a intentar el alta."""
    p = db.get(ALMPeticion, peticion_id)
    c.exigir(p is not None, "almint_peticion_no_encontrada", 404)
    c.exigir(p.estado in ("en_compra", "error"), "almint_peticion_no_cumplible", 409)
    p.estado = "pendiente"
    cumplir(db, p, actor)
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "alm_peticion", p.id, new_values={"estado": p.estado})
    db.commit()
    return serializar(db, p)


def _registrar_pendientes(db: Session, user_id: Optional[str]) -> None:
    """Las peticiones hechas desde el portal se registran al cumplirse; para
    verlas antes (mientras se aprueban) se registran al listarlas."""
    from app.models.service_desk import Ticket
    items = [m.service_item_id for m in db.query(ALMItemDeCatalogo).all()]
    if not items:
        return
    q = db.query(Ticket).filter(Ticket.service_item_id.in_(items),
                                ~Ticket.id.in_(db.query(ALMPeticion.ticket_id)))
    if user_id:
        q = q.filter(Ticket.requester_user_id == user_id)
    nuevas = [registrar(db, t) for t in q.all()]
    if any(nuevas):
        db.commit()


def _al_dia(db: Session, p: ALMPeticion, t) -> None:
    """Una petición cuyo ticket se canceló (rechazo de la aprobación) queda rechazada."""
    if p.estado == "pendiente" and t is not None and getattr(t.status, "value", t.status) == "cancelled":
        p.estado = "rechazada"


def listar(db: Session, *, user_id: Optional[str] = None, estado: Optional[str] = None) -> list[dict]:
    _registrar_pendientes(db, user_id)
    q = db.query(ALMPeticion)
    if user_id:
        q = q.filter((ALMPeticion.beneficiario_id == user_id) | (ALMPeticion.solicitante_id == user_id))
    if estado:
        q = q.filter(ALMPeticion.estado == estado)
    salida = [serializar(db, p) for p in q.order_by(ALMPeticion.created_at.desc()).all()]
    if db.dirty:
        db.commit()  # `_al_dia` pudo marcar rechazadas
    return salida


def serializar(db: Session, p: ALMPeticion) -> dict:
    from app.models.service_desk import Ticket
    t = db.get(Ticket, p.ticket_id)
    _al_dia(db, p, t)
    compra = db.get(Ticket, p.compra_ticket_id) if p.compra_ticket_id else None
    lic = db.get(ALMLicense, p.license_id) if p.license_id else None
    persona = db.get(User, p.beneficiario_id) if p.beneficiario_id else None
    return {
        "id": p.id, "tipo": p.tipo, "estado": p.estado,
        "aprobacion": getattr(t, "approval_status", None) if t else None,
        "license_id": p.license_id, "license_name": lic.name if lic else None, "asset_type": p.asset_type,
        "asset_id": p.asset_id, "project_id": p.project_id, "motivo": p.motivo,
        "beneficiario_id": p.beneficiario_id, "beneficiario_name": persona.full_name if persona else None,
        "ticket": c.serializar_ticket(t) if t else None,
        "compra": c.serializar_ticket(compra) if compra else None,
        "error": (c.json_o(p.detalle, {}) or {}).get("error") if p.detalle else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "cumplida_en": p.cumplida_en.isoformat() if p.cumplida_en else None,
    }


# ── Pasos assign_license / revoke_license del aprovisionamiento ───────────────

def paso_de_catalogo(db: Session, step: dict, ticket, actor) -> dict:
    """Ejecuta un paso ``assign_license`` o ``revoke_license`` contra ALM y, si
    el paso trae ``url``, también contra el sistema externo (como antes).

    La licencia sale del paso (``license_id``), de la petición del ticket o de
    sus campos dinámicos; la persona, de la petición o del solicitante.
    """
    tipo = str(step.get("type") or "").lower()
    p = registrar(db, ticket)
    license_id = step.get("license_id") or (p.license_id if p else None)
    persona = (p.beneficiario_id if p else None) or ticket.requester_user_id
    salida: dict = {"type": tipo, "provider": "alm", "ok": False}
    if not license_id or not persona:
        salida["error"] = "almint_paso_sin_licencia_o_persona"
    elif tipo == "assign_license":
        r = s.dar_licencia(db, actor=actor, user_id=persona, license_id=license_id, org_id=ticket.organization_id,
                           project_id=ticket.project_id, source="catalog",
                           reason=f"Catálogo: ticket {ticket.number}", origen_ticket_id=ticket.id)
        salida.update(ok=r["resultado"] == "asignada", alm=r)
        if r["resultado"] == "asignada":
            c.enlazar_ticket(db, ticket.id, c.ENLACE_LICENCIA, license_id)
    else:
        abiertas = db.query(ALMAsignacion).filter(
            ALMAsignacion.license_id == license_id, ALMAsignacion.holder_user_id == persona,
            ALMAsignacion.status.in_(("active", "pending"))).all()
        for a in abiertas:
            c.asignaciones().liberar(db, a.id, actor=actor, motivo=f"Catálogo: ticket {ticket.number}",
                                     tipo="revoked", origen="catalog", commit=False)
        salida.update(ok=True, alm={"resultado": "liberadas", "n": len(abiertas)})
        c.enlazar_ticket(db, ticket.id, c.ENLACE_LICENCIA, license_id)
    if step.get("url"):
        from app.services.service_desk.smart_catalog_service import _render_context
        from app.services import bookings_service as externo
        cfg = {**step, "operation": tipo}
        try:
            fuera = externo._execute_provision_action(cfg, _render_context(ticket, actor, ticket.service_item_id))
            salida["external"] = {k: fuera.get(k) for k in ("ok", "status_code", "operation")}
            salida["status_code"] = fuera.get("status_code")
            salida["ok"] = bool(salida["ok"] and fuera.get("ok"))
        except Exception as exc:  # el sistema externo no deshace lo hecho en ALM
            logger.warning("paso %s: fallo del sistema externo", tipo, exc_info=True)
            salida["external"] = {"ok": False, "error": str(exc)}
            salida["ok"] = False
    return salida
