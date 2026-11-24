"""«Mi cuaderno»: ficheros e instantáneas al borrar (antes al final de `app/models/cuaderno.py`).

Las filas se borran por el ORM (pantalla, papelera, retención, RGPD): antes de
confirmar se apuntan las claves de fichero y las páginas; después de confirmar
se borran del almacén y de `document_collab_snapshots`. Si la transacción se
deshace, no se toca nada.

23-11-2026 (prueba global): sale del modelo porque un modelo no importa servicios
(`file_storage`) y para no cerrar el ciclo modelo -> app/db -> modelo. Lo registra
`app/models/__init__.py` cuando ya están cargados todos los modelos.
"""
from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_CLAVE = "cuaderno_pendiente_de_borrar"


def _apuntar(session, flush_context) -> None:
    from app.models.cuaderno import NotebookAttachment, NotebookPage
    ficheros, paginas = [], []
    for obj in session.deleted:
        if isinstance(obj, NotebookAttachment) and obj.file_key:
            ficheros.append(obj.file_key)
        elif isinstance(obj, NotebookPage):
            paginas.append(obj.id)
    if ficheros or paginas:
        p = session.info.setdefault(_CLAVE, {"ficheros": [], "paginas": []})
        p["ficheros"].extend(ficheros)
        p["paginas"].extend(paginas)


def _tras_borrar(session) -> None:
    pendiente = session.info.pop(_CLAVE, None)
    if not pendiente:
        return
    if pendiente["ficheros"]:
        try:
            from app.services.s3_service import file_storage
            for clave in pendiente["ficheros"]:
                try:
                    file_storage.delete_file(clave)
                except Exception:  # noqa: BLE001 - un fichero que no está no impide el resto
                    log.warning("cuaderno: no se pudo borrar el fichero %s", clave, exc_info=True)
        except Exception:  # noqa: BLE001
            log.warning("cuaderno: almacén no disponible al borrar", exc_info=True)
    if pendiente["paginas"]:
        try:
            from app.db.contexto_de_tenant import declarar_sistema
            from app.db.session import SessionLocal, sin_filtro_de_tenant
            from app.models.document_collab import DocumentCollabSnapshot
            with SessionLocal() as s:
                declarar_sistema(s, "cuaderno: borrar instantáneas de páginas borradas")
                with sin_filtro_de_tenant(s):
                    s.query(DocumentCollabSnapshot).filter(
                        DocumentCollabSnapshot.document_id.in_(pendiente["paginas"])).delete(synchronize_session=False)
                s.commit()
        except Exception:  # noqa: BLE001
            log.warning("cuaderno: no se pudieron borrar las instantáneas", exc_info=True)


def _descartar(session) -> None:
    session.info.pop(_CLAVE, None)


def registrar() -> None:
    if not event.contains(Session, "after_flush", _apuntar):
        event.listen(Session, "after_flush", _apuntar)
        event.listen(Session, "after_commit", _tras_borrar)
        event.listen(Session, "after_rollback", _descartar)
