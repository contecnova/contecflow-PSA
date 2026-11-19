"""Documentos de una ausencia durante toda su vida: requisitos, plazos, subida y acceso.

- Cada documento tiene tipo y versión y se puede sustituir (la versión
  anterior queda «sustituida», no se borra). Lo suben la persona, RRHH, su
  responsable o un administrador.
- El fichero va al almacén de documentos de siempre (`s3_service.file_storage`:
  S3 o disco), con la misma validación de subida (`core.uploads`) y el mismo
  antivirus (`collaboration._storage.scan_with_av`); se descarga con un enlace
  firmado de corta duración. No hay otro almacén.
- Requisitos (`requisitos_de_ausencia`): los que pide el tipo (con su plazo
  desde la petición, el inicio o el fin; los que se repiten cada N días, como
  el parte de confirmación de una baja), los que pide una política
  (`require_attachment` con tipos de documento de ausencia) y los que pide a
  mano RRHH o el responsable. La pasada diaria recuerda antes de vencer, marca
  los vencidos y escala a quien diga el tipo.
- Categoría especial (RGPD art. 9: salud): si el tipo de documento o el tipo de
  ausencia lo es, el contenido solo lo ven la persona, RRHH y quien esté en la
  lista de acceso especial (un administrador, solo si está en ella). Cada
  vista, descarga o intento denegado queda en `document_access_logs` y en el
  registro de auditoría. Retención y bloqueo legal: tipo `absence_documents`
  de `app/db/bloqueo_legal.py`.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.ausencias import (DocumentoDeAusencia, RequisitoDeAusencia, RequisitoDocumentalDeTipo,
                                  TipoDeDocumentoDeAusencia)
from app.models.resources import Absence, AbsenceStatus
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def _rol(u) -> str:
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _evento(db, a, tipo, actor_id=None, **datos):
    from app.services.ausencias.solicitudes import evento
    evento(db, a, tipo, actor_id, **datos)


# ── Requisitos ───────────────────────────────────────────────────────────────

def tipos_de_politica(db: Session, ev: Optional[dict]) -> list[TipoDeDocumentoDeAusencia]:
    """Los tipos de documento que piden las políticas (`require_attachment`)."""
    claves = {c for r in ((ev or {}).get("resultado") or {}).get("requisitos") or []
              if r.get("tipo") == "require_attachment" for c in r.get("tipos_de_documento") or []}
    if not claves:
        return []
    return db.query(TipoDeDocumentoDeAusencia).filter(TipoDeDocumentoDeAusencia.clave.in_(claves)).all()


def _base(regla: RequisitoDocumentalDeTipo, a: Absence) -> date:
    if regla.plazo_desde == "solicitud":
        return (a.requested_at or _ahora()).date() if isinstance(a.requested_at, datetime) else timeutil.today()
    return a.end_date if regla.plazo_desde == "fin" else a.start_date


def crear_requisitos(db: Session, a: Absence, tipo, ev: Optional[dict]) -> int:
    """Los requisitos que faltan: uno por regla del tipo y uno por tipo de
    documento que pida una política. No duplica los que ya existen. No confirma."""
    existentes = db.query(RequisitoDeAusencia).filter(RequisitoDeAusencia.absence_id == a.id).all()
    por_regla = {r.regla_id for r in existentes if r.regla_id}
    por_tipo = {r.tipo_id for r in existentes if r.estado in ("pendiente", "entregado", "vencido")}
    n = 0
    for regla in tipo.requisitos or []:
        if regla.id in por_regla or not regla.obligatorio:
            continue
        db.add(RequisitoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id,
                                   tipo_id=regla.tipo_de_documento_id, regla_id=regla.id, origen="tipo", secuencia=1,
                                   vence=_base(regla, a) + timedelta(days=int(regla.plazo_dias or 0)), estado="pendiente"))
        por_tipo.add(regla.tipo_de_documento_id)
        n += 1
    for t in tipos_de_politica(db, ev):
        if t.id in por_tipo:
            continue
        db.add(RequisitoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id,
                                   tipo_id=t.id, origen="politica", secuencia=1, vence=timeutil.today(),
                                   estado="pendiente"))
        n += 1
    return n


def pedir(db: Session, usuario, a: Absence, tipo_id: str, vence, nota: Optional[str]) -> dict:
    """RRHH o el responsable piden otro documento (un informe distinto, un parte más)."""
    exigir_gestion(db, usuario, a)
    t = db.query(TipoDeDocumentoDeAusencia).filter(TipoDeDocumentoDeAusencia.id == tipo_id).first()
    if t is None:
        raise error(422, "elige_tipo_de_documento")
    try:
        fecha = vence if isinstance(vence, date) else date.fromisoformat(str(vence)[:10])
    except (TypeError, ValueError):
        raise error(422, "fecha_no_valida", detail="Fecha límite no válida")
    previos = db.query(RequisitoDeAusencia).filter(RequisitoDeAusencia.absence_id == a.id,
                                                   RequisitoDeAusencia.tipo_id == t.id).count()
    r = RequisitoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id, tipo_id=t.id,
                            origen="manual", secuencia=previos + 1, vence=fecha, estado="pendiente",
                            nota=(nota or None) and nota[:500], pedido_por=usuario.id)
    db.add(r)
    _evento(db, a, "documento_pedido", usuario.id, documento=t.nombre, vence=fecha)
    from app.services.ausencias.solicitudes import avisar
    avisar(db, [a.user_id], "Te piden un documento", f"{t.nombre} antes del {fecha.isoformat()}"
           + (f" — {nota}" if nota else ""), a)
    db.commit()
    return requisito_dict(r)


def dispensar(db: Session, usuario, a: Absence, requisito_id: str, nota: Optional[str]) -> dict:
    exigir_gestion(db, usuario, a)
    r = db.query(RequisitoDeAusencia).filter(RequisitoDeAusencia.id == requisito_id,
                                             RequisitoDeAusencia.absence_id == a.id).first()
    if r is None:
        raise error(404, "no_encontrado", detail="Requisito no encontrado", que="requisito")
    r.estado, r.nota = "dispensado", (nota or r.nota)
    _evento(db, a, "documento_dispensado", usuario.id, documento=r.tipo.nombre if r.tipo else None, nota=nota)
    db.commit()
    return requisito_dict(r)


def requisito_dict(r: RequisitoDeAusencia) -> dict:
    return {"id": r.id, "tipo_id": r.tipo_id, "tipo": r.tipo.nombre if r.tipo else None, "origen": r.origen,
            "secuencia": r.secuencia, "vence": r.vence.isoformat(), "estado": r.estado, "nota": r.nota,
            "recordado_en": r.recordado_en.isoformat() if r.recordado_en else None,
            "escalado_en": r.escalado_en.isoformat() if r.escalado_en else None}


# ── Quién puede qué ──────────────────────────────────────────────────────────

def _es_responsable(db: Session, usuario, a: Absence) -> bool:
    from app.services.approval_engine._base import responsable_de_nivel
    for nivel in (1, 2, 3):
        jefe = responsable_de_nivel(db, a.user_id, nivel)
        if jefe is None:
            return False
        if jefe == usuario.id:
            return True
    return False


def _es_aprobador(db: Session, usuario, a: Absence) -> bool:
    from app.services.politicas.servicio import _es_aprobador as aprobador
    from app.services.politicas import catalogo
    return aprobador(db, usuario, catalogo.dominio("ausencias"), a.id)


def exigir_gestion(db: Session, usuario, a: Absence) -> None:
    """RRHH, administrador o responsable (hasta 3 niveles) de la persona."""
    if usuario.is_superadmin or _rol(usuario) in ("admin", "hr") or _es_responsable(db, usuario, a):
        return
    raise error(403, "solo_rrhh_admin_o_responsable")


def especial(a: Absence, doc: DocumentoDeAusencia) -> bool:
    return bool(doc.especial or (doc.tipo and doc.tipo.categoria_especial)
                or (a.absence_type and a.absence_type.datos_especiales))


def puede_ver(db: Session, usuario, a: Absence, doc: DocumentoDeAusencia) -> bool:
    """El contenido. Categoría especial: la persona, RRHH y la lista de acceso
    especial (nadie más, tampoco un administrador que no esté). Lo demás:
    además quien lo subió, administradores, responsables y quien la aprueba."""
    from app.services.ausencias.catalogo import tiene_acceso_especial
    if usuario.id == a.user_id:
        return True
    if especial(a, doc):
        return tiene_acceso_especial(db, usuario)
    return (usuario.id == doc.subido_por or usuario.is_superadmin or _rol(usuario) in ("admin", "hr")
            or _es_responsable(db, usuario, a) or _es_aprobador(db, usuario, a))


def puede_subir(db: Session, usuario, a: Absence) -> bool:
    return usuario.id == a.user_id or usuario.is_superadmin or _rol(usuario) in ("admin", "hr") \
        or _es_responsable(db, usuario, a)


# ── Subir ────────────────────────────────────────────────────────────────────

def subir(db: Session, usuario, a: Absence, *, tipo_id: str, nombre: str, content_type: str, contenido: bytes,
          sustituye_a: Optional[str] = None, nota: Optional[str] = None, ip: Optional[str] = None) -> dict:
    from app.core.config import settings
    from app.core.uploads import validate_upload
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.audit import audit_log
    from app.services.collaboration._storage import scan_with_av
    from app.services.s3_service import file_storage
    from app.services.settings_service import get_runtime_int
    if not puede_subir(db, usuario, a):
        raise error(403, "adjuntar_solo_persona_rrhh_responsable_admin")
    if a.status == AbsenceStatus.cancelled:
        raise error(400, "ausencia_cancelada")
    tipo = db.query(TipoDeDocumentoDeAusencia).filter(TipoDeDocumentoDeAusencia.id == tipo_id).first()
    if tipo is None:
        raise error(422, "elige_tipo_de_documento")
    maximo = (get_runtime_int(db, "MAX_FILE_SIZE_MB", a.organization_id) or settings.MAX_FILE_SIZE_MB) * 1024 * 1024
    if len(contenido) > maximo:
        raise error(413, "fichero_demasiado_grande", detail=f"El archivo supera el máximo de {maximo // (1024 * 1024)} MB", max=maximo // (1024 * 1024))
    validate_upload(nombre or "", content_type or "", contenido)
    av, detalle = scan_with_av(contenido)
    if av == "infected":
        audit_log(db, usuario, "UPLOAD_BLOCKED", "absence_document", a.id, nombre, metadata={"antivirus": detalle})
        db.commit()
        raise error(422, "antivirus_bloqueado")
    previo = None
    if sustituye_a:
        previo = db.query(DocumentoDeAusencia).filter(DocumentoDeAusencia.id == sustituye_a,
                                                      DocumentoDeAusencia.absence_id == a.id).first()
        if previo is None:
            raise error(404, "no_encontrado", detail="El documento a sustituir no existe", que="documento")
    version = (previo.version + 1) if previo else 1
    doc = Document(id=str(uuid.uuid4()), organization_id=a.organization_id,
                   title=f"{tipo.nombre} · {a.start_date}"[:255], category=DocumentCategory.other,
                   created_by=usuario.id, description=None)
    db.add(doc)
    clave, tamano = file_storage.upload_file(file_content=contenido, file_name=nombre or "documento",
                                             document_id=doc.id, version_num=version,
                                             content_type=content_type or "application/octet-stream")
    try:
        db.add(DocumentVersion(id=str(uuid.uuid4()), organization_id=a.organization_id, document_id=doc.id,
                               version_num=1, file_key=clave, file_name=(nombre or "documento")[:255],
                               file_size=tamano, file_mime_type=content_type, change_note=nota, created_by=usuario.id))
        fila = DocumentoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id,
                                   user_id=a.user_id, tipo_id=tipo.id, document_id=doc.id, version=version,
                                   estado="vigente", sustituye_a=previo.id if previo else None,
                                   especial=bool(tipo.categoria_especial or (a.absence_type and a.absence_type.datos_especiales)),
                                   nota=(nota or None) and nota[:500], subido_por=usuario.id)
        if previo is not None:
            previo.estado = "sustituido"
        req = db.query(RequisitoDeAusencia).filter(
            RequisitoDeAusencia.absence_id == a.id, RequisitoDeAusencia.tipo_id == tipo.id,
            RequisitoDeAusencia.estado.in_(("pendiente", "vencido"))).order_by(RequisitoDeAusencia.vence).first()
        if req is not None:
            req.estado = "entregado"
            fila.requisito_id = req.id
        db.add(fila)
        _evento(db, a, "documento", usuario.id, documento=tipo.nombre, version=version, sustituye=bool(previo),
                requisito=req.id if req else None)
        audit_log(db, usuario, "CREATE", "absence_document", fila.id, tipo.nombre, ip_address=ip,
                  metadata={"absence_id": a.id, "version": version, "special_category": fila.especial,
                            "antivirus": av})
        db.commit()
    except Exception:
        db.rollback()
        try:
            file_storage.delete_file(clave)
        except Exception:
            logger.warning("no se pudo borrar el fichero huérfano %s", clave, exc_info=True)
        raise
    if usuario.id != a.user_id:
        from app.services.ausencias.solicitudes import avisar
        avisar(db, [a.user_id], "Documento añadido a tu ausencia", f"{tipo.nombre} (v{version})", a)
        db.commit()
    return documento_dict(db, usuario, a, fila)


def documento_dict(db: Session, usuario, a: Absence, d: DocumentoDeAusencia) -> dict:
    ver = puede_ver(db, usuario, a, d)
    version = (d.documento.versions or [None])[0] if d.documento else None
    return {"id": d.id, "tipo_id": d.tipo_id, "tipo": d.tipo.nombre if d.tipo else None, "version": d.version,
            "estado": d.estado, "sustituye_a": d.sustituye_a, "especial": especial(a, d), "puede_ver": ver,
            "nombre_de_fichero": version.file_name if (ver and version) else None,
            "tamano": version.file_size if (ver and version) else None, "nota": d.nota if ver else None,
            "subido_por": d.subido_por, "subido_en": d.subido_en.isoformat() if d.subido_en else None}


def listar(db: Session, usuario, a: Absence) -> dict:
    docs = db.query(DocumentoDeAusencia).filter(DocumentoDeAusencia.absence_id == a.id) \
        .order_by(DocumentoDeAusencia.subido_en.desc()).all()
    reqs = db.query(RequisitoDeAusencia).filter(RequisitoDeAusencia.absence_id == a.id) \
        .order_by(RequisitoDeAusencia.vence).all()
    return {"documentos": [documento_dict(db, usuario, a, d) for d in docs],
            "requisitos": [requisito_dict(r) for r in reqs], "puede_subir": puede_subir(db, usuario, a)}


def abrir(db: Session, usuario, a: Absence, doc_id: str, accion: str, ip: Optional[str]) -> dict:
    """Enlace firmado para ver o descargar. Auditado (también si se deniega)."""
    from app.models.documents import DocumentAccessLog
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    d = db.query(DocumentoDeAusencia).filter(DocumentoDeAusencia.id == doc_id,
                                             DocumentoDeAusencia.absence_id == a.id).first()
    if d is None:
        raise error(404, "no_encontrado", detail="Documento no encontrado", que="documento")
    accion = "download" if accion == "download" else "view"
    if not puede_ver(db, usuario, a, d):
        audit_log(db, usuario, "ACCESS_DENIED", "absence_document", d.id, d.tipo.nombre if d.tipo else None,
                  ip_address=ip, metadata={"absence_id": a.id, "action": accion, "special_category": especial(a, d)})
        db.commit()
        raise error(403, "sin_acceso_documento")
    version = (d.documento.versions or [None])[0]
    if version is None or not version.file_key:
        raise error(404, "documento_sin_fichero")
    db.add(DocumentAccessLog(id=str(uuid.uuid4()), organization_id=a.organization_id, document_id=d.document_id,
                             user_id=usuario.id, action=accion, ip_address=ip))
    audit_log(db, usuario, "VIEW" if accion == "view" else "DOWNLOAD", "absence_document", d.id,
              d.tipo.nombre if d.tipo else None, ip_address=ip,
              metadata={"absence_id": a.id, "special_category": especial(a, d), "owner": a.user_id})
    db.commit()
    return {"url": file_storage.generate_presigned_url(version.file_key), "nombre": version.file_name,
            "tipo_mime": version.file_mime_type, "accion": accion}


def acceso_por_el_repositorio(db: Session, usuario, document_id: str) -> Optional[bool]:
    """Para `documents_service.check_document_access`: si el documento es de una
    ausencia, manda esta regla (None si no lo es). Así un administrador no lo
    abre por `/documents` saltándose la categoría especial."""
    d = db.query(DocumentoDeAusencia).filter(DocumentoDeAusencia.document_id == document_id).first()
    if d is None:
        return None
    a = db.query(Absence).filter(Absence.id == d.absence_id).first()
    return a is not None and puede_ver(db, usuario, a, d)


# ── La pasada diaria ─────────────────────────────────────────────────────────

def _siguientes(db: Session, hoy: date) -> int:
    """Los requisitos que se repiten (parte de confirmación cada N días) mientras dure la ausencia."""
    n = 0
    reglas = db.query(RequisitoDocumentalDeTipo).filter(RequisitoDocumentalDeTipo.repetir_cada_dias.isnot(None)).all()
    for regla in reglas:
        filas = db.query(RequisitoDeAusencia, Absence).join(Absence, Absence.id == RequisitoDeAusencia.absence_id).filter(
            RequisitoDeAusencia.regla_id == regla.id, Absence.is_active.is_(True),
            Absence.status.in_([AbsenceStatus.approved, AbsenceStatus.pending])).all()
        ultimos: dict = {}
        for r, a in filas:
            if r.absence_id not in ultimos or r.secuencia > ultimos[r.absence_id][0].secuencia:
                ultimos[r.absence_id] = (r, a)
        for r, a in ultimos.values():
            vence, sec = r.vence, r.secuencia
            while True:
                vence = vence + timedelta(days=int(regla.repetir_cada_dias))
                if vence > a.end_date or vence - timedelta(days=int(regla.recordar_dias_antes or 0)) > hoy:
                    break
                sec += 1
                db.add(RequisitoDeAusencia(id=str(uuid.uuid4()), organization_id=a.organization_id, absence_id=a.id,
                                           tipo_id=regla.tipo_de_documento_id, regla_id=regla.id, origen="tipo",
                                           secuencia=sec, vence=vence, estado="pendiente"))
                n += 1
    db.flush()
    return n


def pasada(db: Session, hoy: Optional[date] = None) -> dict:
    """Recordatorios antes de vencer, vencidos y escalado. Una vez por requisito. Confirma."""
    from app.services.ausencias.solicitudes import avisar
    from app.services.politicas import ejecutar_avisos
    hoy = hoy or timeutil.today()
    informe = {"nuevos": _siguientes(db, hoy), "recordados": 0, "vencidos": 0, "escalados": 0}
    filas = db.query(RequisitoDeAusencia, Absence).join(Absence, Absence.id == RequisitoDeAusencia.absence_id).filter(
        RequisitoDeAusencia.estado.in_(("pendiente", "vencido")), Absence.is_active.is_(True),
        Absence.status.in_([AbsenceStatus.approved, AbsenceStatus.pending, AbsenceStatus.waitlisted])).all()
    reglas = {r.id: r for r in db.query(RequisitoDocumentalDeTipo).all()}
    for req, a in filas:
        regla = reglas.get(req.regla_id)
        antes = int(regla.recordar_dias_antes) if regla is not None else 1
        nombre = req.tipo.nombre if req.tipo else "Documento"
        if req.estado == "pendiente" and req.recordado_en is None and hoy >= req.vence - timedelta(days=antes):
            avisar(db, [a.user_id], "Recuerda entregar un documento",
                   f"{nombre} de tu ausencia del {a.start_date}: vence el {req.vence.isoformat()}", a)
            req.recordado_en = _ahora()
            _evento(db, a, "recordatorio", None, documento=nombre, vence=req.vence)
            informe["recordados"] += 1
        if req.estado == "pendiente" and hoy > req.vence:
            req.estado = "vencido"
            _evento(db, a, "documento_vencido", None, documento=nombre, vence=req.vence)
            informe["vencidos"] += 1
        dias_escalado = regla.escalar_dias_despues if regla is not None else (0 if req.pedido_por else None)
        if req.estado == "vencido" and req.escalado_en is None and dias_escalado is not None \
                and hoy >= req.vence + timedelta(days=int(dias_escalado)):
            destinatarios = json.loads(regla.escalar_a or "[]") if regla is not None else []
            if req.pedido_por:
                destinatarios.append({"tipo": "persona", "valor": req.pedido_por})
            destinatarios = destinatarios or [{"tipo": "responsable"}]
            ejecutar_avisos(db, {"avisar": [{"destinatarios": destinatarios, "canales": ["app", "email"],
                                             "mensaje": f"Falta {nombre} (venció el {req.vence.isoformat()})",
                                             "politica": "Documentos de ausencias"}]},
                            a.user_id, "absence", a.id, f"{a.type} {a.start_date} → {a.end_date}", a.organization_id)
            req.escalado_en = _ahora()
            _evento(db, a, "escalado", None, documento=nombre, destinatarios=destinatarios)
            informe["escalados"] += 1
    db.commit()
    return informe
