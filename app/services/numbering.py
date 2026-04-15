from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import is_postgres
from app.models.advanced_config import NumberingSequence


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _render_sequence(sequence: NumberingSequence, number: int, year: int, year_separator: str = "") -> str:
    year_part = str(year) if sequence.include_year else ""
    padded = str(number).zfill(sequence.padding or 4)
    middle = f"{year_part}{year_separator}{padded}" if year_part else padded
    if sequence.prefix:
        return f"{sequence.prefix}{sequence.separator}{middle}{sequence.suffix}"
    return f"{middle}{sequence.suffix}"


def _lock_sequence(db: Session, entity: str):
    q = db.query(NumberingSequence).filter(NumberingSequence.entity == entity)
    if is_postgres():
        q = q.with_for_update()
    return q.first()


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
    sequence = _lock_sequence(db, entity)

    if not sequence:
        try:
            with db.begin_nested():
                db.add(NumberingSequence(
                    entity=entity,
                    prefix=prefix,
                    suffix=suffix,
                    separator=separator,
                    include_year=include_year,
                    padding=padding,
                    current_value=0,
                    reset_yearly=reset_yearly,
                    last_reset_year=current_year if reset_yearly else None,
                ))
                db.flush()
        except IntegrityError:
            pass
        sequence = _lock_sequence(db, entity)

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
