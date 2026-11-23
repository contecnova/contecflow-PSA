"""Peticiones RGPD: alta, borrado y portabilidad.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.cab import GDPRRequest
from app.models.cab import GDPRRequestType, GDPRRequestStatus
from app.models.imputation import Imputation as Imp
from app.models.user import User as UserModel
from app.services.audit import audit_log
from app.core import timeutil
from app.core.paginacion import Pagina, Paginacion, paginar
from app.core.codigos_de_error import error


# ─── GDPR ─────────────────────────────────────────────────────────────────────

def _de_la_empresa(db: Session, org):
    q = db.query(GDPRRequest)
    return q.filter(GDPRRequest.organization_id == org) if org else q


def list_gdpr_requests(db: Session, pagina: Optional[Paginacion] = None, org: Optional[str] = None) -> Pagina:
    q = _de_la_empresa(db, org).options(
        joinedload(GDPRRequest.subject_user),
        joinedload(GDPRRequest.processor),
    ).order_by(GDPRRequest.created_at.desc(), GDPRRequest.id)
    # Revisión GRC 16-11-2026: `subject_name` llevaba «Usuario eliminado» escrito
    # en castellano; ahora va vacío y `subject_deleted` lo dice (la interfaz lo
    # traduce). `has_export` permite descargar el resultado de acceso/portabilidad.
    return paginar(q, pagina, "gdpr.requests").mapear(lambda r: {
        "id": r.id, "request_type": getattr(r.request_type, "value", r.request_type),
        "status": getattr(r.status, "value", r.status),
        "subject_email": r.subject_email or (r.subject_user.email if r.subject_user else None),
        "subject_name": r.subject_user.full_name if r.subject_user else None,
        "subject_deleted": r.subject_user is None,
        "deadline": str(r.deadline) if r.deadline else None,
        "completed_at": str(r.completed_at)[:10] if r.completed_at else None,
        "processor": r.processor.full_name if r.processor else None,
        "created_at": str(r.created_at)[:10] if r.created_at else None,
        "notes": r.notes,
        "has_export": _tipo(r) in _CON_COPIA and r.status == GDPRRequestStatus.completed and bool(r.export_data)
                      and not _copia_caducada(db, r),
    })


# ── Copia de los datos: cifrada y con caducidad (auditoría 22-11-2026, A64) ──
#
# `export_data` guardaba la copia de los datos personales EN CLARO y para
# siempre. Ahora se guarda cifrada (`encrypt_value`, la clave de la plataforma)
# y caduca a los `COMPLIANCE_GDPR_EXPORT_TTL_DAYS` días de completarse: al
# pedirla caducada se borra y responde 410; el barrido diario
# (`purgar_copias_caducadas`) las borra aunque nadie las pida.

def _ttl_de_copia(db: Session, org) -> int:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "COMPLIANCE_GDPR_EXPORT_TTL_DAYS", org)
               or settings.COMPLIANCE_GDPR_EXPORT_TTL_DAYS)


def _copia_caducada(db: Session, req) -> bool:
    if not req.completed_at:
        return False
    fin = req.completed_at if req.completed_at.tzinfo else req.completed_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > fin + timedelta(days=_ttl_de_copia(db, req.organization_id))


def _guardar_copia(req, datos: dict) -> None:
    from app.core.encryption import encrypt_value
    req.export_data = encrypt_value(json.dumps(datos, default=str))


def _leer_copia(req) -> dict:
    from app.core.encryption import decrypt_value
    crudo = req.export_data or ""
    if not crudo.lstrip().startswith("{"):
        crudo = decrypt_value(crudo) or "{}"
    return json.loads(crudo)


def purgar_copias_caducadas(db: Session, org: Optional[str] = None) -> int:
    """Borra las copias RGPD caducadas de la empresa `org` (barrido diario de
    retención, `app.worker.aplicar_retencion`)."""
    n = 0
    q = db.query(GDPRRequest).filter(GDPRRequest.export_data.isnot(None), GDPRRequest.completed_at.isnot(None))
    if org:
        q = q.filter(GDPRRequest.organization_id == org)
    for req in q.all():
        if _copia_caducada(db, req):
            req.export_data = None
            n += 1
    if n:
        db.commit()
    return n


#: Tipos cuyo resultado es una copia de los datos de la persona (art. 15 y 20).
_CON_COPIA = (GDPRRequestType.access, GDPRRequestType.portability)


def _tipo(req) -> GDPRRequestType:
    return GDPRRequestType(getattr(req.request_type, "value", req.request_type))


def _sujeto(db: Session, user_id: Optional[str], org: Optional[str]):
    """La persona, si es de la empresa (o None)."""
    from app.db.session import _miembros_de
    if not user_id:
        return None
    q = db.query(UserModel).filter(UserModel.id == user_id)
    return (q.filter(_miembros_de(UserModel, org)) if org else q).first()


def _plazo(db: Session, org) -> int:
    """Plazo legal en días: `COMPLIANCE_GDPR_MAX_DAYS` (el mismo que mide el informe)."""
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "COMPLIANCE_GDPR_MAX_DAYS", org) or settings.COMPLIANCE_GDPR_MAX_DAYS)


def create_gdpr_request(payload, current_user, db: Session) -> dict:
    """Alta de una solicitud RGPD.

    Revisión GRC 16-11-2026: el plazo era 30 días escrito aquí (el ajuste
    `COMPLIANCE_GDPR_MAX_DAYS` sólo lo leía el informe), la persona podía ser
    de otra empresa y la empresa de la solicitud dependía del sellado de la
    sesión.
    """
    org = current_user.organization_id
    if payload.subject_user_id and _sujeto(db, payload.subject_user_id, org) is None:
        raise error(404, "persona_no_existe_en_empresa_rgpd")
    deadline = timeutil.today() + timedelta(days=_plazo(db, org))
    req = GDPRRequest(
        organization_id=org,
        request_type=payload.request_type,
        subject_user_id=payload.subject_user_id or None,
        subject_email=payload.subject_email or None,
        requestor_id=current_user.id,
        notes=payload.notes,
        deadline=deadline,
    )
    db.add(req)
    audit_log(db, current_user, "GDPR_REQUEST", "users",
              payload.subject_user_id or "unknown",
              payload.subject_email or "",
              new_values={"type": getattr(payload.request_type, "value", payload.request_type)})
    db.commit()
    return {"ok": True, "id": req.id, "deadline": str(deadline)}


def _gdpr_erase_user(db: Session, user) -> dict:
    """Supresión de una persona (el mismo borrado que Gobierno del dato). No guarda su correo original."""
    from app.services.supresion_service import suprimir_persona
    detalle = suprimir_persona(db, user)
    # Migracion 189: su ficha de persona externa (y la de proveedor si es freelance).
    from app.services.proveedores.grc import suprimir as suprimir_ficha_de_proveedor
    detalle["tablas"]["proveedor"] = suprimir_ficha_de_proveedor(db, user)
    return {"anonymised": True, "tablas": detalle["tablas"], "credenciales": detalle["credenciales"],
            "almacen": detalle["almacen"], "meetings": detalle.get("reuniones"), "records_kept": ["imputations", "timesheets", "expenses", "overtime_requests"]}


def _gdpr_portability_export(db: Session, user) -> dict:
    """Copia de los datos de la persona (art. 15 acceso y art. 20 portabilidad).

    Revisión GRC 16-11-2026: era un resumen (perfil y NÚMERO de imputaciones)
    con la nota «Solicite el fichero completo al administrador del sistema»,
    cuando quien procesa la solicitud ES el administrador. Ahora lleva sus
    imputaciones y los tickets que abrió, y se descarga desde la solicitud.
    """
    from app.models.service_desk.tickets import Ticket
    imputaciones = db.query(Imp).filter(Imp.user_id == user.id).order_by(Imp.date, Imp.id).all()
    tickets = db.query(Ticket).filter(Ticket.requester_user_id == user.id).order_by(Ticket.created_at).all()
    # 18-11-2026: sus horas extra (pedidas, declaradas, decididas, compensadas) con su línea de tiempo.
    from app.services.horas_extra.consultas import mis_datos as horas_extra_de
    horas_extra = horas_extra_de(db, user.id)
    # 19-11-2026: sus reuniones (como asistente o hablante): lo que dijo, su
    # consentimiento y sus acciones (`app/services/reuniones/rgpd.py`).
    from app.services.reuniones import rgpd as rgpd_reuniones
    reuniones = rgpd_reuniones.copia(db, None, user_id=user.id, email=user.email)
    return {
        "meetings": reuniones["meetings"],
        "user": {
            "email": user.email, "full_name": user.full_name,
            "username": user.username, "role": getattr(user.role, "value", user.role),
            "department": user.department,
            "created_at": str(user.created_at)[:10] if user.created_at else None,
        },
        "imputations": [{"date": str(i.date), "hours": i.hours, "project_id": i.project_id,
                         "task_id": i.task_id, "description": i.description} for i in imputaciones],
        "tickets": [{"number": t.number, "title": t.title, "status": str(getattr(t.status, "value", t.status)),
                     "created_at": str(t.created_at)[:19] if t.created_at else None} for t in tickets],
        "overtime_requests": horas_extra,
        # Migracion 189: si es persona externa (o freelance), su ficha de proveedor y accesos.
        "supplier": _datos_de_proveedor(db, user),
        # 23-11-2026: su seguridad de cuenta (sin contraseñas, hashes ni secretos).
        "account_security": _seguridad_de_cuenta(db, user),
        # Migracion 200: sus llamadas al agente de voz (por la huella de su telefono).
        "voice_sessions": _sesiones_de_voz(db, user),
        "data_summary": {"imputations": len(imputaciones), "tickets": len(tickets),
                         "overtime_requests": len(horas_extra), "meetings": reuniones["meetings_count"]},
        "export_date": str(timeutil.today()),
        "format": "JSON",
    }


def _sesiones_de_voz(db: Session, user):
    from app.services.service_desk.voice_agent_service import copia_rgpd
    return copia_rgpd(db, getattr(user, "phone", None), getattr(user, "organization_id", None))


def _seguridad_de_cuenta(db: Session, user):
    from app.services.seguridad_de_cuentas.rgpd import copia
    return copia(db, user)


def _datos_de_proveedor(db: Session, user):
    from app.services.proveedores.grc import datos_personales
    return datos_personales(db, user)


def _de_la_empresa_o_404(db: Session, request_id: str, org):
    req = _de_la_empresa(db, org).filter(GDPRRequest.id == request_id).first()
    if not req:
        raise error(404, "no_encontrado", detail="Solicitud no encontrada", que="solicitud")
    return req


def process_gdpr_request(request_id: str, current_user, db: Session) -> dict:
    org = current_user.organization_id
    req = _de_la_empresa_o_404(db, request_id, org)
    if req.status in (GDPRRequestStatus.completed, GDPRRequestStatus.rejected):
        raise error(409, "solicitud_ya_cerrada")

    tipo = _tipo(req)
    user = _sujeto(db, req.subject_user_id, org)
    # Revisión GRC 16-11-2026: con la persona apuntada pero fuera de la empresa
    # (o borrada a mano), la solicitud se daba por completada sin hacer nada.
    if req.subject_user_id and user is None:
        raise error(404, "rgpd_persona_ya_no_existe")
    # 18-11-2026: la persona también puede ser contacto de un cliente o usuario
    # de su portal (sin cuenta en la aplicación): se le identifica por su email.
    from app.services import datos_personales_de_contactos as contactos_rgpd
    email = (user.email if user else None) or req.subject_email
    es_contacto = bool(contactos_rgpd.contactos_de(db, email, org) or contactos_rgpd.usuarios_del_portal_de(db, email, org))
    # 19-11-2026: también quien solo fue asistente o hablante de una reunión (sin cuenta).
    from app.services.reuniones import rgpd as rgpd_reuniones
    en_reuniones = bool(user is None and email and rgpd_reuniones.hay_datos(db, org, None, email))
    if tipo in _CON_COPIA and user is None and not es_contacto and not en_reuniones:
        raise error(422, "rgpd_sin_persona")
    if tipo == GDPRRequestType.erasure:
        # Segunda auditoría 2026-11: bajo bloqueo legal, 409 antes de marcarla en curso.
        if user:
            from app.services.supresion_service import exigir_sin_bloqueo_legal
            exigir_sin_bloqueo_legal(db, user)
        if es_contacto:
            contactos_rgpd.exigir_sin_bloqueo_legal(db, email, org)

    # A64: todo en UNA transacción. Antes se confirmaba «processing» y, si la
    # supresión fallaba a medias, la solicitud quedaba atascada en curso con
    # parte de los datos anonimizados. Ahora, si algo falla, se deshace todo y
    # la solicitud sigue como estaba.
    req.status = GDPRRequestStatus.processing
    req.processed_by = current_user.id
    try:
        export_data = _ejecutar_solicitud(db, req, tipo, user, email, es_contacto, en_reuniones, org)
    except Exception:
        db.rollback()
        raise

    req.status = GDPRRequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    _guardar_copia(req, export_data)
    audit_log(db, current_user, "GDPR_PROCESS", "users",
              req.subject_user_id or "unknown", "",
              new_values={"type": tipo.value, "result": req.status.value})
    db.commit()
    return {"ok": True, "status": req.status.value, "data": export_data}


def _ejecutar_solicitud(db: Session, req, tipo, user, email, es_contacto: bool, en_reuniones: bool, org) -> dict:
    from app.services import datos_personales_de_contactos as contactos_rgpd
    from app.services.reuniones import rgpd as rgpd_reuniones
    export_data: dict = {}
    if tipo == GDPRRequestType.erasure and (user or es_contacto or en_reuniones):
        # Primero sus fichas de contacto (con el email original), luego la cuenta.
        contactos_suprimidos = contactos_rgpd.anonimizar(db, email, org) if es_contacto else None
        reuniones_suprimidas = rgpd_reuniones.suprimir(db, org, email=email) if en_reuniones else None
        export_data = _gdpr_erase_user(db, user) if user else {"anonymised": True}
        if contactos_suprimidos is not None:
            export_data["client_contacts"] = contactos_suprimidos
        if reuniones_suprimidas is not None:
            export_data["meetings"] = reuniones_suprimidas
    elif tipo in _CON_COPIA:
        # Revisión GRC 16-11-2026: «acceso» (art. 15) se marcaba completada sin
        # entregar nada; da la misma copia que la portabilidad.
        export_data = _gdpr_portability_export(db, user) if user else {
            "export_date": str(timeutil.today()), "format": "JSON"}
        if es_contacto:
            export_data.update(contactos_rgpd.copia(db, email, org))
        if en_reuniones:
            export_data["meetings"] = rgpd_reuniones.copia(db, org, email=email)["meetings"]
    elif tipo == GDPRRequestType.rectification:
        # La rectificación la hace una persona en la ficha: aquí se deja
        # constancia de quién la confirma.
        export_data = {"rectification": "confirmed_by_processor"}
    return export_data


def reject_gdpr_request(request_id: str, motivo: str, current_user, db: Session) -> dict:
    """Rechazo motivado (art. 12.4). Revisión GRC 16-11-2026: el estado existía y nada lo ponía."""
    req = _de_la_empresa_o_404(db, request_id, current_user.organization_id)
    if req.status in (GDPRRequestStatus.completed, GDPRRequestStatus.rejected):
        raise error(409, "solicitud_ya_cerrada")
    req.status = GDPRRequestStatus.rejected
    req.processed_by = current_user.id
    req.completed_at = datetime.now(timezone.utc)
    req.notes = (req.notes + "\n" if req.notes else "") + motivo
    audit_log(db, current_user, "GDPR_REJECT", "users", req.subject_user_id or "unknown", "",
              new_values={"type": _tipo(req).value, "reason": motivo})
    db.commit()
    return {"ok": True, "status": req.status.value}


def export_of_gdpr_request(request_id: str, current_user, db: Session) -> dict:
    """La copia generada al procesar una solicitud de acceso o portabilidad."""
    req = _de_la_empresa_o_404(db, request_id, current_user.organization_id)
    if _tipo(req) not in _CON_COPIA or req.status != GDPRRequestStatus.completed or not req.export_data:
        raise error(404, "rgpd_sin_copia")
    if _copia_caducada(db, req):
        req.export_data = None
        db.commit()
        raise error(410, "rgpd_copia_caducada", dias=_ttl_de_copia(db, req.organization_id))
    audit_log(db, current_user, "EXPORT", "gdpr_request", req.id, "gdpr export",
              metadata={"type": _tipo(req).value})
    db.commit()
    return _leer_copia(req)
