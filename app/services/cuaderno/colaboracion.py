"""Edición simultánea de una página (Yjs): instantáneas en `document_collab_snapshots`.

Reutiliza la infraestructura de los documentos: la sala `/ws/notebook/{page_id}`
(app/api/v1/endpoints/ws.py, mismo protocolo que `/ws/doc`) reparte las
actualizaciones Yjs entre quienes tienen la página abierta, y el estado se
persiste aquí con cada guardado automático (`document_id` = id de la página,
`metadata_json` `{"kind": "notebook_page"}`), con tope de tamaño y de historial
(`CUADERNO_COLLAB_HISTORY_MAX`). Leer la instantánea exige poder leer la página.
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

_META = json.dumps({"kind": "notebook_page"})


def _tope() -> int:
    from app.core.config import settings
    return int(getattr(settings, "CUADERNO_PAGE_MAX_BYTES", 2 * 1024 * 1024) or 2 * 1024 * 1024) * 2


def guardar(db: Session, usuario, pagina, estado_b64: str) -> None:
    """Guarda el estado Yjs de la página (base64). No confirma."""
    from app.core.config import settings
    from app.models.document_collab import DocumentCollabSnapshot
    try:
        datos = base64.b64decode(estado_b64, validate=True)
    except (binascii.Error, ValueError):
        raise error(422, "cuaderno_estado_no_valido")
    if len(datos) > _tope():
        raise error(413, "cuaderno_pagina_demasiado_grande", max=_tope() // 1024)
    previa = db.query(DocumentCollabSnapshot).filter(DocumentCollabSnapshot.document_id == pagina.id,
                                                     DocumentCollabSnapshot.is_current.is_(True)) \
        .order_by(desc(DocumentCollabSnapshot.clock)).first()
    reloj = (previa.clock + 1) if previa else 1
    db.query(DocumentCollabSnapshot).filter(DocumentCollabSnapshot.document_id == pagina.id,
                                            DocumentCollabSnapshot.is_current.is_(True)) \
        .update({"is_current": False}, synchronize_session=False)
    db.add(DocumentCollabSnapshot(organization_id=pagina.organization_id, document_id=pagina.id, state_vector=datos,
                                  clock=reloj, size_bytes=len(datos), is_current=True, created_by=usuario.id,
                                  metadata_json=_META))
    db.flush()
    maximo = int(getattr(settings, "CUADERNO_COLLAB_HISTORY_MAX", 20) or 0)
    if maximo > 0:
        sobran = [i for (i,) in db.query(DocumentCollabSnapshot.id).filter(
            DocumentCollabSnapshot.document_id == pagina.id).order_by(desc(DocumentCollabSnapshot.clock)).offset(maximo)]
        if sobran:
            db.query(DocumentCollabSnapshot).filter(DocumentCollabSnapshot.id.in_(sobran)) \
                .delete(synchronize_session=False)


def cargar(db: Session, pagina_id: str) -> Optional[str]:
    """El estado Yjs vigente en base64 (o None)."""
    from app.models.document_collab import DocumentCollabSnapshot
    s = db.query(DocumentCollabSnapshot).filter(DocumentCollabSnapshot.document_id == pagina_id,
                                                DocumentCollabSnapshot.is_current.is_(True)) \
        .order_by(desc(DocumentCollabSnapshot.clock)).first()
    return base64.b64encode(s.state_vector).decode("ascii") if s and s.state_vector else None


def invalidar(db: Session, pagina_id: str) -> None:
    """El servidor cambió el JSON de la página: la próxima apertura parte del JSON, no del estado Yjs."""
    from app.models.document_collab import DocumentCollabSnapshot
    db.query(DocumentCollabSnapshot).filter(DocumentCollabSnapshot.document_id == pagina_id) \
        .delete(synchronize_session=False)
