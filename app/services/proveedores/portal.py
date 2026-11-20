"""Portal del proveedor (migracion 191).

Las personas externas de un proveedor (`subcontractor_workers` con su `User`
de rol `subcontractor`) que la empresa marca como **contacto del portal**
(`supplier_portal`) pueden, solo para SU proveedor:

- subir informes: avance de un paquete de trabajo (`progress`), informe
  periodico de un servicio (`periodic`), partes de servicio (`service_log`) y
  evidencias de SLA (`sla_evidence`), con ficheros adjuntos;
- ver sus paquetes de trabajo, sus servicios con el SLA medido en la cola, su
  consumo medido del periodo (prevision por contrato) y sus estados de cuenta.

Minimo privilegio:

- Solo con acceso vigente (`externos.ciclo.acceso_vigente`, que ya aplica
  `get_current_user`: acceso retirado o caducado -> 401) y la marca de contacto
  (sin ella -> 403 `proveedor_portal_sin_acceso`). Ninguna ruta acepta el id del
  proveedor: sale siempre de la ficha de la persona que llama.
- Sin datos internos: ni notas internas, ni responsables, ni quien aprueba, ni
  otros proveedores. Los importes son los del propio proveedor.
- Escribir exige el proveedor activo (suspendido o de baja -> 409).
- Cada informe y cada adjunto deja `audit_log`; abrir un adjunto, tambien
  (`DocumentAccessLog`). El responsable interno recibe un aviso al llegar
  un informe, y lo revisa en la ficha como siempre.

Los ficheros van al almacen de documentos (`s3_service.file_storage`) con la
validacion de subidas y el antivirus de siempre; el `Document` no tiene
proyecto, asi que en `/documents` solo lo ven su autor y administracion.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import REPORT_TYPES, REPORT_TYPES_DE_SERVICIO

#: Adjuntos por informe.
MAX_ADJUNTOS = 20


# ── Quien llama ──────────────────────────────────────────────────────────────

def ficha_del_contacto(db: Session, user):
    """(persona, proveedor) del contacto del portal, o (None, None)."""
    from app.models.enterprise import Subcontractor
    from app.services.externos.ciclo import acceso_vigente, es_rol_externo, trabajador_de_usuario
    if not es_rol_externo(user):
        return None, None
    w = trabajador_de_usuario(db, user.id)
    if w is None or not getattr(w, "supplier_portal", False) or w.is_active is False:
        return None, None
    if not acceso_vigente(db, user):
        return None, None
    sub = db.query(Subcontractor).filter(Subcontractor.id == w.subcontractor_id).first()
    return (w, sub) if sub is not None else (None, None)


def exigir(db: Session, user, escribir: bool = False):
    w, sub = ficha_del_contacto(db, user)
    if sub is None:
        raise error(403, "proveedor_portal_sin_acceso")
    if (sub.lifecycle_status or "active") == "offboarded":
        raise error(403, "proveedor_portal_sin_acceso")
    if escribir:
        from app.services.proveedores.ficha import exigir_activo
        exigir_activo(sub)
    return w, sub


def yo(db: Session, user) -> dict:
    """Siempre 200: si la persona es contacto del portal y de que proveedor."""
    w, sub = ficha_del_contacto(db, user)
    if sub is None or (sub.lifecycle_status or "active") == "offboarded":
        return {"enabled": False}
    activo = (sub.lifecycle_status or "active") not in ("suspended", "offboarded") and sub.is_active is not False
    return {
        "enabled": True, "can_write": activo,
        "supplier": {"id": sub.id, "name": sub.name, "kind": sub.kind or "company",
                     "engagement_modes": sub.engagement_modes or [], "lifecycle_status": sub.lifecycle_status or "active",
                     "currency": sub.currency},
        "person": {"id": w.id, "name": w.name, "access_until": str(w.access_until) if w.access_until else None},
        "report_types": list(REPORT_TYPES),
    }


# ── Lo que ve ────────────────────────────────────────────────────────────────

def _paquete_publico(d: dict) -> dict:
    fuera = ("internal_owner_id", "accepted_by", "legacy_assignment_id")
    return {k: v for k, v in d.items() if k not in fuera}


def paquetes(db: Session, user) -> list:
    from app.services.proveedores import paquetes as pq
    _, sub = exigir(db, user)
    return [_paquete_publico(p) for p in pq.listar(db, sub.id)]


def _servicio_publico(d: dict) -> dict:
    claves = ("id", "service_type", "name", "scope", "status", "start_date", "end_date", "sla_response_hours",
              "sla_resolution_hours", "sla_target_pct", "kpis", "contracted_units", "unit", "reporting_frequency",
              "credit_rules", "bonus_rules", "metering_source", "metering_last_at", "metering_last_quantity")
    return {k: d.get(k) for k in claves}


def servicios(db: Session, user) -> list:
    from app.services.proveedores import servicios as srv
    _, sub = exigir(db, user)
    return [_servicio_publico(s) for s in srv.listar(db, sub.id)]


def sla(db: Session, user, servicio_id: str, desde: date, hasta: date) -> dict:
    from app.models.proveedores import SupplierService
    from app.services.proveedores import servicios as srv
    _, sub = exigir(db, user)
    s = db.query(SupplierService).filter(SupplierService.id == servicio_id,
                                         SupplierService.subcontractor_id == sub.id).first()
    if s is None:
        raise error(404, "no_encontrado", detail="Servicio no encontrado", que="servicio")
    return srv.sla(db, s, desde, hasta)


def _informe_publico(d: dict) -> dict:
    fuera = ("reviewed_by",)
    return {k: v for k, v in d.items() if k not in fuera}


def informes(db: Session, user) -> list:
    from app.services.proveedores import paquetes as pq
    _, sub = exigir(db, user)
    return [_informe_publico(r) for r in pq.listar_informes(db, sub.id)]


def consumo(db: Session, user, desde: date, hasta: date) -> dict:
    """Consumo medido del periodo por contrato activo (la prevision) y los consumos registrados."""
    from app.models.proveedores import SupplierContract
    from app.services.proveedores import consumo as cons
    from app.services.proveedores import facturacion
    _, sub = exigir(db, user)
    contratos = []
    for c in db.query(SupplierContract).filter(SupplierContract.subcontractor_id == sub.id,
                                               SupplierContract.is_template == False,  # noqa: E712
                                               SupplierContract.status.in_(("active", "suspended"))).all():
        p = facturacion.prever(db, c, desde, hasta)
        contratos.append({
            "contract_id": c.id, "title": c.title, "code": c.code, "currency": c.currency,
            "lines": [{k: x.get(k) for k in ("model", "unit", "description", "quantity", "unit_price", "amount",
                                             "source", "service_id")} for x in p["lines"]],
            "subtotal": p["subtotal"], "credits": p["credits"], "bonus": p["bonus"],
            "adjustments": p["adjustments"], "expected_amount": p["expected_amount"],
        })
    registros = [{k: u.get(k) for k in ("id", "contract_id", "service_id", "period_start", "period_end", "unit",
                                        "quantity", "amount", "source", "source_system", "description")}
                 for u in cons.listar(db, sub.id)]
    # GRC: una persona externa consulta importes de su proveedor; queda constancia.
    audit_log(db, user, "VIEW_FINANCIAL", "supplier_usage_records", None, sub.name,
              metadata={"via": "portal", "period": f"{desde}/{hasta}", "subcontractor_id": sub.id})
    db.commit()
    return {"period_start": str(desde), "period_end": str(hasta), "contracts": contratos, "usage": registros}


def estados_de_cuenta(db: Session, user) -> list:
    from app.services.proveedores import facturacion
    _, sub = exigir(db, user)
    fuera = ("closed_by", "approved_by", "approval_request_id")
    salida = []
    for d in facturacion.listar(db, sub.id):
        d = {k: v for k, v in d.items() if k not in fuera}
        # Los detalles internos de calculo (personas, horas por persona) no salen.
        d["lines"] = [{k: x.get(k) for k in ("model", "unit", "description", "quantity", "unit_price", "amount",
                                             "source")} for x in (d.get("lines") or [])]
        salida.append(d)
    audit_log(db, user, "VIEW_FINANCIAL", "supplier_statements", None, sub.name,
              metadata={"via": "portal", "subcontractor_id": sub.id, "n": len(salida)})
    db.commit()
    return salida


# ── Lo que sube ──────────────────────────────────────────────────────────────

def _validar_adjuntos_enlace(adjuntos: Optional[list]) -> list:
    salida = []
    for a in adjuntos or []:
        a = a if isinstance(a, dict) else a.model_dump()
        url = (a.get("url") or "").strip()
        if not url.lower().startswith(("https://", "http://")):
            raise error(422, "proveedor_adjunto_no_valido")
        salida.append({"kind": "link", "name": (a.get("name") or url)[:255], "url": url[:1000]})
    if len(salida) > MAX_ADJUNTOS:
        raise error(422, "proveedor_demasiados_adjuntos", maximo=MAX_ADJUNTOS)
    return salida


def validar_informe(db: Session, sub, datos: dict) -> dict:
    """Tipo y destino del informe (paquete o servicio de ESE proveedor). Lo usa tambien la ficha."""
    from app.models.proveedores import SupplierService, SupplierWorkPackage
    tipo = datos.get("report_type") or ("periodic" if datos.get("service_id") and not datos.get("work_package_id")
                                        else "progress")
    if tipo not in REPORT_TYPES:
        raise error(422, "proveedor_informe_tipo_no_valido", tipo=tipo)
    if tipo == "progress" and not datos.get("work_package_id"):
        raise error(422, "campo_obligatorio", campo="work_package_id")
    if tipo in REPORT_TYPES_DE_SERVICIO and not datos.get("service_id"):
        raise error(422, "campo_obligatorio", campo="service_id")
    if datos.get("work_package_id") and not db.query(SupplierWorkPackage.id).filter(
            SupplierWorkPackage.id == datos["work_package_id"], SupplierWorkPackage.subcontractor_id == sub.id).first():
        raise error(404, "no_encontrado", detail="Paquete no encontrado", que="paquete_de_trabajo")
    if datos.get("service_id") and not db.query(SupplierService.id).filter(
            SupplierService.id == datos["service_id"], SupplierService.subcontractor_id == sub.id).first():
        raise error(404, "no_encontrado", detail="Servicio no encontrado", que="servicio")
    if datos.get("period_start") and datos.get("period_end") and datos["period_end"] < datos["period_start"]:
        raise error(422, "proveedor_fechas_no_validas")
    datos["report_type"] = tipo
    return datos


def _avisar_responsable(db: Session, sub, informe, persona: str) -> None:
    from app.models.proveedores import SupplierService, SupplierWorkPackage
    from app.services.notifications import notify_user
    destino = None
    if informe.work_package_id:
        wp = db.get(SupplierWorkPackage, informe.work_package_id)
        destino = getattr(wp, "internal_owner_id", None)
    elif informe.service_id:
        s = db.get(SupplierService, informe.service_id)
        destino = getattr(s, "internal_owner_id", None)
    destino = destino or sub.internal_owner_id
    if not destino:
        return
    try:
        notify_user(db, destino, "system", f"{sub.name}: informe nuevo del proveedor ({informe.report_type})",
                    f"{persona} lo ha subido desde el portal del proveedor. Revísalo en su ficha.",
                    resource="subcontractors", resource_id=sub.id, action_url="/subcontractors")
    except Exception:  # el aviso no tumba el informe
        import logging
        logging.getLogger(__name__).warning("aviso de informe de proveedor no enviado", exc_info=True)


def crear_informe(db: Session, user, datos: dict) -> dict:
    from app.models.proveedores import SupplierReport, SupplierWorkPackage
    w, sub = exigir(db, user, escribir=True)
    datos = {k: v for k, v in datos.items() if v is not None}
    adjuntos = _validar_adjuntos_enlace(datos.pop("attachments", None))
    datos = validar_informe(db, sub, datos)
    if not (datos.get("summary") or "").strip():
        raise error(422, "campo_obligatorio", campo="summary")
    r = SupplierReport(subcontractor_id=sub.id, submitted_by=user.id, status="submitted", submitted_via="portal",
                       attachments=adjuntos or None, **datos)
    db.add(r)
    if r.work_package_id:
        wp = db.get(SupplierWorkPackage, r.work_package_id)
        if wp is not None:
            wp.last_report_at = timeutil.today()
            if r.progress_pct is not None and wp.status not in ("accepted", "cancelled"):
                wp.progress_pct = r.progress_pct
    db.flush()
    audit_log(db, user, "CREATE", "supplier_reports", r.id, sub.name,
              new_values={"via": "portal", "report_type": r.report_type, "work_package_id": r.work_package_id,
                          "service_id": r.service_id, "attachments": len(adjuntos)})
    _avisar_responsable(db, sub, r, w.name)
    db.commit()
    db.refresh(r)
    return _informe_publico(ser.informe(r))


def _informe_propio(db: Session, sub, informe_id: str):
    from app.models.proveedores import SupplierReport
    r = db.query(SupplierReport).filter(SupplierReport.id == informe_id,
                                        SupplierReport.subcontractor_id == sub.id).first()
    if r is None:
        raise error(404, "no_encontrado", detail="Informe no encontrado", que="informe")
    return r


def subir_adjunto(db: Session, user, informe_id: str, nombre: str, content_type: str, contenido: bytes,
                  ip: Optional[str] = None) -> dict:
    """Adjunta un fichero (evidencia) a un informe del propio proveedor, mientras no esta revisado."""
    w, sub = exigir(db, user, escribir=True)
    r = _informe_propio(db, sub, informe_id)
    if r.status == "reviewed":
        raise error(409, "proveedor_informe_revisado")
    return guardar_adjunto(db, user, sub, r, nombre, content_type, contenido, ip, via="portal")


def guardar_adjunto(db: Session, user, sub, r, nombre: str, content_type: str, contenido: bytes,
                    ip: Optional[str] = None, via: str = "internal") -> dict:
    """Guarda el fichero en el almacen de documentos y lo anade a `attachments` del informe."""
    from app.core.config import settings
    from app.core.uploads import validate_upload
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.collaboration._storage import scan_with_av
    from app.services.s3_service import file_storage
    from app.services.settings_service import get_runtime_int
    actuales = list(r.attachments or [])
    if len(actuales) >= MAX_ADJUNTOS:
        raise error(422, "proveedor_demasiados_adjuntos", maximo=MAX_ADJUNTOS)
    maximo = (get_runtime_int(db, "MAX_FILE_SIZE_MB", r.organization_id) or settings.MAX_FILE_SIZE_MB) * 1024 * 1024
    if len(contenido) > maximo:
        raise error(413, "fichero_demasiado_grande", detail=f"El archivo supera el máximo de {maximo // (1024 * 1024)} MB",
                    max=maximo // (1024 * 1024))
    validate_upload(nombre or "", content_type or "", contenido)
    av, detalle = scan_with_av(contenido)
    if av == "infected":
        audit_log(db, user, "UPLOAD_BLOCKED", "supplier_reports", r.id, nombre, metadata={"antivirus": detalle})
        db.commit()
        raise error(422, "antivirus_bloqueado")
    doc = Document(id=str(uuid.uuid4()), organization_id=r.organization_id,
                   title=f"{sub.name} · {r.report_type} · {nombre or 'evidencia'}"[:255],
                   category=DocumentCategory.other, created_by=user.id, description=None)
    db.add(doc)
    clave, tamano = file_storage.upload_file(file_content=contenido, file_name=nombre or "evidencia",
                                             document_id=doc.id, version_num=1,
                                             content_type=content_type or "application/octet-stream")
    try:
        db.add(DocumentVersion(id=str(uuid.uuid4()), organization_id=r.organization_id, document_id=doc.id,
                               version_num=1, file_key=clave, file_name=(nombre or "evidencia")[:255],
                               file_size=tamano, file_mime_type=content_type, created_by=user.id))
        adjunto = {"kind": "file", "document_id": doc.id, "name": (nombre or "evidencia")[:255], "size": tamano,
                   "mime": content_type, "uploaded_at": datetime.now(timezone.utc).isoformat(), "via": via}
        r.attachments = actuales + [adjunto]
        audit_log(db, user, "CREATE", "supplier_report_attachments", r.id, nombre, ip_address=ip,
                  metadata={"document_id": doc.id, "via": via, "antivirus": av, "size": tamano})
        db.commit()
    except Exception:
        db.rollback()
        try:
            file_storage.delete_file(clave)
        except Exception:
            pass
        raise
    db.refresh(r)
    return ser.informe(r)


def abrir_adjunto(db: Session, user, r, document_id: str, ip: Optional[str] = None) -> dict:
    """Enlace firmado de un adjunto del informe (auditado)."""
    from app.models.documents import Document, DocumentAccessLog
    from app.services.s3_service import file_storage
    if not any(a.get("document_id") == document_id for a in (r.attachments or [])):
        raise error(404, "no_encontrado", detail="Adjunto no encontrado", que="documento")
    doc = db.query(Document).filter(Document.id == document_id).first()
    version = (doc.versions or [None])[0] if doc is not None else None
    if version is None or not version.file_key:
        raise error(404, "documento_sin_fichero")
    db.add(DocumentAccessLog(id=str(uuid.uuid4()), organization_id=r.organization_id, document_id=document_id,
                             user_id=user.id, action="download", ip_address=ip))
    audit_log(db, user, "DOWNLOAD", "supplier_reports", r.id, version.file_name, ip_address=ip,
              metadata={"document_id": document_id})
    db.commit()
    return {"url": file_storage.generate_presigned_url(version.file_key), "name": version.file_name,
            "mime": version.file_mime_type}


def abrir_adjunto_propio(db: Session, user, informe_id: str, document_id: str, ip: Optional[str] = None) -> dict:
    _, sub = exigir(db, user)
    return abrir_adjunto(db, user, _informe_propio(db, sub, informe_id), document_id, ip)


# ── Gestion de contactos (la empresa) ────────────────────────────────────────

def contactos(db: Session, sub) -> list:
    from app.models.enterprise import SubcontractorWorker
    salida = []
    for w in db.query(SubcontractorWorker).filter(SubcontractorWorker.subcontractor_id == sub.id,
                                                  SubcontractorWorker.is_active.isnot(False)).order_by(
            SubcontractorWorker.name).all():
        salida.append({"worker_id": w.id, "name": w.name, "email": w.email, "has_access": bool(w.has_access),
                       "access_until": str(w.access_until) if w.access_until else None,
                       "supplier_portal": bool(getattr(w, "supplier_portal", False)), "user_id": w.user_id})
    return salida


def marcar_contacto(db: Session, sub, worker_id: str, activar: bool, actor) -> dict:
    """La empresa da o quita a una persona del proveedor el acceso al portal (auditado)."""
    from app.models.enterprise import SubcontractorWorker
    w = db.query(SubcontractorWorker).filter(SubcontractorWorker.id == worker_id,
                                             SubcontractorWorker.subcontractor_id == sub.id).first()
    if w is None:
        raise error(404, "no_encontrado", detail="Persona no encontrada", que="persona")
    if activar:
        from app.services.proveedores.ficha import exigir_activo
        exigir_activo(sub)
        hoy = timeutil.today()
        if not w.user_id or not w.has_access or w.is_active is False or (w.access_until and w.access_until < hoy):
            raise error(422, "proveedor_portal_requiere_acceso", persona=w.name)
    anterior = bool(getattr(w, "supplier_portal", False))
    w.supplier_portal = bool(activar)
    audit_log(db, actor, "UPDATE", "subcontractor_workers", w.id, w.name,
              old_values={"supplier_portal": anterior}, new_values={"supplier_portal": bool(activar)},
              metadata={"subcontractor_id": sub.id})
    db.commit()
    return contactos(db, sub)
