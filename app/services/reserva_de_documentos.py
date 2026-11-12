"""Reserva de documentos para editar: check-out / check-in (revisión 2026-11, lo que contecmind tenía).

Mientras una persona tiene un documento reservado, nadie más puede subir una
versión nueva, cambiar sus datos, archivarlo ni guardar la edición
colaborativa: la petición recibe 423 (Locked) diciendo quién lo tiene y hasta
cuándo. Así dos personas no pisan la misma versión.

- La reserva caduca sola a las `DOCUMENT_CHECKOUT_HOURS` (ajuste de la
  empresa): una reserva olvidada no bloquea para siempre.
- La libera quien la tiene (check-in) o, a la fuerza, quien administra el
  documento (nivel `admin` del documento o admin de la empresa); queda en el
  registro de auditoría quién la forzó.
- Reservar exige poder editar el documento.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.errores import ErrorDeDominio



def _aware(valor: Optional[datetime]) -> Optional[datetime]:
    if valor is None or valor.tzinfo:
        return valor
    return valor.replace(tzinfo=timezone.utc)   # SQLite devuelve sin zona


def vigente(doc) -> Optional[dict]:
    """La reserva activa del documento, o None si no tiene o ya caducó."""
    if not doc.checked_out_by:
        return None
    caduca = _aware(doc.checkout_expires_at)
    if caduca is not None and caduca <= datetime.now(timezone.utc):
        return None
    quien = getattr(doc, "checkout_user", None)
    return {"user_id": doc.checked_out_by, "user_name": getattr(quien, "full_name", None),
            "at": _aware(doc.checked_out_at).isoformat() if doc.checked_out_at else None,
            "expires_at": caduca.isoformat() if caduca else None}


def para_mostrar(doc, usuario) -> Optional[dict]:
    reserva = vigente(doc)
    if reserva is not None:
        reserva["mine"] = reserva["user_id"] == getattr(usuario, "id", None)
    return reserva


def exigir_libre(doc, usuario) -> None:
    """423 si otra persona tiene el documento reservado."""
    reserva = vigente(doc)
    if reserva is not None and reserva["user_id"] != usuario.id:
        raise ErrorDeDominio(423, detail={
            "message": f"El documento está reservado por {reserva['user_name'] or 'otra persona'} "
                       f"hasta {reserva['expires_at']}",
            "checkout": reserva})


def _horas(db, org) -> int:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, "DOCUMENT_CHECKOUT_HOURS", org) or settings.DOCUMENT_CHECKOUT_HOURS)


def reservar(db, doc, usuario) -> dict:
    from app.models.documents import DocumentAccessLevel
    from app.services.audit import audit_log
    from app.services.documents_service import check_document_access
    check_document_access(doc, usuario, DocumentAccessLevel.editor)
    exigir_libre(doc, usuario)
    ahora = datetime.now(timezone.utc)
    doc.checked_out_by, doc.checked_out_at = usuario.id, ahora
    doc.checkout_expires_at = ahora + timedelta(hours=_horas(db, usuario.organization_id))
    audit_log(db, usuario, "CHECKOUT", "documents", doc.id, doc.title,
              metadata={"expires_at": doc.checkout_expires_at.isoformat()})
    db.commit()
    db.refresh(doc)
    return para_mostrar(doc, usuario)


def liberar(db, doc, usuario, *, forzar: bool = False) -> None:
    from app.models.documents import DocumentAccessLevel
    from app.services.audit import audit_log
    from app.services.documents_service import check_document_access
    reserva = vigente(doc)
    if reserva is None:
        doc.checked_out_by = doc.checked_out_at = doc.checkout_expires_at = None
        db.commit()
        return
    if reserva["user_id"] != usuario.id:
        if not forzar:
            raise ErrorDeDominio(409, "La reserva es de otra persona: solo quien administra el documento puede forzarla")
        check_document_access(doc, usuario, DocumentAccessLevel.admin)
    audit_log(db, usuario, "CHECKIN_FORCED" if reserva["user_id"] != usuario.id else "CHECKIN", "documents",
              doc.id, doc.title, metadata={"held_by": reserva["user_id"], "held_since": reserva["at"]})
    doc.checked_out_by = doc.checked_out_at = doc.checkout_expires_at = None
    db.commit()
