"""Fuera de la oficina: a quién pasan mis aprobaciones mientras no estoy (revisión 2026-11)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User


def fijar_ausencia(db: Session, usuario: User, delegado_id: Optional[str],
                   desde: Optional[str], hasta: Optional[str]) -> dict:
    """Sin delegado se quita la ausencia. El delegado es de la misma empresa y activo."""
    if not delegado_id:
        usuario.away_delegate_id = usuario.away_from = usuario.away_until = None
        db.commit()
        return {"delegate_id": None, "away_from": None, "away_until": None}
    try:
        inicio, fin = date.fromisoformat(desde or ""), date.fromisoformat(hasta or "")
    except ValueError:
        raise HTTPException(422, "Indica las fechas de inicio y fin (AAAA-MM-DD)")
    if fin < inicio:
        raise HTTPException(422, "La fecha de fin es anterior a la de inicio")
    if delegado_id == usuario.id:
        raise HTTPException(422, "No puedes delegar en ti mismo")
    delegado = db.query(User).filter(User.id == delegado_id, User.is_active == True).first()  # noqa: E712
    if delegado is None:
        raise HTTPException(422, "Ese usuario no existe en tu empresa o no está activo")
    usuario.away_delegate_id, usuario.away_from, usuario.away_until = delegado.id, inicio, fin
    db.commit()
    return {"delegate_id": delegado.id, "away_from": inicio.isoformat(), "away_until": fin.isoformat()}
