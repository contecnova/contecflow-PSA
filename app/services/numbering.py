from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import is_postgres
from app.models.advanced_config import NumberingSequence
import logging

logger = logging.getLogger(__name__)



#: Prefijos de serie por defecto (solo al crear la secuencia de una empresa; la
#: configurada manda). Ronda 2 auditoria 2026-11-22, §6: antes "PRJ"/"INV" en
#: cada llamante.
PREFIJO_PROYECTO = "PRJ"
PREFIJO_FACTURA = "INV"

def _current_year(db: Optional[Session] = None, org_id: Optional[str] = None) -> int:
    """El año en la zona horaria de la empresa (`DEFAULT_TIMEZONE`).

    Auditoria 2026-11-22 (03, bajos m-p): antes en UTC; en Madrid una factura
    del 1 de enero a las 00:30 salia con el año anterior (y el reinicio anual
    llegaba una hora tarde). Sin sesion, o si no se puede leer, UTC."""
    if db is not None:
        try:
            from app.core.timeutil import resolve_zone
            from app.services.settings_service.por_empresa import zona_de_empresa
            return datetime.now(resolve_zone(zona_de_empresa(db, org_id))).year
        except Exception:
            logger.debug("numbering: zona de la empresa no disponible, año en UTC", exc_info=True)
    return datetime.now(timezone.utc).year


def _render_sequence(sequence: NumberingSequence, number: int, year: int, year_separator: str = "") -> str:
    year_part = str(year) if sequence.include_year else ""
    padded = str(number).zfill(sequence.padding or 4)
    middle = f"{year_part}{year_separator}{padded}" if year_part else padded
    if sequence.prefix:
        return f"{sequence.prefix}{sequence.separator}{middle}{sequence.suffix}"
    return f"{middle}{sequence.suffix}"


def _org(db: Session) -> Optional[str]:
    """La empresa de la secuencia: la misma que el sello pondrá en la fila nueva.

    Revisión 2026-11. Un superadmin no tiene empresa en la sesión, pero al
    insertar la secuencia el sello le pone la suya propia: se buscaba la de
    «sin empresa», nunca aparecía, y crear una factura daba 500.
    """
    from app.db.session import _org_del_superadmin
    info = db.info
    if info.get("organization_id") is not None or info.get("fila_global"):
        return info.get("organization_id")
    return _org_del_superadmin(info)


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
    org_id = _org(db)
    current_year = _current_year(db, org_id)
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


# ── Numeración segura con semilla (auditoría 22-11-2026, «numeraciones con carrera») ──
#
# ≥7 sitios numeraban con `max(code)+1` (texto: FR-999 > FR-1000) o `count()+1`:
# dos altas a la vez sacaban el mismo número. `siguiente_codigo` usa la misma
# fila bloqueada de `numbering_sequences` que `next_numbered_code`, y al crear
# la secuencia arranca en el MAYOR número ya usado (`maximo_existente`), para no
# repetir códigos de antes de existir la secuencia.

def maximo_numerico(codigos) -> int:
    """El mayor número final de una lista de códigos («FR-0999», «FR-1000» → 1000)."""
    import re
    mayor = 0
    for c in codigos:
        m = re.search(r"(\d+)$", str(c or ""))
        if m:
            mayor = max(mayor, int(m.group(1)))
    return mayor


def siguiente_codigo(db: Session, entidad: str, *, prefijo: str, relleno: int,
                     maximo_existente, org_id: Optional[str] = None) -> str:
    """`{prefijo}{n:0relleno}` con `n` de una secuencia bloqueada hasta el commit.

    `maximo_existente()` solo se llama al crear la secuencia (la primera vez).
    `org_id`: la empresa de la secuencia (por defecto, la de la sesión).
    """
    org = org_id if org_id is not None else _org(db)
    secuencia = _lock_sequence(db, entidad, org)
    if secuencia is None:
        try:
            with db.begin_nested():
                db.add(NumberingSequence(organization_id=org, entity=entidad, prefix=prefijo, suffix="",
                                         separator="", include_year=False, padding=relleno,
                                         current_value=int(maximo_existente() or 0), reset_yearly=False))
                db.flush()
        except IntegrityError:
            pass  # otra transacción la ha creado a la vez: se usa la suya
        secuencia = _lock_sequence(db, entidad, org)
    if secuencia is None:
        raise RuntimeError(f"No se pudo inicializar la secuencia '{entidad}'")
    secuencia.current_value = int(secuencia.current_value or 0) + 1
    codigo = f"{prefijo}{str(secuencia.current_value).zfill(relleno)}"
    secuencia.example = codigo
    db.flush()
    return codigo
