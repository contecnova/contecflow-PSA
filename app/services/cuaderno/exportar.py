"""Exportar una página, una sección o un cuaderno a Markdown o PDF.

Sirve también para la portabilidad (RGPD art. 20): la persona descarga sus
notas en formatos abiertos. Exporta quien puede leer; cada exportación queda
en `audit_logs` (`EXPORT`, con el formato y cuántas páginas).
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cuaderno import acceso, contenido
from app.services.cuaderno.acceso import LEER

FORMATOS = {"md": "text/markdown; charset=utf-8", "pdf": "application/pdf"}


def _nombre(texto: str) -> str:
    limpio = re.sub(r"[^\w\- ]+", "", texto or "", flags=re.U).strip().replace(" ", "_")
    return (limpio or "cuaderno")[:80]


def _en_orden(paginas: list) -> list:
    """Páginas en el orden del árbol (cada padre seguido de sus subpáginas)."""
    hijos: dict = {}
    for p in paginas:
        hijos.setdefault(p.parent_id, []).append(p)
    ids = {p.id for p in paginas}
    salida: list = []

    def ir(padre, nivel):
        for p in sorted(hijos.get(padre, []), key=lambda x: (x.sort_order, x.created_at or 0)):
            salida.append((p, nivel))
            ir(p.id, nivel + 1)

    ir(None, 0)
    for p in paginas:   # huérfanas (su padre está en otra sección o en la papelera)
        if p.parent_id and p.parent_id not in ids:
            salida.append((p, 0))
            ir(p.id, 1)
    return salida


def paginas_de(db: Session, usuario, tipo: str, oid: str) -> tuple[str, list]:
    """(título, [(página, nivel)]) legibles de lo pedido."""
    from app.models.cuaderno import NotebookPage, NotebookSection
    if tipo == "page":
        p, _ = acceso.pagina(db, usuario, oid, LEER)
        return p.title or "—", [(p, 0)]
    if tipo == "section":
        s, _ = acceso.seccion(db, usuario, oid, LEER)
        filas = db.query(NotebookPage).filter(NotebookPage.section_id == s.id, NotebookPage.deleted_at.is_(None)).all()
        return s.title, _en_orden(filas)
    if tipo == "notebook":
        from app.models.cuaderno import Notebook
        if not _es_cuaderno_visible(db, usuario, oid):
            raise error(404, "no_encontrado", que="cuaderno")
        nb = db.get(Notebook, oid)
        permiso = acceso.permiso_en_cuaderno(db, usuario, nb)
        _, por_seccion = acceso.permisos_compartidos(db, usuario)
        secciones = [s for s in db.query(NotebookSection).filter(NotebookSection.notebook_id == nb.id,
                                                                  NotebookSection.deleted_at.is_(None))
                     .order_by(NotebookSection.sort_order) if permiso or s.id in por_seccion]
        salida = []
        for s in secciones:
            filas = db.query(NotebookPage).filter(NotebookPage.section_id == s.id,
                                                  NotebookPage.deleted_at.is_(None)).all()
            salida.extend(_en_orden(filas))
        return nb.title, salida
    raise error(422, "cuaderno_tipo_no_valido")


def _es_cuaderno_visible(db: Session, usuario, oid: str) -> bool:
    from app.models.cuaderno import Notebook, NotebookSection
    nb = db.get(Notebook, oid)
    if nb is None:
        return False
    if acceso.permiso_en_cuaderno(db, usuario, nb):
        return True
    _, por_seccion = acceso.permisos_compartidos(db, usuario)
    return bool(por_seccion) and db.query(NotebookSection.id).filter(
        NotebookSection.notebook_id == nb.id, NotebookSection.id.in_(list(por_seccion))).first() is not None


def _mapa_de_etiquetas(db: Session, usuario) -> dict:
    from app.services.cuaderno.servicio import etiquetas
    return {e["key"]: e["label"] for e in etiquetas(db, usuario)}


def generar(paginas: list, titulo: str, formato: str, etiquetas: Optional[dict] = None,
            idioma: Optional[str] = None) -> bytes:
    """Markdown o PDF de [(página, nivel)] (sin permisos: para RGPD y acceso excepcional)."""
    docs = [(("  " * 0) + (p.title or "—"), contenido.cargar(p.content)) for p, _ in paginas]
    if formato == "pdf":
        return contenido.a_pdf(docs, titulo, idioma, etiquetas)
    partes = [f"# {titulo}\n"] if len(paginas) > 1 else []
    for (p, nivel), (_, doc) in zip(paginas, docs):
        cabecera = "#" * min(6, (2 if len(paginas) > 1 else 1) + nivel)
        fecha = (p.updated_at or p.created_at)
        partes.append(f"{cabecera} {p.title or '—'}\n\n" + (f"_{fecha:%Y-%m-%d %H:%M}_\n\n" if fecha else "")
                      + contenido.a_markdown(doc, etiquetas))
    return "\n".join(partes).encode("utf-8")


def exportar(db: Session, usuario, tipo: str, oid: str, formato: str) -> tuple[bytes, str, str]:
    """(bytes, nombre de fichero, tipo MIME). Auditado."""
    if formato not in FORMATOS:
        raise error(422, "cuaderno_formato_no_valido")
    titulo, paginas = paginas_de(db, usuario, tipo, oid)
    from app.services.formato_regional import idioma_de_salida
    idioma = idioma_de_salida(db, user_id=usuario.id, org_id=getattr(usuario, "organization_id", None))
    datos = generar(paginas, titulo, formato, _mapa_de_etiquetas(db, usuario), idioma)
    audit_log(db, usuario, "EXPORT", f"notebook_{tipo}" if tipo != "notebook" else "notebook", oid, titulo,
              metadata={"format": formato, "pages": len(paginas)})
    return datos, f"{_nombre(titulo)}.{formato}", FORMATOS[formato]
