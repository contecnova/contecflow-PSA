"""Adjuntos, imágenes pegadas, dibujos y voz de «Mi cuaderno».

- Adjuntos e imágenes: por el validador central de subidas
  (`app.core.uploads`, perfil ATTACHMENT: tamaño, extensión, tipo real, sin
  ejecutables) y el almacén común (`s3_service.file_storage`, disco o S3).
  Se sirven por `/notebook/attachments/{id}/file` solo a quien puede leer la
  página; lo que no es imagen rasterizada se descarga (nunca se pinta un SVG
  o un HTML subido).
- Dibujos: el navegador manda los trazos (JSON) y el SVG lo genera el
  servidor (sin texto libre ni scripts posibles); los trazos se guardan en
  `meta` para volver a editarlo.
- Voz: el audio pasa por `validate_audio_upload` y se transcribe con la
  transcripción de la empresa (`reuniones.transcripcion.transcribir`: los
  proveedores permitidos, el tope de gasto y el contrato del STT externo). El
  audio no se guarda salvo que se pida (`keep_audio`).
"""
from __future__ import annotations
import logging

import json
from typing import Any, Optional

#: Item 36: el servicio no importa FastAPI. Recibe el `UploadFile` de la ruta (o
#: cualquier objeto con `filename`, `content_type` y `file`).
FicheroSubido = Any
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cuaderno import acceso
from app.services.cuaderno.acceso import EDITAR, LEER

#: Imágenes que se pintan en la página (el resto se descarga).
IMAGENES_EN_LINEA = {"image/png", "image/jpeg", "image/gif", "image/webp"}
COLORES_DE_TRAZO = {"ink": "#1f2937", "blue": "#2563eb", "red": "#dc2626", "green": "#16a34a",
                    "amber": "#d97706", "purple": "#7c3aed", "white": "#ffffff"}
MAX_TRAZOS, MAX_PUNTOS = 2000, 5000


def _org(u):
    return getattr(u, "organization_id", None)


def _a_dict(a) -> dict:
    return {"id": a.id, "kind": a.kind, "file_name": a.file_name, "mime_type": a.mime_type, "size_bytes": a.size_bytes,
            "url": f"/api/v1/notebook/attachments/{a.id}/file",
            "created_at": a.created_at.isoformat() if a.created_at else None}


def _guardar_fichero(contenido: bytes, nombre: str, carpeta: str, mime: str) -> tuple[str, int]:
    from app.services.s3_service import file_storage
    return file_storage.upload_file(file_content=contenido, file_name=nombre, document_id=carpeta, version_num=1,
                                    content_type=mime or "application/octet-stream")


def subir(db: Session, usuario, page_id: str, fichero: FicheroSubido) -> dict:
    from app.core.uploads import UploadProfile, read_and_validate_upload_sync, safe_filename
    from app.models.cuaderno import NotebookAttachment
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    datos = read_and_validate_upload_sync(fichero, UploadProfile.ATTACHMENT)
    nombre = safe_filename(fichero.filename, fallback="adjunto")
    mime = (fichero.content_type or "application/octet-stream").split(";")[0].strip().lower()
    clave, tam = _guardar_fichero(datos, nombre, f"notebook-{p.id}", mime)
    a = NotebookAttachment(organization_id=p.organization_id, page_id=p.id, owner_id=p.owner_id,
                           kind="image" if mime in IMAGENES_EN_LINEA else "file", file_key=clave, file_name=nombre,
                           mime_type=mime, size_bytes=tam, created_by=usuario.id)
    db.add(a)
    db.flush()
    audit_log(db, usuario, "CREATE", "notebook_attachment", a.id, nombre,
              metadata={"page_id": p.id, "size": tam, "mime": mime})
    return _a_dict(a)


def _num(v, minimo: float, maximo: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise error(422, "cuaderno_dibujo_no_valido")
    if x != x or x < minimo or x > maximo:
        raise error(422, "cuaderno_dibujo_no_valido")
    return round(x, 1)


def _validar_trazos(datos: dict) -> dict:
    ancho = _num(datos.get("width") or 800, 50, 4000)
    alto = _num(datos.get("height") or 500, 50, 4000)
    trazos = datos.get("strokes")
    if not isinstance(trazos, list) or len(trazos) > MAX_TRAZOS:
        raise error(422, "cuaderno_dibujo_no_valido")
    limpios = []
    for t in trazos:
        if not isinstance(t, dict) or not isinstance(t.get("points"), list) or not t["points"] \
                or len(t["points"]) > MAX_PUNTOS:
            raise error(422, "cuaderno_dibujo_no_valido")
        color = t.get("color") if t.get("color") in COLORES_DE_TRAZO else "ink"
        grosor = _num(t.get("width") or 2, 0.5, 60)
        puntos = [[_num(x, -10, ancho + 10), _num(y, -10, alto + 10)] for x, y in
                  (pt[:2] for pt in t["points"] if isinstance(pt, (list, tuple)) and len(pt) >= 2)]
        if puntos:
            limpios.append({"color": color, "width": grosor, "points": puntos, "erase": bool(t.get("erase"))})
    return {"width": ancho, "height": alto, "strokes": limpios}


def svg_de(dibujo: dict) -> str:
    """SVG generado en el servidor (solo trazados; sin texto ni scripts)."""
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dibujo["width"]} {dibujo["height"]}" '
              f'width="{dibujo["width"]}" height="{dibujo["height"]}">']
    for t in dibujo["strokes"]:
        pts = t["points"]
        d = f"M{pts[0][0]} {pts[0][1]}" + "".join(f" L{x} {y}" for x, y in pts[1:])
        if len(pts) == 1:
            d += f" L{pts[0][0] + 0.1} {pts[0][1]}"
        color = "#ffffff" if t.get("erase") else COLORES_DE_TRAZO[t["color"]]
        partes.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{t["width"]}" '
                      f'stroke-linecap="round" stroke-linejoin="round"/>')
    partes.append("</svg>")
    return "".join(partes)


def dibujo(db: Session, usuario, page_id: str, datos: dict, adjunto_id: Optional[str] = None) -> dict:
    """Crea o reemplaza un dibujo de la página."""
    from app.models.cuaderno import NotebookAttachment
    from app.services.s3_service import file_storage
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    limpio = _validar_trazos(datos)
    svg = svg_de(limpio).encode("utf-8")
    clave, tam = _guardar_fichero(svg, "dibujo.svg", f"notebook-{p.id}", "image/svg+xml")
    if adjunto_id:
        a = db.get(NotebookAttachment, adjunto_id)
        if a is None or a.page_id != p.id or a.kind != "drawing":
            raise error(404, "no_encontrado", que="dibujo")
        anterior = a.file_key
        a.file_key, a.size_bytes, a.meta = clave, tam, json.dumps(limpio)
        try:
            file_storage.delete_file(anterior)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).debug("dibujo: excepcion ignorada", exc_info=True)
        accion = "UPDATE"
    else:
        a = NotebookAttachment(organization_id=p.organization_id, page_id=p.id, owner_id=p.owner_id, kind="drawing",
                               file_key=clave, file_name="dibujo.svg", mime_type="image/svg+xml", size_bytes=tam,
                               meta=json.dumps(limpio), created_by=usuario.id)
        db.add(a)
        accion = "CREATE"
    db.flush()
    audit_log(db, usuario, accion, "notebook_drawing", a.id, "dibujo", metadata={"page_id": p.id})
    return {**_a_dict(a), "drawing": limpio}


def trazos(db: Session, usuario, adjunto_id: str) -> dict:
    from app.models.cuaderno import NotebookAttachment
    a = db.get(NotebookAttachment, adjunto_id)
    if a is None or a.kind != "drawing":
        raise error(404, "no_encontrado", que="dibujo")
    acceso.pagina(db, usuario, a.page_id, LEER)
    return {**_a_dict(a), "drawing": json.loads(a.meta or "{}")}


def leer(db: Session, usuario, adjunto_id: str) -> tuple[bytes, str, str, bool]:
    """(bytes, mime, nombre, en_linea). 404 si no se puede leer la página."""
    from app.models.cuaderno import NotebookAttachment
    from app.services.s3_service import file_storage
    a = db.get(NotebookAttachment, adjunto_id)
    if a is None:
        raise error(404, "no_encontrado", que="adjunto")
    acceso.pagina(db, usuario, a.page_id, LEER)
    try:
        datos = file_storage.get_file_bytes(a.file_key)
    except (FileNotFoundError, PermissionError):
        raise error(404, "no_encontrado", que="adjunto")
    en_linea = a.mime_type in IMAGENES_EN_LINEA or a.kind == "drawing"
    return datos, a.mime_type or "application/octet-stream", a.file_name, en_linea


def borrar(db: Session, usuario, adjunto_id: str) -> None:
    from app.models.cuaderno import NotebookAttachment
    a = db.get(NotebookAttachment, adjunto_id)
    if a is None:
        raise error(404, "no_encontrado", que="adjunto")
    acceso.pagina(db, usuario, a.page_id, EDITAR)
    audit_log(db, usuario, "DELETE", "notebook_attachment", a.id, a.file_name, metadata={"page_id": a.page_id})
    db.delete(a)


def transcribir(db: Session, usuario, page_id: str, fichero: FicheroSubido, idioma: Optional[str] = None,
                guardar_audio: bool = False) -> dict:
    """Transcribe una nota de voz con la transcripción de la empresa."""
    from app.core.config import settings
    from app.core.uploads import read_upload_within_limit_sync, safe_filename, validate_audio_upload
    from app.models.cuaderno import NotebookAttachment
    from app.services.cuaderno import config
    from app.services.reuniones.transcripcion import transcribir as stt
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    if not config.leer(db, _org(usuario)).get("voice_enabled", True):
        raise error(403, "cuaderno_voz_desactivada")
    tope = int(getattr(settings, "CUADERNO_VOICE_MAX_BYTES", 25 * 1024 * 1024) or 25 * 1024 * 1024)
    datos = read_upload_within_limit_sync(fichero, tope)
    nombre = safe_filename(fichero.filename, fallback="nota.webm")
    validate_audio_upload(nombre, datos)
    mime = (fichero.content_type or "audio/webm").split(";")[0].strip().lower()
    try:
        resultado = stt(db, _org(usuario), datos, nombre, mime, idioma)
    except ValueError as exc:
        from app.core.codigos_de_error import desde_valor
        raise desde_valor(422, exc)
    texto = (getattr(resultado, "text", "") or "").strip()
    salida = {"text": texto, "provider": getattr(resultado, "provider", None),
              "language": getattr(resultado, "language", None), "attachment": None}
    if guardar_audio:
        clave, tam = _guardar_fichero(datos, nombre, f"notebook-{p.id}", mime)
        a = NotebookAttachment(organization_id=p.organization_id, page_id=p.id, owner_id=p.owner_id, kind="audio",
                               file_key=clave, file_name=nombre, mime_type=mime, size_bytes=tam,
                               meta=json.dumps({"transcript": texto[:20000]}), created_by=usuario.id)
        db.add(a)
        db.flush()
        salida["attachment"] = _a_dict(a)
    audit_log(db, usuario, "TRANSCRIBE", "notebook_page", p.id, p.title or "—",
              metadata={"provider": salida["provider"], "kept_audio": bool(guardar_audio), "chars": len(texto)})
    return salida


def pagina_del_dibujo(db: Session, adjunto_id: str) -> str:
    """La página de un dibujo (el acceso lo comprueba `dibujo` con esa página)."""
    from app.models.cuaderno import NotebookAttachment
    a = db.get(NotebookAttachment, adjunto_id)
    if a is None:
        raise error(404, "no_encontrado", que="dibujo")
    return a.page_id
