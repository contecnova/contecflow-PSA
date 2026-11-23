"""Confirmación de la transacción: la API no hace commit, lo hace el servicio."""
from sqlalchemy.orm import Session


def confirmar(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
