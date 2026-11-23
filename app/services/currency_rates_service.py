from contextvars import ContextVar
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import is_postgres
from app.models.billing_reports import Invoice, InvoiceStatus
from app.models.bookings import ExchangeRate
from app.models.exchange_rates_log import CurrencyConversionLog
from app.models.expenses import Expense
import logging

logger = logging.getLogger(__name__)


def list_exchange_rates(
    db: Session,
    base_currency: Optional[str] = None,
    target_currency: Optional[str] = None,
) -> list:
    q = db.query(ExchangeRate)
    if base_currency:
        q = q.filter(ExchangeRate.from_currency == base_currency.upper())
    if target_currency:
        q = q.filter(ExchangeRate.to_currency == target_currency.upper())
    from app.services.exchange_rate_service import PROPIOS_PRIMERO
    return q.order_by(ExchangeRate.effective_date.desc(), PROPIOS_PRIMERO).limit(200).all()


def upsert_exchange_rate(
    db: Session,
    from_currency: str,
    to_currency: str,
    rate: float,
    effective_date: date,
    source: str = "manual",
) -> tuple:
    """Returns (rate_obj, created: bool, previous_snapshot: dict|None).

    Revisión 2026-11: el tipo manual es de la empresa de la sesión (sin empresa:
    global). Antes actualizaba el primero que encontrara, también el global.
    """
    from app.services.exchange_rate_service import org_de_la_sesion, solo_de
    org = org_de_la_sesion(db)
    existing_q = solo_de(db.query(ExchangeRate), org).filter(
        ExchangeRate.from_currency == from_currency,
        ExchangeRate.to_currency == to_currency,
        ExchangeRate.effective_date == effective_date,
    )
    if is_postgres():
        existing_q = existing_q.with_for_update()
    existing = existing_q.first()
    if existing:
        previous = {
            "id": existing.id,
            "rate": existing.rate,
            "source": existing.source,
            "effective_date": str(existing.effective_date),
        }
        existing.rate = rate
        existing.source = source
        db.commit()
        db.refresh(existing)
        return existing, False, previous
    rate_obj = ExchangeRate(
        organization_id=org,
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        effective_date=effective_date,
        source=source,
    )
    db.add(rate_obj)
    db.commit()
    db.refresh(rate_obj)
    return rate_obj, True, None


def registrar_tipo_de_cambio(
    db: Session,
    current_user,
    *,
    from_currency: str,
    to_currency: str,
    rate: float,
    effective_date: date,
    source: str = "manual",
) -> tuple:
    """Alta o actualizacion manual del tipo, con su auditoria, y confirma.

    Devuelve (rate_obj, created).
    """
    from app.services.audit import audit_log

    rate_obj, created, previous_snapshot = upsert_exchange_rate(
        db,
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        effective_date=effective_date,
        source=source,
    )
    audit_log(
        db,
        current_user,
        "CREATE" if created else "UPDATE",
        "exchange_rates",
        rate_obj.id,
        f"{rate_obj.from_currency}->{rate_obj.to_currency}@{rate_obj.effective_date}",
        old_values=previous_snapshot,
        new_values={
            "id": rate_obj.id,
            "rate": rate_obj.rate,
            "source": rate_obj.source,
            "effective_date": str(rate_obj.effective_date),
        },
    )
    db.commit()
    return rate_obj, created


def get_rate(
    db: Session,
    from_c: str,
    to_c: str,
    ref_date: date,
) -> Optional[ExchangeRate]:
    """Return the latest ExchangeRate for from_c -> to_c on or before ref_date."""
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_c,
            ExchangeRate.to_currency == to_c,
            ExchangeRate.effective_date <= ref_date,
        )
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.organization_id.is_(None))
        .first()
    )


def get_rate_inverse(
    db: Session,
    from_c: str,
    to_c: str,
    ref_date: date,
) -> Optional[ExchangeRate]:
    """Return ExchangeRate for to_c -> from_c (inverse direction)."""
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == to_c,
            ExchangeRate.to_currency == from_c,
            ExchangeRate.effective_date <= ref_date,
        )
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.organization_id.is_(None))
        .first()
    )


# ── Resolutor ÚNICO de tipos de cambio (auditoría 22-11-2026, A41) ─────────
#
# Había cuatro (`get_rate`/`resolve_rate` aquí, `exchange_rate_service.get_rate`
# y `profitability_service.get_fx_rate`) y tres devolvían 1,0 en silencio si no
# había tipo: USD→GBP o una moneda sin tipo cargado se convertía 1:1 y entraba
# en coste, margen y EVM sin que nadie lo viera. Ahora todos pasan por
# `tipo_de_cambio`:
#
#   directo → inverso → cruzado por la moneda pivote (EUR, la base del BCE)
#
# y, si no hay, devuelve None. Quien llama decide: un cálculo puntual
# (convertir, política) da error explícito (`resolve_rate`); un agregado
# (rentabilidad, costes, informes) usa `tipo_o_aviso`, que anota el par que
# falta en `TiposQueFaltan` para que la respuesta lo diga.

MONEDA_PIVOTE = "EUR"

_FALTAN: ContextVar[Optional[set]] = ContextVar("tipos_de_cambio_que_faltan", default=None)


_TABLA: ContextVar[Optional["TablaDeTipos"]] = ContextVar("tabla_de_tipos_precargada", default=None)


class TablaDeTipos:
    """Tipos precargados para un cálculo EN BLOQUE (auditoría 22-11-2026, §7.2).

    ``with TablaDeTipos(db): ...``: mientras dura el bloque, `tipo_de_cambio`
    (el resolutor único) resuelve en memoria con las MISMAS reglas que
    `get_rate`/`get_rate_inverse` —último tipo con fecha ≤ la pedida; a igual
    fecha, el de la empresa antes que el global— y la misma cadena directo →
    inverso → cruzado por EUR. Una consulta por moneda nueva que aparece (no por
    fecha ni por proyecto): el margen de 500 proyectos con imputaciones de 300
    días en tres monedas son tres consultas de tipos, no 900.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._monedas: set = set()
        self._pares: dict = {}       # (de, a) -> ([fechas asc], [tipos])
        self._marca = None

    def __enter__(self) -> "TablaDeTipos":
        if _TABLA.get() is None:
            self._marca = _TABLA.set(self)
        return self

    def __exit__(self, *exc) -> None:
        if self._marca is not None:
            _TABLA.reset(self._marca)
            self._marca = None

    def _cargar(self, *monedas: str) -> None:
        nuevas = {m for m in monedas if m} - self._monedas
        if not nuevas:
            return
        todas = self._monedas | nuevas | {MONEDA_PIVOTE}
        self._monedas = set(todas)
        filas = self.db.query(ExchangeRate.from_currency, ExchangeRate.to_currency, ExchangeRate.effective_date,
                              ExchangeRate.rate, ExchangeRate.organization_id).filter(
            ExchangeRate.from_currency.in_(todas), ExchangeRate.to_currency.in_(todas)).all()
        por_par: dict = {}
        for de, a, fecha, tipo, org in filas:
            if not tipo:
                continue
            dias = por_par.setdefault((de, a), {})
            # A igual fecha, el propio (org no nula) antes que el global: como get_rate.
            if fecha not in dias or (org is not None and dias[fecha][1] is None):
                dias[fecha] = (float(tipo), org)
        for par, dias in por_par.items():
            fechas = sorted(dias)
            self._pares[par] = (fechas, [dias[f][0] for f in fechas])

    def _ultimo(self, de: str, a: str, fecha: date) -> Optional[float]:
        from bisect import bisect_right
        fechas, tipos = self._pares.get((de, a), ((), ()))
        i = bisect_right(fechas, fecha) - 1 if fechas else -1
        return tipos[i] if i >= 0 else None

    def directo_o_inverso(self, de: str, a: str, fecha: date) -> Optional[float]:
        self._cargar(de, a)
        directo = self._ultimo(de, a, fecha)
        if directo is not None:
            return directo
        inverso = self._ultimo(a, de, fecha)
        return 1.0 / inverso if inverso else None


def _directo_o_inverso(db: Session, de: str, a: str, fecha: date) -> Optional[float]:
    tabla = _TABLA.get()
    if tabla is not None and tabla.db is db:
        return tabla.directo_o_inverso(de, a, fecha)
    r = get_rate(db, de, a, fecha)
    if r and r.rate:
        return float(r.rate)
    r2 = get_rate_inverse(db, de, a, fecha)
    if r2 and r2.rate:
        return 1.0 / float(r2.rate)
    return None


def tipo_de_cambio(db: Session, de: str, a: str, fecha: date) -> Optional[float]:
    """Tipo de `de`→`a` a `fecha` (directo, inverso o cruzado por EUR); None si no hay."""
    de, a = (de or "").upper(), (a or "").upper()
    if not de or not a or de == a:
        return 1.0
    directo = _directo_o_inverso(db, de, a, fecha)
    if directo is not None:
        return directo
    tabla = _TABLA.get()
    if tabla is not None and tabla.db is db:
        tabla._cargar(de, a)   # una sola consulta trae también los pares con EUR
    if MONEDA_PIVOTE not in (de, a):
        de_pivote = _directo_o_inverso(db, de, MONEDA_PIVOTE, fecha)
        pivote_a = _directo_o_inverso(db, MONEDA_PIVOTE, a, fecha) if de_pivote is not None else None
        if de_pivote is not None and pivote_a is not None:
            return de_pivote * pivote_a
    return None


class TiposQueFaltan:
    """`with TiposQueFaltan() as faltan: ...` → `faltan` = {"USD→GBP@2026-01-31", …}
    con los pares que `tipo_o_aviso` no encontró dentro del bloque."""

    def __enter__(self) -> set:
        self._set: set = set()
        self._marca = _FALTAN.set(self._set)
        return self._set

    def __exit__(self, *exc) -> None:
        _FALTAN.reset(self._marca)


def tipo_o_aviso(db: Session, de: str, a: str, fecha: date) -> float:
    """Para AGREGADOS: el tipo, o 1,0 con aviso EXPLÍCITO (log + `TiposQueFaltan`).

    El importe no se descarta (el total no se hunde), pero el hueco queda
    anotado y la respuesta lo enseña (`avisos_de_divisa` / `missing_rates`).
    """
    t = tipo_de_cambio(db, de, a, fecha)
    if t is not None:
        return t
    par = f"{(de or '').upper()}→{(a or '').upper()}@{fecha.isoformat() if fecha else ''}"
    logger.warning("sin tipo de cambio %s: se cuenta 1:1 y se avisa", par)
    faltan = _FALTAN.get()
    if faltan is not None:
        faltan.add(par)
    return 1.0


def resolve_rate(db: Session, from_c: str, to_c: str, ref_date: date) -> float:
    """Tipo de `from_c`→`to_c`; sin tipo, error 409 (antes 1,0 en silencio)."""
    t = tipo_de_cambio(db, from_c, to_c, ref_date)
    if t is None:
        from app.core.codigos_de_error import error
        raise error(409, "tipo_de_cambio_no_configurado", desde=from_c, hasta=to_c)
    return t


def resolve_rate_with_snapshot(db: Session, from_c: str, to_c: str, ref_date: date) -> dict:
    """Resolve FX rate plus immutable snapshot metadata used for auditing.

    Sin tipo: `rate` None y `source` "fallback" (antes 1,0): quien llama decide.
    """
    if from_c == to_c:
        return {"rate": 1.0, "rate_id": None, "rate_date": str(ref_date), "source": "identity"}

    direct = get_rate(db, from_c, to_c, ref_date)
    if direct:
        return {"rate": direct.rate, "rate_id": direct.id, "rate_date": str(direct.effective_date),
                "source": direct.source}

    inverse = get_rate_inverse(db, from_c, to_c, ref_date)
    if inverse and inverse.rate:
        return {"rate": 1.0 / inverse.rate, "rate_id": inverse.id, "rate_date": str(inverse.effective_date),
                "source": f"inverse:{inverse.source}"}

    cruzado = tipo_de_cambio(db, from_c, to_c, ref_date)
    if cruzado is not None:
        return {"rate": cruzado, "rate_id": None, "rate_date": str(ref_date), "source": f"cross:{MONEDA_PIVOTE}"}

    return {"rate": None, "rate_id": None, "rate_date": str(ref_date), "source": "fallback"}


def log_currency_conversion(
    db: Session,
    *,
    organization_id: Optional[str],
    entity_type: str,
    entity_id: str,
    from_currency: str,
    to_currency: str,
    original_amount: float,
    converted_amount: float,
    rate_used: float,
    rate_date: date,
) -> None:
    db.add(
        CurrencyConversionLog(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            from_currency=from_currency,
            to_currency=to_currency,
            original_amount=original_amount,
            converted_amount=converted_amount,
            rate_used=rate_used,
            rate_date=rate_date,
        )
    )


def registrar_conversion(db: Session, **datos) -> None:
    """`log_currency_conversion` y confirma: la traza de una conversion pedida por la API."""
    log_currency_conversion(db, **datos)
    db.commit()


def get_report_data(
    db: Session,
    target: str,
    ref_date: date,
) -> tuple:
    """(facturas, gastos) del informe multimoneda A `ref_date`.

    Auditoría 22-11-2026 (baja): antes ignoraba los parámetros. Ahora solo lo
    emitido o gastado hasta `ref_date` (el tipo se toma a esa fecha) y sin
    gastos borrados; `target` solo decide la conversión (la hace quien llama).
    """
    invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.cancelled,
                                        Invoice.issue_date <= ref_date).all()
    expenses = db.query(Expense).filter(Expense.is_active.isnot(False), Expense.expense_date <= ref_date).all()
    return invoices, expenses
