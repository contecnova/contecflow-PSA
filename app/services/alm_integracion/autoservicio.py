"""«Mis equipos y licencias»: lo que cada persona tiene, pide, devuelve y firma.

Todo se acota a quien pregunta (titular persona = él): un empleado o un
subcontratado solo ve lo suyo. Pedir va al catálogo (`catalogo.pedir`),
devolver abre la devolución con su ticket (`bajas.abrir_devolucion`), una
avería abre un incidente enlazado al equipo y las actas se firman con
`alm_actas.firmar` (fase 1).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.alm import ALMActa, ALMAsignacion, ALMLicense
from app.models.alm_integracion import ALMDevolucion
from app.services.alm_integracion import _comun as c
from app.services.alm_integracion import bajas, catalogo

#: Urgencias que puede marcar la persona al comunicar una avería.
URGENCIAS = ("low", "medium", "high", "critical")


def _licencia(a: ALMAsignacion) -> dict:
    lic = a.license
    return {
        "assignment_id": a.id, "license_id": a.license_id, "name": lic.name if lic else None,
        "product_name": lic.product_name if lic else None, "edition": getattr(lic, "edition", None),
        "status": a.status, "mode": a.mode, "from_pool": bool(a.parent_id),
        "valid_from": a.valid_from.isoformat() if a.valid_from else None,
        "valid_to": a.valid_to.isoformat() if a.valid_to else None,
        "source": a.source,
    }


def _equipo(db: Session, a: ALMAsignacion, devoluciones: dict) -> dict:
    activo = a.asset
    hoy = c.hoy()
    dev = devoluciones.get(a.asset_id)
    return {
        "assignment_id": a.id, "asset_id": a.asset_id, "name": activo.name if activo else None,
        "type": getattr(activo.type, "value", activo.type) if activo else None,
        "brand": activo.brand if activo else None, "model": activo.model if activo else None,
        "asset_tag": activo.asset_tag if activo else None, "serial_number": activo.serial_number if activo else None,
        "mode": a.mode,
        "valid_from": a.valid_from.isoformat() if a.valid_from else None,
        "valid_to": a.valid_to.isoformat() if a.valid_to else None,
        "overdue": bool(a.mode == "loan" and a.valid_to and a.valid_to < hoy),
        "days_to_due": (a.valid_to - hoy).days if a.valid_to else None,
        "devolucion": bajas.serializar_devolucion(db, dev) if dev else None,
        "averias_abiertas": [t for t in c.tickets_del_recurso(db, c.ENLACE_ACTIVO, a.asset_id, solo_abiertos=True)
                             if t["ticket_type"] == "incident"],
        "acta_entrega": c.serializar_acta(c.ultima_acta(db, a.id, "delivery")),
    }


def mio(db: Session, user) -> dict:
    """La vista completa de la persona."""
    servicio = c.asignaciones()
    devoluciones = {d.asset_id: d for d in db.query(ALMDevolucion).filter(
        ALMDevolucion.user_id == user.id, ALMDevolucion.estado.in_(bajas.DEVOLUCION_ABIERTA))}
    for d in devoluciones.values():
        bajas.sincronizar(db, d)
    db.commit()
    licencias = [a for a in servicio.asignaciones_de_usuario(db, user.id) if a.resource_type == "license"]
    equipos = servicio.equipos_de_usuario(db, user.id)
    actas = db.query(ALMActa).filter(ALMActa.signer_user_id == user.id,
                                     ALMActa.status == "pending_signature").order_by(ALMActa.created_at).all()
    return {
        "licencias": [_licencia(a) for a in licencias],
        "equipos": [_equipo(db, a, devoluciones) for a in equipos],
        "actas_pendientes": [c.serializar_acta(a) for a in actas],
        "peticiones": catalogo.listar(db, user_id=user.id),
        "devoluciones": [bajas.serializar_devolucion(db, d) for d in db.query(ALMDevolucion)
                         .filter(ALMDevolucion.user_id == user.id)
                         .order_by(ALMDevolucion.created_at.desc()).all()],
        "historial": [_licencia(a) if a.resource_type == "license" else {
            "assignment_id": a.id, "asset_id": a.asset_id, "name": a.asset.name if a.asset else None,
            "status": a.status, "mode": a.mode, "end_kind": a.end_kind,
            "valid_from": a.valid_from.isoformat() if a.valid_from else None,
            "ended_on": a.ended_on.isoformat() if a.ended_on else None}
            for a in servicio.asignaciones_de_usuario(db, user.id, incluir_cerradas=True)
            if a.status in ("ended", "rejected", "cancelled")],
    }


def opciones_de_peticion(db: Session) -> dict:
    """Lo que se puede pedir: licencias (solo nombre y producto) y tipos de equipo
    que tienen ítem en el catálogo. Sin costes ni claves."""
    from app.models.alm_integracion import ALMItemDeCatalogo
    from app.services.alm_integracion.kits import TIPOS_DE_EQUIPO
    tipos = {m.tipo for m in db.query(ALMItemDeCatalogo).all()}
    licencias = []
    if "licencia" in tipos:
        licencias = [{"id": lic.id, "name": lic.name, "product_name": lic.product_name}
                     for lic in db.query(ALMLicense).filter(ALMLicense.is_active.is_(True))
                     .order_by(ALMLicense.name).all()
                     if getattr(lic.status, "value", lic.status) not in ("cancelled", "expired")]
    return {"puede_pedir_licencia": "licencia" in tipos, "puede_pedir_equipo": "equipo" in tipos,
            "licencias": licencias, "tipos_de_equipo": list(TIPOS_DE_EQUIPO) if "equipo" in tipos else []}


def _mia(db: Session, user, asignacion_id: str) -> ALMAsignacion:
    a = db.get(ALMAsignacion, asignacion_id)
    # Lo que no es suyo no existe (404, no 403: no confirmar que existe).
    c.exigir(a is not None and a.holder_user_id == user.id and a.status == "active",
             "almint_asignacion_no_encontrada", 404)
    return a


def devolver(db: Session, user, asignacion_id: str, motivo: Optional[str]) -> dict:
    """La persona avisa de que devuelve un equipo: devolución con ticket."""
    a = _mia(db, user, asignacion_id)
    c.exigir(a.resource_type == "asset", "almint_solo_equipos")
    d = bajas.abrir_devolucion(db, a, origen="autoservicio", actor=user, motivo=(motivo or "").strip() or None)
    db.commit()
    return bajas.serializar_devolucion(db, d)


def dejar_licencia(db: Session, user, asignacion_id: str, motivo: Optional[str]) -> dict:
    """La persona ya no necesita una licencia: vuelve a la bolsa o queda libre."""
    a = _mia(db, user, asignacion_id)
    c.exigir(a.resource_type == "license", "almint_solo_licencias")
    c.asignaciones().liberar(db, a.id, actor=user, motivo=(motivo or "").strip() or None,
                             tipo="released", origen="self_service")
    return {"ok": True}


def averia(db: Session, user, asignacion_id: str, descripcion: str, urgencia: str = "medium") -> dict:
    """Comunica una avería: incidente enlazado al equipo (y a su CI)."""
    a = _mia(db, user, asignacion_id)
    c.exigir(a.resource_type == "asset", "almint_solo_equipos")
    texto = (descripcion or "").strip()
    c.exigir(bool(texto), "almint_descripcion_obligatoria")
    c.exigir(urgencia in URGENCIAS, "almint_urgencia_invalida")
    activo = a.asset
    etiqueta = f" ({activo.asset_tag})" if activo.asset_tag else ""
    t = c.abrir_ticket(
        db, titulo=f"Avería: {activo.name}{etiqueta}", tipo="incident", urgencia=urgencia,
        descripcion=f"{texto}\n\nEquipo: {activo.name}{etiqueta}\nNúmero de serie: {activo.serial_number or '—'}",
        solicitante_id=user.id, grupo_ajuste="ALM_BREAKDOWN_GROUP_ID", org_id=activo.organization_id,
        enlace=(c.ENLACE_ACTIVO, activo.id), ci_id=activo.ci_id)
    from app.services.traduccion.textos_del_sistema import aplicar
    aplicar(db, t, "alm_breakdown", {"name": activo.name, "tag": activo.asset_tag, "serial": activo.serial_number,
                                     "text": texto})
    db.commit()
    return c.serializar_ticket(t)


def firmar_acta(db: Session, user, acta_id: str, ip: Optional[str]) -> dict:
    """Firma en la aplicación del acta de la persona (`alm_actas.firmar`)."""
    modulo = c.actas()
    c.exigir(modulo is not None, "almint_actas_no_disponibles", 409)
    acta = modulo.firmar(db, acta_id, user, ip=ip)
    for d in db.query(ALMDevolucion).filter(ALMDevolucion.acta_id == acta.id).all():
        bajas.sincronizar(db, d, user)
    db.commit()
    return modulo.serializar(db, acta)


def ver_acta(db: Session, user, acta_id: str) -> dict:
    modulo = c.actas()
    c.exigir(modulo is not None, "almint_actas_no_disponibles", 409)
    return modulo.serializar(db, modulo.acta_para(db, acta_id, user, es_gestor=False))
