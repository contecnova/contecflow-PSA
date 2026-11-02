from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import is_postgres
from app.models.advanced_config import NumberingSequence
import logging

logger = logging.getLogger(__name__)


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _render_sequence(sequence: NumberingSequence, number: int, year: int, year_separator: str = "") -> str:
    year_part = str(year) if sequence.include_year else ""
    padded = str(number).zfill(sequence.padding or 4)
    middle = f"{year_part}{year_separator}{padded}" if year_part else padded
    if sequence.prefix:
        return f"{sequence.prefix}{sequence.separator}{middle}{sequence.suffix}"
    return f"{middle}{sequence.suffix}"


def _org(db: Session) -> Optional[str]:
    return db.info.get("organization_id")


def _lock_sequence(db: Session, entity: str, org_id: Optional[str] = None):
    """La secuencia de la organizacion, bloqueada hasta el final de la transaccion.

    El filtro va explicito y sin el de tenant: en una sesion de worker no hay
    filtro, y con el de tenant una fila global (sin organizacion) no se ve.
    """
    from app.db.session import sin_filtro_de_tenant

    with sin_filtro_de_tenant(db):
        q = db.query(NumberingSequence).filter(
            NumberingSequence.entity == entity,
            NumberingSequence.organization_id.is_(None) if org_id is None
            else NumberingSequence.organization_id == org_id,
        )
        if is_postgres():
            q = q.with_for_update()
        return q.first()


def _heredada(db: Session, entity: str, org_id: Optional[str]):
    """La secuencia antigua sin organizacion, de la que parte la nueva.

    Antes de 2026-11 habia una sola secuencia por entidad para toda la base.
    Una organizacion que numeraba con ella sigue desde su valor: arrancar de
    cero repetiria numeros que ya existen.
    """
    if org_id is None:
        return None
    return _lock_sequence(db, entity, None)


def next_numbered_code(
    db: Session,
    entity: str,
    *,
    prefix: str,
    padding: int,
    suffix: str = "",
    separator: str = "-",
    include_year: bool = False,
    reset_yearly: bool = False,
    year_separator: str = "",
) -> str:
    current_year = _current_year()
    org_id = _org(db)
    sequence = _lock_sequence(db, entity, org_id)

    if not sequence:
        base = _heredada(db, entity, org_id)
        try:
            with db.begin_nested():
                db.add(NumberingSequence(
                    organization_id=org_id,
                    entity=entity,
                    prefix=base.prefix if base else prefix,
                    suffix=base.suffix if base else suffix,
                    separator=base.separator if base else separator,
                    include_year=base.include_year if base else include_year,
                    padding=base.padding if base else padding,
                    current_value=int(base.current_value or 0) if base else 0,
                    reset_yearly=base.reset_yearly if base else reset_yearly,
                    last_reset_year=(base.last_reset_year if base else
                                     (current_year if reset_yearly else None)),
                ))
                db.flush()
        # Otra transaccion la ha creado a la vez: se usa la suya.
        except IntegrityError:
            pass
        sequence = _lock_sequence(db, entity, org_id)

    if not sequence:
        raise RuntimeError(f"No se pudo inicializar la secuencia '{entity}'")

    if sequence.reset_yearly and sequence.last_reset_year != current_year:
        sequence.current_value = 0
        sequence.last_reset_year = current_year

    sequence.current_value = int(sequence.current_value or 0) + 1
    code = _render_sequence(sequence, sequence.current_value, current_year, year_separator=year_separator)
    sequence.example = code
    db.flush()
    return code
