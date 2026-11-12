"""contecmind como gestor documental de contecflow (revisión 2026-11).

Los documentos —procedimientos, manuales, contratos firmados, entregables—
viven en contecmind, con sus versiones, sus permisos, su lectura de escaneados
y su aprobación. contecflow guarda el ENLACE de cada documento con la ficha a
la que pertenece (`enlaces_documentales`) y la carpeta de contecmind de cada
ficha (`carpetas_documentales`), y llama con la identidad de quien está
usando contecflow: contecmind decide qué puede ver y hacer esa persona.

Medido en su OpenAPI el 05-11-2026. Lo que una aplicación anfitriona puede usar
y aquí se usa:

- `GET /documents/search` (buscar por tema), `GET /documents/{id}` (ficha),
  `GET /documents/{id}/raw` (el original), `POST /documents` (subir, multipart
  con `title`, `area_id`, `folder_id`, `file`; acepta `Idempotency-Key`);
- `GET/POST /folders` (árbol), `GET /folders/{id}/documents`,
  `POST /folders/{id}/summary` (pregunta sobre una carpeta, con citas);
- `GET/POST /documents/{id}/approval` (estado y petición de aprobación de una
  versión), `GET /areas`.

Lo que NO se puede desde aquí, y por qué:

- **Subir una versión nueva de un documento** existe sólo en
  `/admin/documents/{id}/control/versions`, cerrado a las integraciones. Se
  sube como documento nuevo; versionar es cosa de contecmind.
- **Preguntas sobre todo el corpus** (`/qa`, `/ask`): cerradas a las
  integraciones. Se pregunta sobre la carpeta de la ficha, que sí está abierta.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.conectores import fichas
from app.services.conectores.anfitrion import CONTECMIND, ErrorDeConector, _ajuste, configuracion, llamar
from app.core.errores import ErrorDeDominio

logger = logging.getLogger("contecflow.conectores.contecmind")

LEER = ("documents:read", "documents:search")
ESCRIBIR = ("documents:read", "documents:search", "documents:write")


def _hit(i: dict) -> dict:
    return {"document_id": str(i.get("document_id") or i.get("id")), "title": i.get("title") or "(sin título)",
            "snippet": i.get("snippet") or "", "score": i.get("score"), "media_kind": i.get("media_kind"),
            "matched_chunks": i.get("matched_chunks")}


# ── Lectura ───────────────────────────────────────────────────────────────────

def buscar(db: Session, usuario, texto: str, *, limite: Optional[int] = None,
           folder_id: Optional[str] = None) -> list[dict]:
    texto = (texto or "").strip()
    if len(texto) < 2:
        return []
    limite = limite or int(_ajuste(db, "CONTECMIND_SUGGEST_LIMIT", usuario.organization_id, "int"))
    params = {"q": texto[:500], "limit": max(1, min(limite, 100))}
    if folder_id:
        params.update(folder_id=folder_id, con_subcarpetas=True)
    r = llamar(db, CONTECMIND, usuario, "buscar", "GET", "/documents/search", alcances=LEER, params=params)
    return [_hit(i) for i in (r.json().get("items") or []) if isinstance(i, dict)][:limite]


def documento(db: Session, usuario, document_id: str) -> dict:
    r = llamar(db, CONTECMIND, usuario, "ficha", "GET", f"/documents/{document_id}", alcances=LEER)
    d = r.json()
    texto = d.get("extracted_text") or ""
    return {"id": str(d.get("id")), "title": d.get("title"), "mime_type": d.get("mime_type"),
            "size_bytes": d.get("size_bytes"), "status": d.get("status"), "media_kind": d.get("media_kind"),
            "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
            "review_deadline": d.get("review_deadline"), "locked_by": d.get("locked_by"),
            "lock_note": d.get("lock_note"), "chunk_count": d.get("chunk_count"),
            "metadata": d.get("doc_metadata") or {}, "error": d.get("error"),
            "extracto": texto[:4000], "extracto_recortado": len(texto) > 4000}


def original(db: Session, usuario, document_id: str):
    """`(contenido, tipo, nombre)` del fichero original."""
    r = llamar(db, CONTECMIND, usuario, "descargar", "GET", f"/documents/{document_id}/raw", alcances=LEER)
    nombre = None
    disp = r.headers.get("content-disposition") or ""
    if "filename=" in disp:
        nombre = disp.split("filename=", 1)[1].strip('"; ')
    return r.content, r.headers.get("content-type") or "application/octet-stream", nombre


def aprobacion(db: Session, usuario, document_id: str) -> dict:
    r = llamar(db, CONTECMIND, usuario, "aprobacion", "GET", f"/documents/{document_id}/approval", alcances=LEER)
    return r.json()


def pedir_aprobacion(db: Session, usuario, document_id: str, version_no: Optional[int] = None) -> dict:
    _exigir_escritura(db, usuario)
    r = llamar(db, CONTECMIND, usuario, "pedir_aprobacion", "POST", f"/documents/{document_id}/approval",
               alcances=ESCRIBIR, escribir=True, json={"version_no": version_no})
    return r.json()


def preguntar_carpeta(db: Session, usuario, folder_id: str, pregunta: str) -> dict:
    """Respuesta con citas sobre los documentos de la carpeta (y sus subcarpetas)."""
    r = llamar(db, CONTECMIND, usuario, "preguntar_carpeta", "POST", f"/folders/{folder_id}/summary",
               alcances=LEER, json={"pregunta": pregunta, "con_subcarpetas": True},
               plazo=max(60.0, float(_ajuste(db, "CONECTOR_TIMEOUT_SECONDS", usuario.organization_id, "float"))))
    d = r.json()
    citas = [{"document_id": str(c.get("document_id")), "title": c.get("document_title"),
              "text": (c.get("text") or "")[:600], "page": c.get("page_number")}
             for c in (d.get("citations") or []) if isinstance(c, dict)]
    return {"answer": d.get("answer") or "", "citations": citas, "documents": d.get("documents") or []}


def documentos_de_carpeta(db: Session, usuario, folder_id: str) -> list[dict]:
    r = llamar(db, CONTECMIND, usuario, "carpeta", "GET", f"/folders/{folder_id}/documents", alcances=LEER,
               params={"con_subcarpetas": True})
    return [{"id": str(d.get("id")), "title": d.get("title"), "mime_type": d.get("mime_type"),
             "size_bytes": d.get("size_bytes"), "status": d.get("status"), "updated_at": d.get("updated_at")}
            for d in (r.json().get("items") or []) if isinstance(d, dict)]


# ── Carpetas ──────────────────────────────────────────────────────────────────

def _exigir_escritura(db: Session, usuario) -> None:
    """Sin el rol alto en contecflow no se pregunta a contecmind: se sabe ya que no."""
    from app.services.conectores.anfitrion import puede_escribir
    if not puede_escribir(db, CONTECMIND, usuario):
        raise ErrorDeConector("sin_permiso", "Tu rol no puede subir documentos a contecmind "
                                             "(lo decide CONTECMIND_WRITER_ROLES en Admin)")


def _area(db: Session, usuario) -> str:
    cfg = configuracion(db, CONTECMIND, usuario.organization_id)
    if cfg.get("area_id"):
        return str(cfg["area_id"])
    r = llamar(db, CONTECMIND, usuario, "areas", "GET", "/areas", alcances=LEER)
    areas = r.json().get("items") or []
    if not areas:
        raise ErrorDeConector("sin_permiso", "No hay ninguna área de contecmind en la que escribir: "
                                             "configura el área en Ajustes → Integraciones → contecmind")
    return str(areas[0]["id"])


def _hija(db: Session, usuario, area_id: str, padre: Optional[str], nombre: str) -> str:
    params = {"area_id": area_id}
    if padre:
        params["parent_id"] = padre
    r = llamar(db, CONTECMIND, usuario, "carpetas", "GET", "/folders", alcances=ESCRIBIR, escribir=True,
               params=params)
    for c in r.json().get("items") or []:
        if c.get("name") == nombre and (str(c.get("parent_id") or "") == str(padre or "")):
            return str(c["id"])
    r = llamar(db, CONTECMIND, usuario, "crear_carpeta", "POST", "/folders", alcances=ESCRIBIR, escribir=True,
               json={"area_id": area_id, "name": nombre[:255], "parent_id": padre})
    return str(r.json()["id"])


def carpeta_de(db: Session, usuario, entidad: str, entidad_id: str, *, crear: bool = True) -> Optional[dict]:
    """La carpeta de la ficha: `{folder_id, area_id, ruta}`. Crearla exige poder escribir."""
    from app.models.conectores import CarpetaDocumental
    f, obj = fichas.cargar(db, usuario, entidad, entidad_id)
    fila = db.query(CarpetaDocumental).filter(CarpetaDocumental.entidad == entidad,
                                              CarpetaDocumental.entidad_id == str(entidad_id)).first()
    if fila is not None:
        return {"folder_id": fila.folder_id, "area_id": fila.area_id, "ruta": fila.ruta}
    if not crear:
        return None
    _exigir_escritura(db, usuario)
    area = _area(db, usuario)
    raiz = str(_ajuste(db, "CONTECMIND_ROOT_FOLDER", usuario.organization_id, "str") or "contecflow")
    id_raiz = _hija(db, usuario, area, None, raiz)
    id_tipo = _hija(db, usuario, area, id_raiz, f.carpeta)
    nombre = f.nombre(obj)
    id_ficha = _hija(db, usuario, area, id_tipo, nombre)
    fila = CarpetaDocumental(organization_id=usuario.organization_id, entidad=entidad, entidad_id=str(entidad_id),
                             folder_id=id_ficha, area_id=area, ruta=f"{raiz}/{f.carpeta}/{nombre}")
    db.add(fila)
    try:
        db.commit()
    except IntegrityError:   # otra petición la creó a la vez: vale la suya
        db.rollback()
        fila = db.query(CarpetaDocumental).filter(CarpetaDocumental.entidad == entidad,
                                                  CarpetaDocumental.entidad_id == str(entidad_id)).one()
    return {"folder_id": fila.folder_id, "area_id": fila.area_id, "ruta": fila.ruta}


# ── Enlaces con las fichas ────────────────────────────────────────────────────

def _enlace_dict(e) -> dict:
    return {"id": e.id, "document_id": e.document_id, "title": e.titulo, "mime_type": e.mime_type,
            "size_bytes": e.tamano, "origen": e.origen, "nota": e.nota, "created_by": e.created_by,
            "created_at": e.created_at.isoformat() if e.created_at else None}


def enlaces(db: Session, usuario, entidad: str, entidad_id: str) -> list[dict]:
    from app.models.conectores import EnlaceDocumental
    fichas.cargar(db, usuario, entidad, entidad_id)
    filas = (db.query(EnlaceDocumental)
             .filter(EnlaceDocumental.entidad == entidad, EnlaceDocumental.entidad_id == str(entidad_id))
             .order_by(EnlaceDocumental.created_at.desc()).all())
    return [_enlace_dict(e) for e in filas]


def _guardar_enlace(db: Session, usuario, entidad: str, entidad_id: str, doc: dict, origen: str,
                    nota: Optional[str]) -> dict:
    from app.models.conectores import EnlaceDocumental
    from app.services.audit import audit_log
    existente = (db.query(EnlaceDocumental)
                 .filter(EnlaceDocumental.entidad == entidad, EnlaceDocumental.entidad_id == str(entidad_id),
                         EnlaceDocumental.document_id == str(doc["id"])).first())
    if existente is not None:
        return _enlace_dict(existente)
    e = EnlaceDocumental(organization_id=usuario.organization_id, entidad=entidad, entidad_id=str(entidad_id),
                         document_id=str(doc["id"]), titulo=(doc.get("title") or "(sin título)")[:500],
                         mime_type=doc.get("mime_type"), tamano=doc.get("size_bytes"), origen=origen,
                         nota=(nota or None) and nota[:500], created_by=usuario.id)
    db.add(e)
    audit_log(db, usuario, "CREATE", "enlaces_documentales", f"{entidad}:{entidad_id}", e.titulo,
              new_values={"document_id": e.document_id, "origen": origen})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        e = (db.query(EnlaceDocumental)
             .filter(EnlaceDocumental.entidad == entidad, EnlaceDocumental.entidad_id == str(entidad_id),
                     EnlaceDocumental.document_id == str(doc["id"])).one())
    return _enlace_dict(e)


def enlazar(db: Session, usuario, entidad: str, entidad_id: str, document_id: str,
            nota: Optional[str] = None, origen: str = "enlazado") -> dict:
    """Enlaza un documento que ya existe. Se lee de contecmind con la identidad de quien enlaza:
    sólo se puede enlazar lo que esa persona puede ver allí."""
    fichas.cargar(db, usuario, entidad, entidad_id)
    doc = documento(db, usuario, document_id)
    return _guardar_enlace(db, usuario, entidad, entidad_id, doc, origen, nota)


def desenlazar(db: Session, usuario, entidad: str, entidad_id: str, enlace_id: str) -> None:
    """Quita el enlace. El documento sigue en contecmind: borrarlo es cosa de allí."""
    from app.models.conectores import EnlaceDocumental
    from app.services.audit import audit_log
    fichas.cargar(db, usuario, entidad, entidad_id)
    e = (db.query(EnlaceDocumental)
         .filter(EnlaceDocumental.id == enlace_id, EnlaceDocumental.entidad == entidad,
                 EnlaceDocumental.entidad_id == str(entidad_id)).first())
    if e is None:
        raise ErrorDeDominio(404, "Enlace no encontrado")
    audit_log(db, usuario, "DELETE", "enlaces_documentales", f"{entidad}:{entidad_id}", e.titulo,
              old_values={"document_id": e.document_id})
    db.delete(e)
    db.commit()


def subir(db: Session, usuario, entidad: str, entidad_id: str, contenido: bytes, nombre_fichero: str,
          tipo: Optional[str], titulo: Optional[str] = None, nota: Optional[str] = None) -> dict:
    """Sube el fichero a la carpeta de la ficha en contecmind y lo enlaza."""
    maximo = int(_ajuste(db, "CONTECMIND_UPLOAD_MAX_MB", usuario.organization_id, "int")) * 1024 * 1024
    if not contenido:
        raise ErrorDeDominio(400, "El fichero está vacío")
    if len(contenido) > maximo:
        raise ErrorDeDominio(413, f"El fichero pasa del máximo ({maximo // (1024 * 1024)} MB)")
    _exigir_escritura(db, usuario)
    carpeta = carpeta_de(db, usuario, entidad, entidad_id)
    # Reintentar la misma subida no crea dos documentos en contecmind.
    clave = hashlib.sha256(f"{entidad}:{entidad_id}:".encode() + contenido).hexdigest()
    r = llamar(db, CONTECMIND, usuario, "subir", "POST", "/documents", alcances=ESCRIBIR, escribir=True,
               data={"title": (titulo or nombre_fichero)[:500], "area_id": carpeta["area_id"],
                     "folder_id": carpeta["folder_id"]},
               files={"file": (nombre_fichero, contenido, tipo or "application/octet-stream")},
               headers={"Idempotency-Key": clave},
               plazo=max(60.0, float(_ajuste(db, "CONECTOR_TIMEOUT_SECONDS", usuario.organization_id, "float"))))
    return _guardar_enlace(db, usuario, entidad, entidad_id, r.json(), "subido", nota)


def sugerencias(db: Session, usuario, entidad: str, entidad_id: str) -> list[dict]:
    """Documentos que pueden servir para esta ficha, buscados por su texto, sin los ya enlazados."""
    f, obj = fichas.cargar(db, usuario, entidad, entidad_id)
    texto = " ".join(str(x) for x in (getattr(obj, "title", None) or getattr(obj, "name", None),
                                      (getattr(obj, "description", None) or "")[:400]) if x)
    ya = {e["document_id"] for e in enlaces(db, usuario, entidad, entidad_id)}
    return [h for h in buscar(db, usuario, texto) if h["document_id"] not in ya]
