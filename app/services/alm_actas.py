"""Actas de entrega y devolución de activos (licencias y hardware, fase 1 — 16-11-2026).

Cuando un activo pasa a una persona (o vuelve de ella) se emite un acta:
checklist configurable (`ALM_HANDOVER_CHECKLIST`), estado físico,
observaciones, un PDF guardado en el sistema de documentos y una solicitud de
firma en el módulo de firma electrónica (`esign_service`), con el proveedor
de `ALM_ACT_ESIGN_PROVIDER`:

- ``manual`` (por defecto): firma en la aplicación. La persona entra en su acta
  y pulsa «Firmar»; queda la fecha, la IP y la huella del PDF (firma
  electrónica simple, con la evidencia en el historial inmutable).
- ``docusign`` / ``adobe_sign``: el proveedor envía el documento; el webhook de
  firma actualiza el sobre y el acta lee su estado (`sincronizar`).

Las fotos del estado (y cualquier documento) van como `ALMAdjunto` sobre el
sistema de documentos, con su PDF o imagen validados como cualquier subida.

Sin persona que firme (titular proyecto, cliente...) el acta queda
``unsigned``: sirve de constancia, sin firma.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMActa, ALMAdjunto, ALMAsignacion, ALMAsset

logger = logging.getLogger(__name__)

TIPOS_DE_ACTA = ("delivery", "return")
TIPOS_DE_ADJUNTO = ("photo", "disposal_certificate", "invoice", "other")


def actas_activadas(db: Session, org: Optional[str]) -> bool:
    from app.services.alm_ajustes import ajuste_bool
    return ajuste_bool(db, "ALM_HANDOVER_ACT_ENABLED", org)


def checklist_de(db: Session, org: Optional[str]) -> list[str]:
    """Los códigos del checklist de la empresa (la interfaz los traduce: `alm.chk_<código>`)."""
    from app.services.alm_ajustes import ajuste_lista
    return ajuste_lista(db, "ALM_HANDOVER_CHECKLIST", org)


def _normalizar_checklist(db: Session, org, checklist: Optional[list]) -> list[dict]:
    """Una fila por elemento de la plantilla; lo que no llegó queda sin marcar."""
    recibido = {}
    for fila in checklist or []:
        if isinstance(fila, dict) and fila.get("item"):
            recibido[str(fila["item"])[:60]] = {"ok": bool(fila.get("ok")), "note": (fila.get("note") or "")[:300]}
    salida = []
    for item in checklist_de(db, org):
        r = recibido.pop(item, {"ok": False, "note": ""})
        salida.append({"item": item, **r})
    for item, r in recibido.items():   # elementos añadidos a mano en el acta
        salida.append({"item": item, **r})
    return salida


# ── PDF ───────────────────────────────────────────────────────────────────────

_TEXTOS = {
    "es": {"delivery": "Acta de entrega de equipo", "return": "Acta de devolución de equipo",
           "asset": "Equipo", "serial": "N.º de serie", "tag": "Etiqueta", "holder": "Persona",
           "issued_by": "Emitida por", "date": "Fecha", "condition": "Estado físico", "checklist": "Comprobaciones",
           "yes": "Sí", "no": "No", "observations": "Observaciones", "loan_due": "Devolución prevista",
           "sign": "Firma de la persona", "legal": "La persona declara recibir (o devolver) el equipo en el estado descrito."},
    "en": {"delivery": "Equipment delivery act", "return": "Equipment return act",
           "asset": "Equipment", "serial": "Serial number", "tag": "Asset tag", "holder": "Person",
           "issued_by": "Issued by", "date": "Date", "condition": "Physical condition", "checklist": "Checks",
           "yes": "Yes", "no": "No", "observations": "Observations", "loan_due": "Due back",
           "sign": "Signature", "legal": "The person declares receiving (or returning) the equipment as described."},
    "zh": {"delivery": "设备交付单", "return": "设备归还单",
           "asset": "设备", "serial": "序列号", "tag": "资产标签", "holder": "人员",
           "issued_by": "签发人", "date": "日期", "condition": "外观状态", "checklist": "检查项",
           "yes": "是", "no": "否", "observations": "备注", "loan_due": "预计归还日期",
           "sign": "本人签名", "legal": "本人确认已按上述状态接收（或归还）该设备。"},
}

#: 16-11-2026: el acta salía en español o inglés y el chino caía al inglés
#: (y las fuentes base de reportlab no tienen glifos CJK). Ahora sale en el
#: idioma de la persona del acta (sus preferencias; si no, el de la plataforma)
#: y el chino usa la fuente CID estándar STSong-Light, que no requiere ficheros.
_FUENTE_CJK = "STSong-Light"


def _idioma_del_acta(db: Session, asignacion: ALMAsignacion) -> str:
    from app.core.config import settings
    from app.models.user import UserPreference
    idioma = None
    if asignacion.holder_type == "user" and asignacion.holder_user_id:
        pref = db.query(UserPreference).filter(UserPreference.user_id == asignacion.holder_user_id).first()
        idioma = getattr(pref, "language", None)
    idioma = (idioma or settings.DEFAULT_LANGUAGE or "es")[:2].lower()
    return idioma if idioma in _TEXTOS else "en"


def _fuentes(idioma: str) -> tuple[str, str]:
    """(normal, negrita) para el idioma; en chino, la CID registrada una vez."""
    if idioma != "zh":
        return "Helvetica", "Helvetica-Bold"
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    if _FUENTE_CJK not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_FUENTE_CJK))
    return _FUENTE_CJK, _FUENTE_CJK


def _pdf(db: Session, acta: ALMActa, activo: ALMAsset, titular: str, emisor: str, checklist: list[dict],
         asignacion: ALMAsignacion) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    from app.services._pdf_marca import marca_de_organizacion

    idioma = _idioma_del_acta(db, asignacion)
    tx = _TEXTOS[idioma]
    normal, negrita = _fuentes(idioma)
    marca = marca_de_organizacion(db, acta.organization_id)
    paleta = marca.paleta
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    st = getSampleStyleSheet()
    for nombre in ("Title", "Heading3", "BodyText", "Italic"):
        st[nombre].fontName = negrita if nombre in ("Title", "Heading3") else normal
    e = lambda v: escape(str(v)) if v not in (None, "") else "—"  # noqa: E731
    filas = [
        [tx["asset"], e(activo.name)], [tx["serial"], e(activo.serial_number)], [tx["tag"], e(activo.asset_tag)],
        [tx["holder"], e(titular)], [tx["issued_by"], e(emisor)],
        [tx["date"], timeutil.today().isoformat()], [tx["condition"], e(acta.condition)],
    ]
    if asignacion.mode == "loan" and asignacion.valid_to:
        filas.append([tx["loan_due"], asignacion.valid_to.isoformat()])
    tabla = Table(filas, colWidths=[5 * cm, 11 * cm])
    tabla.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), normal),
                               ("FONTNAME", (0, 0), (0, -1), negrita),
                               ("TEXTCOLOR", (0, 0), (0, -1), paleta.color("acento")),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    chk = Table([[e(c["item"]), tx["yes"] if c["ok"] else tx["no"], e(c.get("note"))] for c in checklist] or [["—", "", ""]],
                colWidths=[6 * cm, 2 * cm, 8 * cm])
    chk.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                             ("FONTNAME", (0, 0), (-1, -1), normal)]))
    contenido = [Paragraph(e(tx[acta.kind]), st["Title"]), Spacer(1, 10), tabla, Spacer(1, 14),
                 Paragraph(tx["checklist"], st["Heading3"]), chk, Spacer(1, 12),
                 Paragraph(tx["observations"], st["Heading3"]), Paragraph(e(acta.observations), st["BodyText"]),
                 Spacer(1, 18), Paragraph(tx["legal"], st["Italic"]), Spacer(1, 36),
                 Paragraph(f"{tx['sign']}: ______________________________", st["BodyText"])]
    doc.build(contenido)
    return buf.getvalue()


# ── Documentos ────────────────────────────────────────────────────────────────

def guardar_documento(db: Session, actor, contenido: bytes, nombre: str, mime: str, titulo: str,
                      categoria: str = "other", validar: bool = True) -> str:
    """Sube el fichero al almacén de documentos y crea su `Document` (versión 1). Devuelve el id."""
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.s3_service import file_storage
    if validar:
        from app.services.documents_service import validate_upload
        validate_upload(nombre, mime, contenido)
    clave, tam = file_storage.upload_file(file_content=contenido, file_name=nombre, document_id="alm",
                                          version_num=1, content_type=mime)
    doc = Document(title=titulo[:255], category=DocumentCategory(categoria), created_by=getattr(actor, "id", None))
    db.add(doc)
    db.flush()
    db.add(DocumentVersion(document_id=doc.id, version_num=1, file_key=clave, file_name=nombre[:255],
                           file_size=tam, file_mime_type=mime, change_note="ALM",
                           created_by=getattr(actor, "id", None)))
    db.flush()
    return doc.id


def url_de_documento(db: Session, document_id: Optional[str]) -> Optional[str]:
    """URL de descarga temporal de la última versión (quien llama ya comprobó el permiso)."""
    if not document_id:
        return None
    from app.models.documents import DocumentVersion
    from app.services.s3_service import file_storage
    v = (db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id)
         .order_by(DocumentVersion.version_num.desc()).first())
    if v is None or not v.file_key:
        return None
    try:
        return file_storage.generate_presigned_url(v.file_key)
    except Exception:
        logger.warning("sin URL para el documento %s", document_id, exc_info=True)
        return None


def _huella(db: Session, document_id: Optional[str]) -> Optional[str]:
    if not document_id:
        return None
    from app.models.documents import DocumentVersion
    v = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).first()
    return hashlib.sha256((v.file_key or "").encode()).hexdigest() if v else None


# ── Crear, firmar, sincronizar ────────────────────────────────────────────────

def crear_acta(db: Session, asignacion: ALMAsignacion, kind: str, actor, *, checklist: Optional[list] = None,
               condition: Optional[str] = None, observations: Optional[str] = None) -> ALMActa:
    """Emite el acta de la asignación (no confirma). Si el PDF o la firma fallan, el
    acta queda emitida sin ellos y se puede regenerar (`regenerar`)."""
    if kind not in TIPOS_DE_ACTA:
        raise ErrorDeDominio(422, "alm_acta_tipo_invalido")
    if condition and condition not in ("new", "good", "fair", "poor"):
        raise ErrorDeDominio(422, "alm_estado_fisico_invalido")
    activo = asignacion.asset
    acta = ALMActa(kind=kind, assignment_id=asignacion.id, asset_id=activo.id,
                   signer_user_id=asignacion.holder_user_id if asignacion.holder_type == "user" else None,
                   issued_by=getattr(actor, "id", None),
                   checklist=json.dumps(_normalizar_checklist(db, asignacion.organization_id, checklist)),
                   condition=condition or getattr(activo.condition, "value", activo.condition),
                   observations=(observations or None),
                   status="pending_signature" if asignacion.holder_type == "user" else "unsigned")
    acta.organization_id = asignacion.organization_id
    db.add(acta)
    db.flush()
    _documento_y_firma(db, acta, actor)
    from app.services.alm_asignaciones import registrar_evento
    registrar_evento(db, evento="act_created", resource_type="asset", asignacion=asignacion,
                     actor_id=getattr(actor, "id", None), datos={"act_id": acta.id, "kind": kind})
    return acta


def _documento_y_firma(db: Session, acta: ALMActa, actor) -> None:
    from app.services.alm_asignaciones import nombre_de_titular
    asignacion = acta.assignment
    try:
        titular = nombre_de_titular(db, asignacion.holder_type, asignacion.holder_id) or ""
        emisor = getattr(actor, "full_name", None) or ""
        contenido = _pdf(db, acta, acta.asset, titular, emisor, json.loads(acta.checklist or "[]"), asignacion)
        with db.begin_nested():
            acta.document_id = guardar_documento(
                db, actor, contenido, f"acta-{acta.kind}-{acta.asset.asset_tag or acta.asset_id[:8]}.pdf",
                "application/pdf", f"{acta.kind} · {acta.asset.name}", categoria="legal", validar=False)
    except Exception:
        logger.exception("acta %s: no se pudo generar o guardar el PDF", acta.id)
        return
    if acta.signer_user_id and acta.document_id:
        try:
            with db.begin_nested():
                _pedir_firma(db, acta, actor)
        except Exception:
            logger.exception("acta %s: no se pudo crear la solicitud de firma", acta.id)


def _pedir_firma(db: Session, acta: ALMActa, actor) -> None:
    from app.models.documents import Document
    from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner, ESignStatus
    from app.models.user import User
    from app.services.alm_ajustes import ajuste_str
    from app.services.esign_service import create_provider_envelope
    firmante = db.get(User, acta.signer_user_id)
    if firmante is None or not firmante.email:
        return
    try:
        proveedor = ESignProvider(ajuste_str(db, "ALM_ACT_ESIGN_PROVIDER", acta.organization_id) or "manual")
    except ValueError:
        proveedor = ESignProvider.manual
    doc = db.get(Document, acta.document_id)
    sobre = ESignEnvelope(document_id=acta.document_id, provider=proveedor, created_by_id=getattr(actor, "id", None),
                          subject=f"{acta.kind}: {acta.asset.name}"[:500], status=ESignStatus.draft)
    sobre.organization_id = acta.organization_id
    sobre.signers = [ESignSigner(name=firmante.full_name or firmante.email, email=firmante.email,
                                 routing_order=1, user_id=firmante.id)]
    resultado = create_provider_envelope(sobre, doc, db) if proveedor != ESignProvider.manual else \
        {"provider_envelope_id": None, "signing_url": None, "status": ESignStatus.sent}
    sobre.provider_envelope_id = resultado.get("provider_envelope_id")
    sobre.signing_url = resultado.get("signing_url")
    sobre.status = resultado.get("status", ESignStatus.sent)
    if sobre.status == ESignStatus.sent:
        sobre.sent_at = timeutil.utcnow()
    for s in sobre.signers:
        s.organization_id = acta.organization_id
    db.add(sobre)
    db.flush()
    acta.envelope_id = sobre.id
    _avisar_firmante(db, acta)


def _avisar_firmante(db: Session, acta: ALMActa) -> None:
    try:
        from app.services.notifications import notify_user
        from app.services.alm_ajustes import texto_de_aviso
        notify_user(db, acta.signer_user_id, "system", texto_de_aviso("act_to_sign_title", nombre=acta.asset.name),
                    body=texto_de_aviso(f"act_to_sign_{acta.kind}"), resource="alm_act", resource_id=acta.id,
                    action_url="/my-equipment")
    except Exception:
        logger.warning("acta %s: no se pudo avisar a quien firma", acta.id, exc_info=True)


def regenerar(db: Session, acta_id: str, actor) -> ALMActa:
    """Vuelve a generar el PDF y la solicitud de firma de un acta que no los tiene."""
    acta = _acta(db, acta_id)
    if acta.status == "signed":
        raise ErrorDeDominio(409, "alm_acta_ya_firmada")
    if acta.document_id and (acta.envelope_id or not acta.signer_user_id):
        return acta
    if not acta.document_id:
        _documento_y_firma(db, acta, actor)
    elif acta.signer_user_id and not acta.envelope_id:
        with db.begin_nested():
            _pedir_firma(db, acta, actor)
    db.commit()
    return acta


def _acta(db: Session, acta_id: str) -> ALMActa:
    acta = db.query(ALMActa).filter(ALMActa.id == acta_id).first()
    if acta is None:
        raise ErrorDeDominio(404, "alm_acta_no_encontrada")
    return acta


def sincronizar(db: Session, acta: ALMActa) -> ALMActa:
    """El estado del sobre manda: si el proveedor la completó, el acta queda firmada."""
    if acta.status != "pending_signature" or not acta.envelope_id:
        return acta
    from app.models.esign import ESignEnvelope, ESignStatus
    sobre = db.get(ESignEnvelope, acta.envelope_id)
    if sobre is None:
        return acta
    estado = getattr(sobre.status, "value", sobre.status)
    if estado == ESignStatus.completed.value:
        acta.status = "signed"
        acta.signed_at = sobre.completed_at or timeutil.utcnow()
        from app.services.alm_asignaciones import registrar_evento
        registrar_evento(db, evento="act_signed", resource_type="asset", asignacion=acta.assignment,
                         actor_id=acta.signer_user_id, datos={"act_id": acta.id, "provider": getattr(sobre.provider, "value", sobre.provider)})
        db.commit()
    elif estado in (ESignStatus.voided.value, ESignStatus.declined.value):
        acta.status = "void"
        db.commit()
    return acta


def firmar(db: Session, acta_id: str, usuario, ip: Optional[str] = None) -> ALMActa:
    """Firma en la aplicación (proveedor ``manual``): solo la persona del acta."""
    from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner
    from app.services.esign_service import mark_signer_signed
    acta = _acta(db, acta_id)
    if acta.signer_user_id != getattr(usuario, "id", None):
        raise ErrorDeDominio(403, "alm_acta_no_es_tuya")
    if acta.status == "signed":
        raise ErrorDeDominio(409, "alm_acta_ya_firmada")
    if acta.status != "pending_signature":
        raise ErrorDeDominio(409, "alm_acta_no_firmable")
    if not acta.envelope_id:
        raise ErrorDeDominio(409, "alm_acta_sin_solicitud")
    sobre = db.get(ESignEnvelope, acta.envelope_id)
    if sobre is None or getattr(sobre.provider, "value", sobre.provider) != ESignProvider.manual.value:
        raise ErrorDeDominio(409, "alm_acta_firma_externa")
    firmante = db.query(ESignSigner).filter(ESignSigner.envelope_id == sobre.id,
                                            ESignSigner.user_id == usuario.id).first()
    if firmante is None:
        raise ErrorDeDominio(403, "alm_acta_no_es_tuya")
    mark_signer_signed(db, firmante, sobre)   # confirma; con un firmante completa el sobre
    acta = _acta(db, acta_id)
    acta.status = "signed"
    acta.signed_at = timeutil.utcnow()
    from app.services.alm_asignaciones import registrar_evento
    registrar_evento(db, evento="act_signed", resource_type="asset", asignacion=acta.assignment,
                     actor_id=usuario.id, datos={"act_id": acta.id, "provider": "manual", "ip": ip,
                                                 "document_sha256": _huella(db, acta.document_id)})
    db.commit()
    db.refresh(acta)
    return acta


def anular(db: Session, acta_id: str, actor, motivo: Optional[str]) -> ALMActa:
    acta = _acta(db, acta_id)
    if acta.status == "signed":
        raise ErrorDeDominio(409, "alm_acta_ya_firmada")
    acta.status = "void"
    if acta.envelope_id:
        from app.models.esign import ESignEnvelope
        from app.services.esign_service import void_envelope
        sobre = db.get(ESignEnvelope, acta.envelope_id)
        if sobre is not None:
            void_envelope(db, sobre)
    from app.services.alm_asignaciones import registrar_evento
    registrar_evento(db, evento="cancelled", resource_type="asset", asignacion=acta.assignment,
                     actor_id=getattr(actor, "id", None), motivo=motivo, datos={"act_id": acta.id})
    db.commit()
    return acta


# ── Adjuntos ──────────────────────────────────────────────────────────────────

def adjuntar(db: Session, actor, contenido: bytes, nombre: str, mime: str, *, kind: str = "photo",
             asset_id: Optional[str] = None, act_id: Optional[str] = None,
             invoice_id: Optional[str] = None) -> ALMAdjunto:
    if kind not in TIPOS_DE_ADJUNTO:
        raise ErrorDeDominio(422, "alm_adjunto_tipo_invalido")
    org = None
    titulo = nombre
    if act_id:
        acta = _acta(db, act_id)
        asset_id = asset_id or acta.asset_id
        org = acta.organization_id
    if asset_id:
        activo = db.query(ALMAsset).filter(ALMAsset.id == asset_id).first()
        if activo is None:
            raise ErrorDeDominio(404, "alm_activo_no_encontrado")
        org = org or activo.organization_id
        titulo = f"{activo.name} · {nombre}"
    if invoice_id:
        from app.models.alm import ALMFacturaProveedor
        f = db.query(ALMFacturaProveedor).filter(ALMFacturaProveedor.id == invoice_id).first()
        if f is None:
            raise ErrorDeDominio(404, "alm_factura_no_encontrada")
        org = org or f.organization_id
    doc_id = guardar_documento(db, actor, contenido, nombre, mime, titulo)
    adj = ALMAdjunto(asset_id=asset_id, act_id=act_id, invoice_id=invoice_id, document_id=doc_id, kind=kind,
                     uploaded_by=getattr(actor, "id", None))
    adj.organization_id = org
    db.add(adj)
    db.commit()
    db.refresh(adj)
    return adj


def adjuntos(db: Session, *, asset_id=None, act_id=None, invoice_id=None) -> list[dict]:
    from app.models.documents import DocumentVersion
    q = db.query(ALMAdjunto)
    if asset_id:
        q = q.filter(ALMAdjunto.asset_id == asset_id)
    if act_id:
        q = q.filter(ALMAdjunto.act_id == act_id)
    if invoice_id:
        q = q.filter(ALMAdjunto.invoice_id == invoice_id)
    salida = []
    for adj in q.order_by(ALMAdjunto.created_at.desc()).all():
        v = db.query(DocumentVersion).filter(DocumentVersion.document_id == adj.document_id).first()
        salida.append({"id": adj.id, "kind": adj.kind, "act_id": adj.act_id, "asset_id": adj.asset_id,
                       "invoice_id": adj.invoice_id, "document_id": adj.document_id,
                       "file_name": v.file_name if v else None, "mime": v.file_mime_type if v else None,
                       "url": url_de_documento(db, adj.document_id),
                       "created_at": adj.created_at.isoformat() if adj.created_at else None})
    return salida


# ── Lectura ───────────────────────────────────────────────────────────────────

def serializar(db: Session, acta: ALMActa, con_url: bool = True) -> dict:
    sincronizar(db, acta)
    from app.services.alm_asignaciones import nombre_de_titular
    a = acta.assignment
    try:
        checklist = json.loads(acta.checklist or "[]")
    except ValueError:
        checklist = []
    proveedor = None
    if acta.envelope_id:
        from app.models.esign import ESignEnvelope
        sobre = db.get(ESignEnvelope, acta.envelope_id)
        proveedor = getattr(sobre.provider, "value", sobre.provider) if sobre else None
    return {
        "id": acta.id, "kind": acta.kind, "status": acta.status, "assignment_id": acta.assignment_id,
        "asset_id": acta.asset_id, "asset_name": acta.asset.name if acta.asset else None,
        "holder_type": a.holder_type if a else None,
        "holder_name": nombre_de_titular(db, a.holder_type, a.holder_id) if a else None,
        "signer_user_id": acta.signer_user_id, "signer_name": acta.signer.full_name if acta.signer else None,
        "checklist": checklist, "condition": acta.condition, "observations": acta.observations,
        "document_id": acta.document_id, "pdf_url": url_de_documento(db, acta.document_id) if con_url else None,
        "esign_provider": proveedor, "signed_at": acta.signed_at.isoformat() if acta.signed_at else None,
        "created_at": acta.created_at.isoformat() if acta.created_at else None,
        "attachments": adjuntos(db, act_id=acta.id) if con_url else [],
    }


def listar(db: Session, *, asset_id=None, assignment_id=None, signer_user_id=None, status=None) -> list[dict]:
    q = db.query(ALMActa)
    if asset_id:
        q = q.filter(ALMActa.asset_id == asset_id)
    if assignment_id:
        q = q.filter(ALMActa.assignment_id == assignment_id)
    if signer_user_id:
        q = q.filter(ALMActa.signer_user_id == signer_user_id)
    if status:
        q = q.filter(ALMActa.status == status)
    return [serializar(db, a) for a in q.order_by(ALMActa.created_at.desc()).all()]


def acta_para(db: Session, acta_id: str, usuario, es_gestor: bool) -> ALMActa:
    """El acta, si quien la pide es gestor o la persona que firma (si no, 404)."""
    acta = _acta(db, acta_id)
    if not es_gestor and acta.signer_user_id != getattr(usuario, "id", None):
        raise ErrorDeDominio(404, "alm_acta_no_encontrada")
    return acta

