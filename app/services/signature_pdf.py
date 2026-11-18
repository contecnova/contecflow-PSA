"""signature_pdf.py — Genera un PDF con certificado de firma digital.

Auditoria 2026-08 (hallazgo 32). Los colores estaban escritos en duro dieciseis
veces —cinco constantes locales y once `HexColor` intercalados—, asi que este
certificado, que es lo que recibe el cliente al firmar, salia con los colores de
la plataforma aunque el cliente tuviera su marca configurada.

Ahora la paleta viene de `_pdf_marca` y el llamador puede pasar la del tenant.
Los tres tintes propios de este documento —el gris de cuerpo, el sombreado de
filas y el fondo verdoso del sello— viven desde 2026-11 en `_pdf_marca`
(`TINTES_DE_FIRMA`), con los mismos valores: toda la paleta de documentos en un
solo sitio.

18-11-2026 (auditoria de textos fijos): el certificado lo recibe el cliente,
asi que sale en su idioma (`idioma`; etiquetas en los 8 idiomas del portal,
castellano por defecto), con el nombre de la empresa (`marca`) y la fecha en
el formato del idioma y en la zona `zona` con su etiqueta (UTC si no se da).
Antes, `%B` daba el mes en ingles en medio de una frase en castellano
(«18 de November de 2026»).
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.services._pdf_marca import PALETA_POR_DEFECTO, TINTES_DE_FIRMA
from app.core.constantes import NOMBRE_DEL_PRODUCTO

#: Etiquetas del certificado en los 8 idiomas del portal (lo que falte, en castellano).
ETIQUETAS = {
    "es": {"titulo": "CERTIFICADO DE FIRMA DIGITAL", "sub": "Documento firmado electrónicamente",
           "firmado": "DOCUMENTO FIRMADO", "documento": "Documento", "doc_titulo": "Título", "proyecto": "Proyecto",
           "descripcion": "Descripción", "archivo": "Archivo original", "firmante": "Firmante", "nombre": "Nombre",
           "email": "Email", "cargo": "Cargo", "fecha": "Fecha", "hash": "Código de verificación (SHA-256)",
           "aviso": "Este certificado acredita que el documento fue revisado y aceptado electrónicamente por el "
                    "firmante identificado. El código SHA-256 garantiza la integridad del registro."},
    "en": {"titulo": "DIGITAL SIGNATURE CERTIFICATE", "sub": "Electronically signed document",
           "firmado": "DOCUMENT SIGNED", "documento": "Document", "doc_titulo": "Title", "proyecto": "Project",
           "descripcion": "Description", "archivo": "Original file", "firmante": "Signer", "nombre": "Name",
           "email": "Email", "cargo": "Job title", "fecha": "Date", "hash": "Verification code (SHA-256)",
           "aviso": "This certificate attests that the document was reviewed and accepted electronically by the "
                    "identified signer. The SHA-256 code guarantees the integrity of the record."},
    "fr": {"titulo": "CERTIFICAT DE SIGNATURE NUMÉRIQUE", "sub": "Document signé électroniquement",
           "firmado": "DOCUMENT SIGNÉ", "documento": "Document", "doc_titulo": "Titre", "proyecto": "Projet",
           "descripcion": "Description", "archivo": "Fichier d'origine", "firmante": "Signataire", "nombre": "Nom",
           "email": "E-mail", "cargo": "Fonction", "fecha": "Date", "hash": "Code de vérification (SHA-256)",
           "aviso": "Ce certificat atteste que le document a été examiné et accepté électroniquement par le "
                    "signataire identifié. Le code SHA-256 garantit l'intégrité de l'enregistrement."},
    "de": {"titulo": "ZERTIFIKAT DER DIGITALEN SIGNATUR", "sub": "Elektronisch signiertes Dokument",
           "firmado": "DOKUMENT SIGNIERT", "documento": "Dokument", "doc_titulo": "Titel", "proyecto": "Projekt",
           "descripcion": "Beschreibung", "archivo": "Originaldatei", "firmante": "Unterzeichner", "nombre": "Name",
           "email": "E-Mail", "cargo": "Position", "fecha": "Datum", "hash": "Prüfcode (SHA-256)",
           "aviso": "Dieses Zertifikat bestätigt, dass das Dokument vom angegebenen Unterzeichner elektronisch "
                    "geprüft und akzeptiert wurde. Der SHA-256-Code garantiert die Integrität des Datensatzes."},
    "it": {"titulo": "CERTIFICATO DI FIRMA DIGITALE", "sub": "Documento firmato elettronicamente",
           "firmado": "DOCUMENTO FIRMATO", "documento": "Documento", "doc_titulo": "Titolo", "proyecto": "Progetto",
           "descripcion": "Descrizione", "archivo": "File originale", "firmante": "Firmatario", "nombre": "Nome",
           "email": "Email", "cargo": "Ruolo", "fecha": "Data", "hash": "Codice di verifica (SHA-256)",
           "aviso": "Questo certificato attesta che il documento è stato esaminato e accettato elettronicamente "
                    "dal firmatario identificato. Il codice SHA-256 garantisce l'integrità del registro."},
    "pt": {"titulo": "CERTIFICADO DE ASSINATURA DIGITAL", "sub": "Documento assinado eletronicamente",
           "firmado": "DOCUMENTO ASSINADO", "documento": "Documento", "doc_titulo": "Título", "proyecto": "Projeto",
           "descripcion": "Descrição", "archivo": "Ficheiro original", "firmante": "Signatário", "nombre": "Nome",
           "email": "Email", "cargo": "Cargo", "fecha": "Data", "hash": "Código de verificação (SHA-256)",
           "aviso": "Este certificado atesta que o documento foi revisto e aceite eletronicamente pelo signatário "
                    "identificado. O código SHA-256 garante a integridade do registo."},
    "pl": {"titulo": "CERTYFIKAT PODPISU CYFROWEGO", "sub": "Dokument podpisany elektronicznie",
           "firmado": "DOKUMENT PODPISANY", "documento": "Dokument", "doc_titulo": "Tytuł", "proyecto": "Projekt",
           "descripcion": "Opis", "archivo": "Plik oryginalny", "firmante": "Podpisujący", "nombre": "Imię i nazwisko",
           "email": "E-mail", "cargo": "Stanowisko", "fecha": "Data", "hash": "Kod weryfikacyjny (SHA-256)",
           "aviso": "Niniejszy certyfikat potwierdza, że dokument został sprawdzony i zaakceptowany elektronicznie "
                    "przez wskazanego podpisującego. Kod SHA-256 gwarantuje integralność zapisu."},
    "zh": {"titulo": "数字签名证书", "sub": "电子签署的文件", "firmado": "文件已签署", "documento": "文件",
           "doc_titulo": "标题", "proyecto": "项目", "descripcion": "描述", "archivo": "原始文件", "firmante": "签署人",
           "nombre": "姓名", "email": "邮箱", "cargo": "职务", "fecha": "日期", "hash": "验证码（SHA-256）",
           "aviso": "本证书证明该文件已由所标识的签署人以电子方式审阅并接受。SHA-256 代码保证记录的完整性。"},
}


def etiquetas(idioma) -> dict:
    """Las etiquetas del certificado en `idioma` (castellano para lo que falte)."""
    from app.services.traduccion.idiomas import normalizar
    return {**ETIQUETAS[IDIOMA_DE_RESPALDO], **ETIQUETAS.get(normalizar(idioma) or IDIOMA_DE_RESPALDO, {})}


def _fecha_de_firma(signed_at: datetime, idioma, zona=None) -> str:
    """Fecha y hora (con segundos) de la firma en el formato del idioma y la zona, con su etiqueta."""
    from datetime import timezone
    from app.services.formato_regional import formato_de_fecha
    momento = signed_at if signed_at.tzinfo else signed_at.replace(tzinfo=timezone.utc)
    momento = momento.astimezone(zona or timezone.utc)
    return f"{momento.strftime(formato_de_fecha(idioma) + ' %H:%M:%S')} {momento.tzname() or 'UTC'}"


#: Tintes propios de este documento; ver la nota de la cabecera.
_GRIS_DE_CUERPO = TINTES_DE_FIRMA["gris_de_cuerpo"]
_SOMBREADO_DE_FILA = TINTES_DE_FIRMA["sombreado_de_fila"]
_FONDO_DEL_SELLO = TINTES_DE_FIRMA["fondo_del_sello"]
_FONDO_DE_EVIDENCIA = PALETA_POR_DEFECTO.fila_alterna


def generate_signed_pdf(
    document_title: str,
    document_description: str,
    signer_name: str,
    signer_email: str,
    signer_job_title: str,
    project_name: str,
    signed_at: datetime,
    signature_ip: str = "",
    original_file_name: str = "",
    paleta=None,
    idioma=None,
    marca=None,
    zona=None,
) -> bytes:
    """
    Genera un PDF certificado de firma digital del documento.
    Incluye: datos del firmante, timestamp, IP y un hash de evidencia.
    `idioma`, `marca` y `zona` los resuelve quien llama (tiene el `db`).
    """
    import hashlib

    # La resuelve el llamador con `marca_de_organizacion()`, que tiene el
    # `db` y el `organization_id`.
    paleta = paleta or PALETA_POR_DEFECTO
    et = etiquetas(idioma)
    cuando = _fecha_de_firma(signed_at, idioma or IDIOMA_DE_RESPALDO, zona)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)

    ACCENT  = paleta.color("acento")
    GREEN   = paleta.color("exito")
    GREY    = paleta.color("texto_secundario")
    BORDER  = paleta.color("linea_separadora")
    BG_CERT = colors.HexColor(_FONDO_DEL_SELLO)
    # El gris va dentro de una etiqueta `<font color>` del marcado de
    # ReportLab, asi que hace falta el hexadecimal y no el objeto Color.
    GRIS_HEX = paleta.texto_secundario

    styles = getSampleStyleSheet()

    # Hash de evidencia (SHA256 de los datos clave)
    evidence_str = f"{document_title}|{signer_email}|{signed_at.isoformat()}|{signature_ip}"
    evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements.append(Paragraph(marca or NOMBRE_DEL_PRODUCTO, ParagraphStyle("Brand",
        parent=styles["Normal"], fontSize=13, fontName="Helvetica-Bold",
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=4)))

    elements.append(Paragraph(et["titulo"], ParagraphStyle("CertTitle",
        parent=styles["Title"], fontSize=20, fontName="Helvetica-Bold",
        textColor=paleta.color("texto_principal"), alignment=TA_CENTER, spaceAfter=4)))

    elements.append(Paragraph(et["sub"], ParagraphStyle("Sub",
        parent=styles["Normal"], fontSize=11, textColor=GREY,
        alignment=TA_CENTER, spaceAfter=16)))

    elements.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=20))

    # ── Estado de firma ────────────────────────────────────────────────────────
    status_table = Table([[
        Paragraph("✓", ParagraphStyle("Check", parent=styles["Normal"],
                  fontSize=28, fontName="Helvetica-Bold", textColor=GREEN, alignment=TA_CENTER)),
        Paragraph(
            f"<b>{et['firmado']}</b><br/>"
            f"<font color='{GRIS_HEX}' size='10'>{cuando}</font>",
            ParagraphStyle("StatusText", parent=styles["Normal"],
                          fontSize=14, fontName="Helvetica-Bold",
                          textColor=paleta.color("texto_principal")),
        )
    ]], colWidths=[2*cm, "80%"])
    status_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), BG_CERT),
        ("BOX",         (0,0), (-1,-1), 1.5, GREEN),
        ("ROUNDEDCORNERS", [8]),
        ("PADDING",     (0,0), (-1,-1), 14),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 20))

    # ── Datos del documento ────────────────────────────────────────────────────
    elements.append(Paragraph(et["documento"], ParagraphStyle("Section",
        parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor(_GRIS_DE_CUERPO), spaceAfter=8, spaceBefore=4)))

    doc_data = [
        [et["doc_titulo"],  document_title],
        [et["proyecto"],    project_name],
        [et["descripcion"], document_description or "—"],
    ]
    if original_file_name:
        doc_data.append([et["archivo"], original_file_name])

    doc_table = Table(doc_data, colWidths=["25%", "75%"])
    doc_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), GREY),
        ("TEXTCOLOR",   (1,0), (1,-1), paleta.color("texto_principal")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor(_SOMBREADO_DE_FILA)]),
        ("BOX",         (0,0), (-1,-1), 0.5, BORDER),
        ("INNERGRID",   (0,0), (-1,-1), 0.25, BORDER),
        ("PADDING",     (0,0), (-1,-1), 8),
    ]))
    elements.append(doc_table)
    elements.append(Spacer(1, 20))

    # ── Datos del firmante ────────────────────────────────────────────────────
    elements.append(Paragraph(et["firmante"], ParagraphStyle("Section2",
        parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor(_GRIS_DE_CUERPO), spaceAfter=8, spaceBefore=4)))

    signer_data = [
        [et["nombre"], signer_name],
        [et["email"],  signer_email],
        [et["cargo"],  signer_job_title or "—"],
        [et["fecha"],  cuando],
    ]
    if signature_ip:
        signer_data.append(["IP",  signature_ip])

    signer_table = Table(signer_data, colWidths=["25%", "75%"])
    signer_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), GREY),
        ("TEXTCOLOR",   (1,0), (1,-1), paleta.color("texto_principal")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor(_SOMBREADO_DE_FILA)]),
        ("BOX",         (0,0), (-1,-1), 0.5, BORDER),
        ("INNERGRID",   (0,0), (-1,-1), 0.25, BORDER),
        ("PADDING",     (0,0), (-1,-1), 8),
    ]))
    elements.append(signer_table)
    elements.append(Spacer(1, 20))

    # ── Hash de evidencia ──────────────────────────────────────────────────────
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=12))

    elements.append(Paragraph(et["hash"], ParagraphStyle("HashLabel",
        parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold",
        textColor=GREY, spaceAfter=4)))

    elements.append(Paragraph(
        f"<font name='Courier' size='8'>{evidence_hash[:32]}<br/>{evidence_hash[32:]}</font>",
        ParagraphStyle("Hash", parent=styles["Normal"],
                      fontSize=8, textColor=colors.HexColor(_GRIS_DE_CUERPO),
                      backColor=colors.HexColor(_FONDO_DE_EVIDENCIA), spaceAfter=12,
                      leftIndent=10, rightIndent=10, borderPad=6)
    ))

    elements.append(Paragraph(
        et["aviso"],
        ParagraphStyle("Disclaimer", parent=styles["Normal"],
                      fontSize=8, textColor=GREY, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
