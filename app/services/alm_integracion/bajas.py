"""Bajas: al desactivar a una persona (manual, SCIM, fin de contrato o baja
programada) se liberan sus licencias según la regla de la empresa y se abre la
devolución de cada equipo, con su ticket, hasta el acta de devolución firmada.

Regla de licencias (`ALM_OFFBOARDING_LICENSE_RELEASE_DAYS`): 0 las libera en
el momento; N las libera N días después de la fecha efectiva (el barrido
diario). Equipo sin devolver (`ALM_OFFBOARDING_PENDING_ASSETS`):

- ``avisar``: la baja sigue y se avisa al responsable;
- ``confirmar``: la desactivación manual exige confirmarlo (queda auditado);
- ``bloquear``: la desactivación manual se rechaza hasta que el equipo vuelva o
  se dé por perdido. SCIM y el fin de contrato nunca se bloquean: el proveedor
  de identidad y el contrato mandan; la baja queda «pendiente de devolución».

Nada aquí confirma salvo las acciones de endpoint (`*_confirmado`) y el
barrido diario; quien desactiva confirma con su propio commit.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMAsignacion, ALMAsset
from app.models.alm_integracion import ALMBaja, ALMDevolucion
from app.models.user import User, UserStatus
from app.services.alm_integracion import _comun as c

logger = logging.getLogger(__name__)

#: Estados de una baja que siguen abiertos.
ABIERTAS = ("programada", "pendiente_devolucion")
#: Estados de una devolución que aún esperan algo.
DEVOLUCION_ABIERTA = ("pendiente", "recibida")
#: Estados finales de una devolución.
DEVOLUCION_TERMINADA = ("cerrada", "perdida", "anulada")


# ── Lectura ───────────────────────────────────────────────────────────────────

def _equipos(db: Session, user_id: str) -> list[ALMAsignacion]:
    return c.asignaciones().equipos_de_usuario(db, user_id)


def _licencias(db: Session, user_id: str) -> list[ALMAsignacion]:
    return [a for a in c.asignaciones().asignaciones_de_usuario(db, user_id) if a.resource_type == "license"]


def previsualizar(db: Session, user: User) -> dict:
    """Lo que pasará al dar de baja a `user`: lo que se libera, lo que tiene que
    volver y qué dice la política de la empresa. Lo pinta la pantalla antes de
    confirmar la desactivación."""
    org = user.organization_id
    equipos = _equipos(db, user.id)
    abiertas = {d.asset_id for d in db.query(ALMDevolucion).filter(
        ALMDevolucion.user_id == user.id, ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA))}
    return {
        "user_id": user.id, "user_name": user.full_name,
        "politica": c.politica_de_pendientes(db, org),
        "dias_para_liberar": c.ajuste_int(db, "ALM_OFFBOARDING_LICENSE_RELEASE_DAYS", org),
        "licencias": [{"assignment_id": a.id, "license_id": a.license_id,
                       "name": a.license.name if a.license is not None else None,
                       "status": a.status} for a in _licencias(db, user.id)],
        "equipos": [{"assignment_id": a.id, "asset_id": a.asset_id,
                     "name": a.asset.name if a.asset is not None else None,
                     "asset_tag": a.asset.asset_tag if a.asset is not None else None,
                     "mode": a.mode, "valid_to": a.valid_to.isoformat() if a.valid_to else None,
                     "devolucion_abierta": a.asset_id in abiertas} for a in equipos],
        "baja_abierta": serializar_baja(db, baja_abierta(db, user.id), detalle=False),
    }


def baja_abierta(db: Session, user_id: str) -> Optional[ALMBaja]:
    return (db.query(ALMBaja).filter(ALMBaja.user_id == user_id, ALMBaja.estado.in_(ABIERTAS))
            .order_by(ALMBaja.created_at.desc()).first())


# ── Comprobación previa de una desactivación manual ───────────────────────────

def comprobar_desactivacion_manual(db: Session, user: User, confirmar: bool) -> None:
    """Aplica la política de equipo sin devolver a una desactivación manual.

    409 ``almint_baja_bloqueada`` (política bloquear) o
    ``almint_baja_requiere_confirmacion`` (política confirmar, sin confirmar).
    """
    if not _equipos(db, user.id):
        return
    politica = c.politica_de_pendientes(db, user.organization_id)
    if politica == "bloquear":
        raise ErrorDeDominio(409, "almint_baja_bloqueada")
    if politica == "confirmar" and not confirmar:
        raise ErrorDeDominio(409, "almint_baja_requiere_confirmacion")


# ── La baja ───────────────────────────────────────────────────────────────────

def al_dar_de_baja(db: Session, user: User, motivo: str, actor=None, *, fecha=None,
                   confirmada_con_pendientes: bool = False, notas: Optional[str] = None) -> ALMBaja:
    """Abre (o completa) el expediente de baja de `user`. No confirma.

    Idempotente: si ya hay una baja abierta (p. ej. programada), la usa.
    """
    c.exigir(motivo in ("manual", "scim", "fin_contrato", "programada"), "almint_motivo_invalido")
    org = user.organization_id
    with c.en_organizacion(db, org):
        dia = fecha or c.hoy()
        baja = baja_abierta(db, user.id)
        if baja is None:
            baja = ALMBaja(organization_id=org, user_id=user.id, motivo=motivo, fecha_efectiva=dia,
                           creada_por=getattr(actor, "id", None), notas=notas)
            db.add(baja)
        baja.estado = "pendiente_devolucion"
        baja.fecha_efectiva = min(baja.fecha_efectiva or dia, dia)
        baja.confirmada_con_pendientes = bool(baja.confirmada_con_pendientes or confirmada_con_pendientes)
        dias = c.ajuste_int(db, "ALM_OFFBOARDING_LICENSE_RELEASE_DAYS", org)
        baja.licencias_liberar_en = baja.fecha_efectiva + timedelta(days=dias)
        db.flush()

        if baja.licencias_liberar_en <= c.hoy():
            liberar_licencias(db, baja, actor)
        for a in _equipos(db, user.id):
            abrir_devolucion(db, a, origen="baja", actor=actor, baja=baja)
        db.flush()
        _avisar_baja(db, baja, user)
        from app.services.audit import audit_log
        audit_log(db, actor, "OFFBOARD", "alm_baja", baja.id, user.full_name,
                  new_values={"motivo": motivo, "fecha_efectiva": baja.fecha_efectiva,
                              "licencias_liberar_en": baja.licencias_liberar_en,
                              "confirmada_con_pendientes": baja.confirmada_con_pendientes})
        actualizar_estado(db, baja)
    return baja


def liberar_licencias(db: Session, baja: ALMBaja, actor=None) -> int:
    """Libera las licencias de la persona de la baja (asignaciones y pendientes).

    Se usa `liberar` asignación a asignación con ``commit=False`` y no
    `liberar_licencias_de_usuario` (que confirma): la baja va en la misma
    transacción que la desactivación, y si algo falla se deshace todo junto.
    """
    servicio = c.asignaciones()
    n = 0
    for a in _licencias(db, baja.user_id):
        servicio.liberar(db, a.id, actor=actor, motivo="Baja de la persona", tipo="released",
                         origen="offboarding", commit=False)
        n += 1
    baja.licencias_liberadas = (baja.licencias_liberadas or 0) + n
    baja.licencias_liberadas_en = timeutil.utcnow()
    return n


def _avisar_baja(db: Session, baja: ALMBaja, user: User) -> None:
    """Al responsable de la persona (o a los roles de respaldo) si queda equipo por volver."""
    pendientes = db.query(ALMDevolucion).filter(ALMDevolucion.baja_id == baja.id,
                                                ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA)).count()
    if not pendientes:
        return
    from app.services.notifications import notify_role, notify_user
    titulo = f"Baja de {user.full_name}: {pendientes} equipo(s) por devolver"
    cuerpo = "Se ha abierto un ticket de devolución por equipo; la baja sigue abierta hasta el acta firmada."
    url = "/alm/altas-y-bajas?tab=bajas"
    if user.manager_id:
        notify_user(db, user.manager_id, "alm_offboarding", titulo, cuerpo, "alm_baja", baja.id, url)
        return
    for rol in c.roles_de_respaldo(db, baja.organization_id):
        notify_role(db, rol, "alm_offboarding", titulo, cuerpo, "alm_baja", baja.id, url,
                    organization_id=baja.organization_id)


def actualizar_estado(db: Session, baja: ALMBaja) -> None:
    """Cierra la baja cuando no queda nada: licencias liberadas y devoluciones terminadas."""
    if baja.estado != "pendiente_devolucion":
        return
    # Sin autoflush en la sesión: la devolución que se acaba de cerrar
    # (`sincronizar`, `marcar_perdida`) aún no está en la base y contaría como abierta.
    db.flush()
    abiertas = db.query(ALMDevolucion).filter(ALMDevolucion.baja_id == baja.id,
                                              ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA)).count()
    if abiertas == 0 and baja.licencias_liberadas_en is not None:
        baja.estado = "cerrada"
        baja.cerrada_en = timeutil.utcnow()


# ── Bajas programadas ─────────────────────────────────────────────────────────

def programar_baja(db: Session, user_id: str, fecha, actor, motivo: str = "programada",
                   notas: Optional[str] = None) -> dict:
    """Deja la baja de una persona para una fecha (último día de contrato)."""
    from app.services.alm_asignaciones import _fecha
    user = db.query(User).filter(User.id == user_id).first()
    c.exigir(user is not None, "almint_persona_no_encontrada", 404)
    dia = _fecha(fecha, "fecha")
    c.exigir(dia is not None and dia >= c.hoy(), "almint_fecha_pasada")
    c.exigir(baja_abierta(db, user.id) is None, "almint_baja_ya_abierta", 409)
    baja = ALMBaja(organization_id=user.organization_id, user_id=user.id, motivo=motivo, estado="programada",
                   fecha_efectiva=dia, creada_por=getattr(actor, "id", None), notas=notas)
    db.add(baja)
    db.flush()
    from app.services.audit import audit_log
    audit_log(db, actor, "CREATE", "alm_baja", baja.id, user.full_name,
              new_values={"motivo": motivo, "fecha_efectiva": dia, "estado": "programada"})
    db.commit()
    return serializar_baja(db, baja)


def anular_baja(db: Session, baja_id: str, actor) -> dict:
    baja = db.get(ALMBaja, baja_id)
    c.exigir(baja is not None, "almint_baja_no_encontrada", 404)
    c.exigir(baja.estado == "programada", "almint_baja_no_anulable", 409)
    baja.estado = "anulada"
    baja.cerrada_en = timeutil.utcnow()
    from app.services.audit import audit_log
    audit_log(db, actor, "CANCEL", "alm_baja", baja.id)
    db.commit()
    return serializar_baja(db, baja)


def ejecutar_baja(db: Session, baja: ALMBaja, actor=None) -> None:
    """Desactiva a la persona de una baja programada o de un fin de contrato."""
    user = db.get(User, baja.user_id)
    if user is None:
        return
    user.is_active = False
    user.status = UserStatus.inactive
    al_dar_de_baja(db, user, baja.motivo, actor, fecha=baja.fecha_efectiva)


# ── Devoluciones ──────────────────────────────────────────────────────────────

def abrir_devolucion(db: Session, asignacion: ALMAsignacion, *, origen: str, actor=None,
                     baja: Optional[ALMBaja] = None, motivo: Optional[str] = None) -> ALMDevolucion:
    """La devolución de un equipo con su ticket. Idempotente por equipo."""
    existente = db.query(ALMDevolucion).filter(ALMDevolucion.asset_id == asignacion.asset_id,
                                               ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA)).first()
    if existente is not None:
        if baja is not None and existente.baja_id is None:
            existente.baja_id = baja.id
        return existente
    activo: ALMAsset = asignacion.asset
    persona = db.get(User, asignacion.holder_user_id) if asignacion.holder_user_id else None
    org = asignacion.organization_id
    dias = c.ajuste_int(db, "ALM_RETURN_DUE_DAYS", org)
    limite = (c.hoy() + timedelta(days=dias)) if dias > 0 else None
    etiqueta = f" ({activo.asset_tag})" if activo.asset_tag else ""
    nombre = persona.full_name if persona else "—"
    descripcion = (
        f"Devolución del equipo {activo.name}{etiqueta}.\n"
        f"Persona: {nombre}\nNúmero de serie: {activo.serial_number or '—'}\n"
        + (f"Fecha límite: {limite.isoformat()}\n" if limite else "")
        + (f"Motivo: {motivo}\n" if motivo else "")
        + ("Baja de la persona.\n" if origen == "baja" else "")
        + "Se cierra con el acta de devolución firmada."
    )
    ticket = c.abrir_ticket(
        db, titulo=f"Devolución de {activo.name}{etiqueta} — {nombre}", descripcion=descripcion,
        solicitante_id=getattr(actor, "id", None) or asignacion.holder_user_id,
        grupo_ajuste="ALM_RETURN_GROUP_ID", org_id=org, enlace=(c.ENLACE_ACTIVO, activo.id),
        ci_id=activo.ci_id,
    )
    from app.services.traduccion.textos_del_sistema import aplicar
    aplicar(db, ticket, "alm_return", {"name": activo.name, "tag": activo.asset_tag, "serial": activo.serial_number,
                                       "person": nombre, "due": limite.isoformat() if limite else None,
                                       "reason": motivo, "offboarding": "1" if origen == "baja" else None})
    dev = ALMDevolucion(organization_id=org, baja_id=baja.id if baja else None, asset_id=activo.id,
                        user_id=asignacion.holder_user_id, ticket_id=ticket.id, origen=origen,
                        estado="pendiente", fecha_limite=limite, notas=motivo,
                        solicitada_por=getattr(actor, "id", None))
    db.add(dev)
    db.flush()
    return dev


def _devolucion(db: Session, devolucion_id: str) -> ALMDevolucion:
    d = db.get(ALMDevolucion, devolucion_id)
    c.exigir(d is not None, "almint_devolucion_no_encontrada", 404)
    return d


def registrar_recepcion(db: Session, devolucion_id: str, actor, *, condition: Optional[str] = None,
                        checklist: Optional[list] = None, observations: Optional[str] = None,
                        a_reparar: bool = False) -> dict:
    """El equipo ha vuelto: devolución en ALM (acta de devolución) y seguimiento."""
    d = _devolucion(db, devolucion_id)
    c.exigir(d.estado == "pendiente", "almint_devolucion_no_pendiente", 409)
    asignacion = c.asignaciones().asignacion_vigente_de_activo(db, d.asset_id)
    if asignacion is not None and asignacion.status == "active":
        asignacion = c.asignaciones().devolver(db, asignacion.id, actor=actor, motivo=d.notas,
                                               checklist=checklist, condition=condition,
                                               observations=observations, a_reparar=a_reparar)
        acta = c.ultima_acta(db, asignacion.id, "return")
        d.acta_id = acta.id if acta is not None else None
    d = _devolucion(db, devolucion_id)
    d.estado = "recibida"
    d.condicion = condition
    d.recibida_en = timeutil.utcnow()
    d.recibida_por = getattr(actor, "id", None)
    sincronizar(db, d, actor)
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "alm_devolucion", d.id, new_values={"estado": d.estado, "condition": condition})
    db.commit()
    return serializar_devolucion(db, d)


def marcar_perdida(db: Session, devolucion_id: str, actor, motivo: str) -> dict:
    """El equipo no va a volver: se cierra su asignación como perdida."""
    d = _devolucion(db, devolucion_id)
    c.exigir(d.estado == "pendiente", "almint_devolucion_no_pendiente", 409)
    c.exigir(bool((motivo or "").strip()), "almint_motivo_obligatorio")
    asignacion = c.asignaciones().asignacion_vigente_de_activo(db, d.asset_id)
    if asignacion is not None:
        c.asignaciones().liberar(db, asignacion.id, actor=actor, motivo=motivo, tipo="lost",
                                 origen="offboarding" if d.origen == "baja" else "return", commit=False)
    d.estado = "perdida"
    d.notas = motivo
    d.cerrada_en = timeutil.utcnow()
    c.resolver_ticket(db, d.ticket_id, f"Equipo dado por perdido: {motivo}", getattr(actor, "id", None))
    if d.baja_id:
        actualizar_estado(db, db.get(ALMBaja, d.baja_id))
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "alm_devolucion", d.id, new_values={"estado": "perdida", "motivo": motivo})
    db.commit()
    return serializar_devolucion(db, d)


def sincronizar(db: Session, d: ALMDevolucion, actor=None) -> bool:
    """Pone la devolución al día con ALM. Devuelve si cambió.

    - pendiente → recibida: el equipo se devolvió por otro camino (la pantalla
      de ALM); se toma su acta de devolución.
    - recibida → cerrada: el acta de devolución está firmada (o no hay acta
      que firmar: actas desactivadas o sin firmante). Resuelve el ticket.
    """
    antes = d.estado
    if d.estado == "pendiente":
        vigente = c.asignaciones().asignacion_vigente_de_activo(db, d.asset_id)
        if vigente is None or vigente.holder_user_id != d.user_id:
            ultima = (db.query(ALMAsignacion).filter(ALMAsignacion.asset_id == d.asset_id,
                                                     ALMAsignacion.holder_user_id == d.user_id,
                                                     ALMAsignacion.status == "ended")
                      .order_by(ALMAsignacion.ended_at.desc()).first())
            acta = c.ultima_acta(db, ultima.id, "return") if ultima is not None else None
            d.acta_id = acta.id if acta is not None else d.acta_id
            d.estado = "recibida"
            d.recibida_en = d.recibida_en or timeutil.utcnow()
    if d.estado == "recibida":
        acta = c.acta_de(db, d.acta_id)
        if acta is None or acta.status in ("signed", "unsigned"):
            d.estado = "cerrada"
            d.cerrada_en = timeutil.utcnow()
            c.resolver_ticket(db, d.ticket_id, "Equipo devuelto" + (" con acta firmada" if acta else ""),
                              getattr(actor, "id", None))
    if d.estado != antes and d.baja_id:
        actualizar_estado(db, db.get(ALMBaja, d.baja_id))
    return d.estado != antes


# ── Barrido diario ────────────────────────────────────────────────────────────

def pasada_diaria(db: Session, org_id: Optional[str] = None) -> dict:
    """Bajas programadas que llegan, licencias cuyo plazo vence, fines de
    contrato de subcontratados y devoluciones al día. Confirma al final."""
    hoy = c.hoy()
    ejecutadas = liberadas = fines = cambios = 0
    for baja in db.query(ALMBaja).filter(ALMBaja.estado == "programada", ALMBaja.fecha_efectiva <= hoy).all():
        ejecutar_baja(db, baja)
        ejecutadas += 1
    for baja in db.query(ALMBaja).filter(ALMBaja.estado == "pendiente_devolucion",
                                         ALMBaja.licencias_liberadas_en.is_(None),
                                         ALMBaja.licencias_liberar_en <= hoy).all():
        liberadas += liberar_licencias(db, baja)
        actualizar_estado(db, baja)
    if c.ajuste_bool(db, "ALM_CONTRACT_END_OFFBOARDING", org_id):
        fines = _fines_de_contrato(db, hoy)
    for d in db.query(ALMDevolucion).filter(ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA)).all():
        cambios += int(sincronizar(db, d))
    db.commit()
    return {"bajas_ejecutadas": ejecutadas, "licencias_liberadas": liberadas,
            "fines_de_contrato": fines, "devoluciones_actualizadas": cambios}


def _fines_de_contrato(db: Session, hoy) -> int:
    """Subcontratados cuyo contrato (`available_until`) ya terminó y siguen activos."""
    from app.models.enterprise import SubcontractorWorker
    n = 0
    filas = (db.query(SubcontractorWorker, User).join(User, User.id == SubcontractorWorker.user_id)
             .filter(SubcontractorWorker.available_until.isnot(None),
                     SubcontractorWorker.available_until < hoy, User.is_active.is_(True)).all())
    for trabajador, user in filas:
        if baja_abierta(db, user.id) is not None:
            continue
        baja = ALMBaja(organization_id=user.organization_id, user_id=user.id, motivo="fin_contrato",
                       estado="programada", fecha_efectiva=trabajador.available_until)
        db.add(baja)
        db.flush()
        ejecutar_baja(db, baja)
        n += 1
    return n


# ── Listados ──────────────────────────────────────────────────────────────────

def listar_bajas(db: Session, estado: Optional[str] = None) -> list[dict]:
    q = db.query(ALMBaja)
    if estado:
        q = q.filter(ALMBaja.estado == estado)
    return [serializar_baja(db, b) for b in q.order_by(ALMBaja.created_at.desc()).all()]


def detalle_baja(db: Session, baja_id: str) -> dict:
    baja = db.get(ALMBaja, baja_id)
    c.exigir(baja is not None, "almint_baja_no_encontrada", 404)
    for d in db.query(ALMDevolucion).filter(ALMDevolucion.baja_id == baja.id,
                                            ALMDevolucion.estado.in_(DEVOLUCION_ABIERTA)).all():
        sincronizar(db, d)
    db.commit()
    return serializar_baja(db, baja, detalle=True)


def listar_devoluciones(db: Session, *, estado: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
    q = db.query(ALMDevolucion)
    if estado:
        q = q.filter(ALMDevolucion.estado == estado)
    if user_id:
        q = q.filter(ALMDevolucion.user_id == user_id)
    return [serializar_devolucion(db, d) for d in q.order_by(ALMDevolucion.created_at.desc()).all()]


def serializar_devolucion(db: Session, d: ALMDevolucion) -> dict:
    from app.models.service_desk import Ticket
    activo = db.get(ALMAsset, d.asset_id)
    persona = db.get(User, d.user_id) if d.user_id else None
    ticket = db.get(Ticket, d.ticket_id) if d.ticket_id else None
    hoy = c.hoy()
    return {
        "id": d.id, "baja_id": d.baja_id, "asset_id": d.asset_id,
        "asset_name": activo.name if activo else None, "asset_tag": activo.asset_tag if activo else None,
        "user_id": d.user_id, "user_name": persona.full_name if persona else None,
        "origen": d.origen, "estado": d.estado, "condicion": d.condicion, "notas": d.notas,
        "fecha_limite": d.fecha_limite.isoformat() if d.fecha_limite else None,
        "vencida": bool(d.estado == "pendiente" and d.fecha_limite and d.fecha_limite < hoy),
        "ticket": c.serializar_ticket(ticket) if ticket else None,
        "acta": c.serializar_acta(c.acta_de(db, d.acta_id)),
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "recibida_en": d.recibida_en.isoformat() if d.recibida_en else None,
        "cerrada_en": d.cerrada_en.isoformat() if d.cerrada_en else None,
    }


def serializar_baja(db: Session, baja: Optional[ALMBaja], detalle: bool = False) -> Optional[dict]:
    if baja is None:
        return None
    persona = db.get(User, baja.user_id)
    devs = db.query(ALMDevolucion).filter(ALMDevolucion.baja_id == baja.id).all()
    salida = {
        "id": baja.id, "user_id": baja.user_id, "user_name": persona.full_name if persona else None,
        "motivo": baja.motivo, "estado": baja.estado,
        "fecha_efectiva": baja.fecha_efectiva.isoformat() if baja.fecha_efectiva else None,
        "licencias_liberar_en": baja.licencias_liberar_en.isoformat() if baja.licencias_liberar_en else None,
        "licencias_liberadas_en": baja.licencias_liberadas_en.isoformat() if baja.licencias_liberadas_en else None,
        "licencias_liberadas": baja.licencias_liberadas or 0,
        "confirmada_con_pendientes": bool(baja.confirmada_con_pendientes),
        "devoluciones_total": len(devs),
        "devoluciones_pendientes": sum(1 for d in devs if d.estado in DEVOLUCION_ABIERTA),
        "notas": baja.notas,
        "created_at": baja.created_at.isoformat() if baja.created_at else None,
        "cerrada_en": baja.cerrada_en.isoformat() if baja.cerrada_en else None,
    }
    if detalle:
        salida["devoluciones"] = [serializar_devolucion(db, d) for d in devs]
        salida["licencias_vigentes"] = [
            {"assignment_id": a.id, "license_id": a.license_id,
             "name": a.license.name if a.license is not None else None}
            for a in _licencias(db, baja.user_id)]
    return salida


def previsualizar_persona(db: Session, user_id: str) -> dict:
    """`previsualizar` por id de persona; 404 si no existe (en la organización de quien pide)."""
    persona = db.query(User).filter(User.id == user_id).first()
    c.exigir(persona is not None, "almint_persona_no_encontrada", 404)
    return previsualizar(db, persona)
