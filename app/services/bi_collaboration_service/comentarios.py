"""Comentarios de panel: listado, alta y resolucion (con su formato heredado en JSON).

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.models.bi_collaboration import DashboardComment
from app.models.user import User

from app.services.bi_collaboration_service._comun import (
    COMMENTS_KEY,
    _emit_dashboard_notification,
    _get_json,
    _is_missing_table_error,
    _iso_now,
    _set_json,
    _table_exists,
)


def _legacy_list_comments(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: Optional[str] = None,
    widget_id: Optional[str] = None,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    if not isinstance(rows, list):
        rows = []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if dashboard_key and row.get("dashboard_key") != dashboard_key:
            continue
        if widget_id and row.get("widget_id") != widget_id:
            continue
        if not include_resolved and bool(row.get("resolved", False)):
            continue
        out.append({
            "id": row.get("id") or str(uuid.uuid4()),
            "dashboard_key": row.get("dashboard_key"),
            "widget_id": row.get("widget_id"),
            "message": row.get("message") or "",
            "author_id": row.get("author_id"),
            "author_name": row.get("author_name"),
            "resolved": bool(row.get("resolved", False)),
            "resolved_at": row.get("resolved_at"),
            "resolved_by": row.get("resolved_by"),
            "created_at": row.get("created_at"),
        })

    out.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return out


def list_comments(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: Optional[str] = None,
    widget_id: Optional[str] = None,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    if not _table_exists(db, "dashboard_comments"):
        return _legacy_list_comments(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            include_resolved=include_resolved,
        )

    try:
        q = db.query(DashboardComment)
        if organization_id:
            q = q.filter(DashboardComment.organization_id == organization_id)
        else:
            q = q.filter(DashboardComment.organization_id.is_(None))
        if dashboard_key:
            q = q.filter(DashboardComment.dashboard_key == dashboard_key)
        if widget_id:
            q = q.filter(DashboardComment.widget_id == widget_id)
        if not include_resolved:
            q = q.filter(DashboardComment.resolved.is_(False))
        rows = q.order_by(DashboardComment.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "dashboard_key": r.dashboard_key,
                "widget_id": r.widget_id,
                "message": r.message,
                "author_id": r.author_id,
                "author_name": r.author_name,
                "resolved": bool(r.resolved),
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "resolved_by": r.resolved_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        return _legacy_list_comments(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            include_resolved=include_resolved,
        )


def create_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    widget_id: str,
    message: str,
    author: User,
) -> dict[str, Any]:
    if not _table_exists(db, "dashboard_comments"):
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        payload = {
            "id": str(uuid.uuid4()),
            "dashboard_key": dashboard_key,
            "widget_id": widget_id,
            "message": message.strip(),
            "author_id": author.id,
            "author_name": author.full_name,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "created_at": _iso_now(),
        }
        legacy_rows.append(payload)
        _set_json(
            db,
            COMMENTS_KEY,
            organization_id,
            legacy_rows,
            description="BI Collaboration comments (legacy JSON fallback)",
        )
        return payload

    try:
        row = DashboardComment(
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            message=message.strip(),
            author_id=author.id,
            author_name=author.full_name,
            resolved=False,
        )
        db.add(row)
        _emit_dashboard_notification(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            event_type="comment_created",
            payload={"widget_id": widget_id, "author_id": author.id, "message": row.message[:200]},
        )
        db.commit()
        return {
            "id": row.id,
            "dashboard_key": row.dashboard_key,
            "widget_id": row.widget_id,
            "message": row.message,
            "author_id": row.author_id,
            "author_name": row.author_name,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        db.rollback()
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        payload = {
            "id": str(uuid.uuid4()),
            "dashboard_key": dashboard_key,
            "widget_id": widget_id,
            "message": message.strip(),
            "author_id": author.id,
            "author_name": author.full_name,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "created_at": _iso_now(),
        }
        legacy_rows.append(payload)
        _set_json(
            db,
            COMMENTS_KEY,
            organization_id,
            legacy_rows,
            description="BI Collaboration comments (legacy JSON fallback)",
        )
        return payload


def _resolver_en_json_heredado(db: Session, *, organization_id: Optional[str],
                               comment_id: str, current_user: User) -> dict[str, Any]:
    """Marca un comentario como resuelto en el respaldo JSON.

    Auditoría 2026-09 (hallazgo 18): este bloque estaba **escrito dos veces,
    palabra por palabra** dentro de `resolve_comment` —una para «la tabla no
    existe» y otra para «la consulta falló porque la tabla no existe»—, y era la
    mitad de sus 109 líneas. Son el mismo caso visto desde dos sitios, así que
    es una sola función.

    Levanta `comment_not_found` si no está: el respaldo no es una excusa para
    devolver éxito sobre algo que no se ha tocado.
    """
    filas = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    if not isinstance(filas, list):
        filas = []

    for fila in filas:
        if not isinstance(fila, dict) or fila.get("id") != comment_id:
            continue
        fila["resolved"] = True
        fila["resolved_at"] = _iso_now()
        fila["resolved_by"] = current_user.full_name
        _set_json(
            db, COMMENTS_KEY, organization_id, filas,
            description="BI Collaboration comments (legacy JSON fallback)",
        )
        return {
            "id": fila.get("id"),
            "dashboard_key": fila.get("dashboard_key"),
            "widget_id": fila.get("widget_id"),
            "message": fila.get("message") or "",
            "author_id": fila.get("author_id"),
            "author_name": fila.get("author_name"),
            "resolved": True,
            "resolved_at": fila.get("resolved_at"),
            "resolved_by": fila.get("resolved_by"),
            "created_at": fila.get("created_at"),
        }
    raise ValueError("comment_not_found")


def _comentario_como_dict(row) -> dict[str, Any]:
    """La forma que devuelve la API para un comentario de la tabla."""
    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "widget_id": row.widget_id,
        "message": row.message,
        "author_id": row.author_id,
        "author_name": row.author_name,
        "resolved": bool(row.resolved),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_by": row.resolved_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def resolve_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    comment_id: str,
    current_user: User,
) -> dict[str, Any]:
    """Marca un comentario de panel como resuelto.

    Con el respaldo a JSON en instalaciones donde la tabla todavía no existe:
    se comprueba antes, y también se captura después, porque entre la
    comprobación y la consulta puede haber una migración a medias.
    """
    if not _table_exists(db, "dashboard_comments"):
        return _resolver_en_json_heredado(
            db, organization_id=organization_id, comment_id=comment_id, current_user=current_user,
        )

    try:
        q = db.query(DashboardComment).filter(DashboardComment.id == comment_id)
        # `organization_id` nulo es el ámbito global, y hay que preguntarlo con
        # `IS NULL`: en SQL `columna = NULL` no encaja con nada.
        if organization_id:
            q = q.filter(DashboardComment.organization_id == organization_id)
        else:
            q = q.filter(DashboardComment.organization_id.is_(None))

        row = q.first()
        if row is None:
            raise ValueError("comment_not_found")

        row.resolved = True
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = current_user.full_name
        _emit_dashboard_notification(
            db,
            organization_id=organization_id,
            dashboard_key=row.dashboard_key,
            event_type="comment_resolved",
            payload={"comment_id": row.id, "resolved_by": current_user.id},
        )
        db.commit()
        return _comentario_como_dict(row)
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        db.rollback()
        return _resolver_en_json_heredado(
            db, organization_id=organization_id, comment_id=comment_id, current_user=current_user,
        )
