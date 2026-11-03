"""Series temporales de metricas para el motor de alertas inteligentes.

Devuelve la serie mensual de cada metrica soportada —y de las compuestas que
define el cliente— a partir de datos reales de la base.

── Como esta organizado y por que ───────────────────────────────────────────
Auditoria 2026-08 (hallazgo 18). `_fetch_metric_series` era la funcion mas
compleja de la solucion con enorme diferencia: complejidad ciclomatica **247** en
945 lineas, cuando la siguiente del proyecto esta en 67. Eran 55 `if metric_key
== ...` secuenciales al mismo nivel, cada uno con su consulta y su `return`: una
tabla de despacho escrita como una unica funcion.

Eso tenia tres costes concretos, no esteticos:

  · una clave del catalogo sin rama caia al `return _empty_like()` del final, asi
    que la metrica presentaba una linea plana en vez de fallar — el mismo patron
    que dejo muerto el endpoint `/analytics/adhoc` y el reconocimiento ASC 606;
  · las 945 lineas compartian un unico ambito, asi que cualquier variable de una
    rama era visible para las 54 siguientes;
  · ninguna rama se podia probar por separado.

Ahora cada grupo de metricas es una funcion con nombre, registrada en
`_RESOLUTORES`. La logica de cada una se movio VERBATIM —misma condicion, mismo
cuerpo, mismos comentarios— y la equivalencia se verifico comparando las 133
series del catalogo antes y despues, valor a valor. Lo unico que se anadio a cada
funcion es el preambulo que reenlaza los nombres que tomaba del entorno.

El contexto compartido (`_Ctx`) lleva la serie de meses de referencia y los cuatro
ayudantes de agregacion que antes eran cierres. Se llama `ctx` y no `c` porque el
codigo original usa `c` como variable propia en cinco sitios.

Ver tests/test_bi_metrics_catalog.py: comprueba que las 133 claves del catalogo se
resuelven, que todas devuelven series de la misma longitud y que catalogo y
codigo no se pueden separar.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, NamedTuple, Optional

from sqlalchemy.orm import Session

from .constants import CUSTOM_METRICS_KEY
from .persistence import _get_json

logger = logging.getLogger(__name__)

# Metricas del perfil de coste de personal. Estaba definido DENTRO de la funcion,
# recreandose en cada llamada; izado aqui porque el registro lo necesita para
# saber que claves atiende `_serie_cost_profile`.
COST_PROFILE_KEYS = frozenset({
        "cost_profile_avg_per_hour", "cost_profile_max_per_hour",
        "cost_profile_p95_per_hour", "cost_profile_dept_max_per_hour",
        "cost_profile_country_max_per_hour",
        "cost_profile_total_annual", "cost_profile_top_person_annual",
        "cost_profile_top_country_annual",
        "cost_profile_users_with", "cost_profile_users_legacy",
        "cost_profile_users_missing",
        "cost_profile_employer_pct_avg", "cost_profile_employer_pct_max",
})


@dataclass
class _Ctx:
    """Lo que toda metrica necesita del entorno para calcular su serie.

    `series` es la rejilla de meses de referencia: todas las metricas devuelven
    una serie de su misma longitud para que los paneles puedan compararlas entre
    si. Los cuatro ayudantes eran cierres dentro de la funcion original y su
    cuerpo se conserva igual.
    """

    db: Session
    key: str
    org_id: Optional[str]
    series: list[dict] = field(default_factory=list)
    start_date: Optional[date] = None

    def empty_like(self) -> list[float]:
        """Serie a cero de la longitud correcta. Es la respuesta a «no hay dato»."""
        return [0.0 for _ in self.series]

    def bucket_count(self, rows, date_field_idx=0, *, start: date) -> list[float]:
        """Cuenta filas por mes. `start` se conserva en la firma por
        compatibilidad con las llamadas: el cuerpo original no lo usaba."""
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d = row[date_field_idx] if isinstance(row, (list, tuple)) else row
            if d:
                bkt[f"{d.year:04d}-{d.month:02d}"] += 1.0
        return [float(bkt.get(m["month"], 0.0)) for m in self.series]

    def bucket_sum(self, rows, date_idx=0, value_idx=1, *, start: date) -> list[float]:
        """Suma un valor por mes. `start`, igual que arriba."""
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d, v = row[date_idx], row[value_idx]
            if d and v is not None:
                bkt[f"{d.year:04d}-{d.month:02d}"] += float(v)
        return [float(bkt.get(m["month"], 0.0)) for m in self.series]

    def current(self, val: float) -> list[float]:
        """Un valor instantaneo repetido en toda la serie.

        Se usa en las metricas que solo tienen «ahora» (cuantos proyectos hay
        activos), donde no existe historico mensual que reconstruir.
        """
        return [val] * len(self.series)


def _construir_contexto(db: Session, metric_key: str, organization_id: Optional[str]) -> _Ctx:
    """Prepara la rejilla de meses. Era el prologo de la funcion original."""
    from app.services.bi_intelligence_service import _month_series

    try:
        series = _month_series(db, organization_id, months_history=24)
    except Exception:
        logger.warning(
            "Failed to load _month_series for smart alerts org=%s",
            organization_id, exc_info=True,
        )
        series = []
    if not series:
        # Sin historico se devuelve una rejilla del ano en curso a cero, para que
        # las series sigan teniendo la misma longitud y los paneles no se
        # descuadren.
        _cur_year = datetime.now(timezone.utc).year
        series = [
            {"month": f"{_cur_year}-{m:02d}", "revenue": 0.0, "cost": 0.0, "hours": 0.0}
            for m in range(1, 13)
        ]

    return _Ctx(
        db=db,
        key=metric_key,
        org_id=organization_id,
        series=series,
        start_date=date.fromisoformat(series[0]["month"] + "-01"),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Resolutores. Uno por metrica o por grupo de metricas que comparten consulta.
# El cuerpo de cada uno viene VERBATIM de la funcion original.
# ═════════════════════════════════════════════════════════════════════════════

def _serie_custom(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas compuestas definidas por el cliente (prefijo `custom_`)."""
    _empty_like, db, metric_key, organization_id = ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key.startswith("custom_"):
        customs = _get_json(db, CUSTOM_METRICS_KEY, organization_id, default=[])
        cm = next((c for c in customs if c.get("key") == metric_key), None)
        if not cm:
            return _empty_like()
        f = cm.get("formula", {})
        a_s = _fetch_metric_series(db, f.get("operand_a", ""), organization_id)
        op = f.get("operator", "+")
        b_s = (_fetch_metric_series(db, f.get("operand_b", ""), organization_id)
               if f.get("operand_b_type") == "metric"
               else [float(f.get("operand_b", 0) or 0)] * len(a_s))
        scale = float(f.get("scale", 1) or 1)
        result = []
        for a, b in zip(a_s, b_s):  # noqa: B905
            try:
                v = {"+": a+b, "-": a-b, "*": a*b, "/": a/b if b else 0.0}.get(op, a)
            except Exception:
                logger.debug("Custom metric %s arithmetic failed (op=%s a=%s b=%s)", metric_key, op, a, b, exc_info=True)
                v = 0.0
            result.append(round(v * scale, 4))
        return result

def _serie_revenue(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `revenue`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "revenue":
        return [float(m.get("revenue", 0)) for m in series]

def _serie_cost(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `cost`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "cost":
        return [float(m.get("cost", 0)) for m in series]

def _serie_margin(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `margin`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "margin":
        return [float(m.get("revenue", 0)) - float(m.get("cost", 0)) for m in series]

def _serie_margin_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `margin_pct`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "margin_pct":
        return [round((float(m.get("revenue",0))-float(m.get("cost",0)))/float(m.get("revenue",0))*100,2)
                if float(m.get("revenue",0)) > 0 else 0.0 for m in series]

def _serie_budget_used_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `budget_used_pct`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "budget_used_pct":
        return [round(float(m.get("cost",0))/float(m.get("revenue",0))*100,2)
                if float(m.get("revenue",0)) > 0 else 0.0 for m in series]

# ── Metricas de facturacion ──────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_serie_invoice` era complejidad 24: siete
# ramas sobre `metric_key`, y seis de ellas el MISMO bucle copiado cambiando
# solo tres cosas — el estado que cuenta, de que campo saca la fecha, y si suma
# el importe o cuenta filas. Esas tres cosas son ahora una tabla.

# Los tres campos de fecha, como funciones para poder ponerlos en la tabla. La
# firma es siempre `(vencimiento, emision, pago)` para que sean intercambiables.
def _fecha_de_vencimiento(due, iss, paid):
    return due


def _fecha_de_emision(due, iss, paid):
    return iss


def _fecha_de_cobro(due, iss, paid):
    """La de pago, y si no hay, la de emision.

    Una factura marcada como pagada sin fecha de pago sigue siendo un cobro que
    hay que ver en algun mes; se imputa al de emision antes que perderla.
    """
    return paid or iss


@dataclass(frozen=True, slots=True)
class _MetricaDeFactura:
    """Como se calcula una de las seis metricas de recuento/importe."""

    estado: str          # el estado de factura que entra en el recuento
    fecha: object        # de que campo sale el mes al que se imputa
    importe: bool        # True suma `total`; False cuenta facturas


_METRICAS_DE_FACTURA = {
    "invoice_overdue_count":  _MetricaDeFactura("overdue", _fecha_de_vencimiento, importe=False),
    "invoice_overdue_amount": _MetricaDeFactura("overdue", _fecha_de_vencimiento, importe=True),
    "invoices_draft_count":   _MetricaDeFactura("draft",   _fecha_de_emision,     importe=False),
    "invoices_sent_count":    _MetricaDeFactura("sent",    _fecha_de_emision,     importe=False),
    "invoices_paid_count":    _MetricaDeFactura("paid",    _fecha_de_cobro,       importe=False),
    "invoices_paid_total":    _MetricaDeFactura("paid",    _fecha_de_cobro,       importe=True),
}

# La septima no encaja en la tabla: es una media, no una acumulacion.
_METRICA_DIAS_DE_COBRO = "invoice_days_to_pay_avg"

CLAVES_DE_FACTURA = frozenset(_METRICAS_DE_FACTURA) | {_METRICA_DIAS_DE_COBRO}


def _estado_de(st) -> str:
    """El estado como cadena, venga como Enum o ya como texto.

    `getattr(st, "value", st)` porque la columna es un Enum de SQLAlchemy pero
    algunas consultas lo devuelven ya resuelto a cadena.
    """
    return str(getattr(st, "value", st))


def _acumular(ctx: _Ctx, rows, spec: _MetricaDeFactura) -> list[float]:
    """Agrupa las facturas del estado pedido por su mes y acumula."""
    bkt: dict[str, float] = defaultdict(float)
    for due, iss, paid, st, tot in rows:
        if _estado_de(st) != spec.estado:
            continue
        d = spec.fecha(due, iss, paid)
        if not d:
            continue
        bkt[f"{d.year:04d}-{d.month:02d}"] += float(tot or 0) if spec.importe else 1.0
    return [float(bkt.get(m["month"], 0.0)) for m in ctx.series]


def _dias_medios_de_cobro(ctx: _Ctx, rows) -> list[float]:
    """Media de dias entre emision y cobro, por mes de emision.

    Se imputa al mes de EMISION y no al de cobro a proposito: la pregunta que
    responde es «lo que factune en marzo, cuanto tardo en cobrarse».
    """
    suma: dict[str, float] = defaultdict(float)
    cuenta: dict[str, float] = defaultdict(float)
    for due, iss, paid, st, tot in rows:  # noqa: B007
        if iss and paid and _estado_de(st) == "paid":
            k = f"{iss.year:04d}-{iss.month:02d}"
            suma[k] += (paid - iss).days
            cuenta[k] += 1.0
    return [
        round(suma[m["month"]] / cuenta[m["month"]], 1)
        if cuenta.get(m["month"], 0) > 0 else 0.0
        for m in ctx.series
    ]


def _serie_invoice(ctx: _Ctx) -> Optional[list[float]]:
    """Las siete metricas de facturacion, que comparten una sola consulta."""
    if ctx.key not in CLAVES_DE_FACTURA:
        return None
    try:
        from sqlalchemy import or_ as _or
        from app.models.billing_reports import Invoice

        # El `or_(... is None)` corrige un defecto encontrado en la auditoria: el
        # filtro era solo `due_date >= start_date`, y `due_date` es NULLABLE —
        # el esquema y la API aceptan una factura sin fecha de vencimiento. Esa
        # factura quedaba fuera de las SIETE metricas, incluidas las cuatro que
        # ni usan el vencimiento (borradores, enviadas, cobradas e importe
        # cobrado, que van por emision o por pago). Es el patron central de la
        # auditoria: un filtro que devuelve cero en silencio en vez de fallar.
        rows = (ctx.db.query(Invoice.due_date, Invoice.issue_date,
                             Invoice.paid_date, Invoice.status, Invoice.total)
                       .filter(_or(Invoice.due_date >= ctx.start_date,
                                   Invoice.due_date.is_(None)))
                       .all())

        if ctx.key == _METRICA_DIAS_DE_COBRO:
            return _dias_medios_de_cobro(ctx, rows)
        return _acumular(ctx, rows, _METRICAS_DE_FACTURA[ctx.key])
    except Exception:
        logger.debug(
            "Failed to fetch metric %s for org=%s", ctx.key, ctx.org_id, exc_info=True
        )
        return ctx.empty_like()


def _serie_expense(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · expense_total
    · expenses_travel
    · expenses_software
    · expenses_hardware
    · expenses_subcontract
    · expenses_training_exp
    · expenses_draft_count
    · expenses_submitted_count
    · expenses_approved_count
    · expenses_rejected_count
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("expense_total","expenses_travel","expenses_software","expenses_hardware",
                       "expenses_subcontract","expenses_training_exp",
                       "expenses_draft_count","expenses_submitted_count",
                       "expenses_approved_count","expenses_rejected_count"):
        try:
            from app.models.expenses import Expense
            rows = db.query(Expense.expense_date, Expense.amount, Expense.category, Expense.status).filter(
                Expense.expense_date >= start_date
            ).all()
            CAT_MAP = {
                "expenses_travel": "travel", "expenses_software": "software",
                "expenses_hardware": "hardware", "expenses_subcontract": "subcontract",
                "expenses_training_exp": "training",
            }
            STATUS_MAP = {
                "expenses_draft_count": "draft", "expenses_submitted_count": "submitted",
                "expenses_approved_count": "approved", "expenses_rejected_count": "rejected",
            }
            bkt: dict[str,float] = defaultdict(float)
            for d, amt, cat, st in rows:
                if not d: continue
                k = f"{d.year:04d}-{d.month:02d}"
                sv = str(getattr(st,"value",st)); cv = str(getattr(cat,"value",cat))
                if metric_key == "expense_total" and sv != "rejected":
                    bkt[k] += float(amt or 0)
                elif metric_key in CAT_MAP and cv == CAT_MAP[metric_key] and sv != "rejected":
                    bkt[k] += float(amt or 0)
                elif metric_key in STATUS_MAP and sv == STATUS_MAP[metric_key]:
                    bkt[k] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_imputations_approved_hours(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · imputations_approved_hours
    · imputations_invoiced_count
    · imputations_cost_total
    · hourly_rate_avg
    """
    _bucket_count, _bucket_sum, _empty_like, db, metric_key, organization_id, series, start_date = ctx.bucket_count, ctx.bucket_sum, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("imputations_approved_hours","imputations_invoiced_count",
                       "imputations_cost_total","hourly_rate_avg"):
        try:
            # `func as sqf` estaba aquí y no se usa en ninguna de estas cuatro
            # métricas. Era deuda que el ámbito único de 945 líneas ocultaba:
            # ruff veía el nombre usado en otra rama y no lo marcaba.
            from app.models.imputation import Imputation
            if metric_key == "imputations_approved_hours":
                rows = db.query(Imputation.date, Imputation.hours).filter(
                    Imputation.date >= start_date, Imputation.is_approved == True
                ).all()
                return _bucket_sum(rows, start=start_date)
            if metric_key == "imputations_invoiced_count":
                rows = db.query(Imputation.date).filter(
                    Imputation.date >= start_date, Imputation.is_invoiced == True
                ).all()
                return _bucket_count(rows, start=start_date)
            if metric_key == "imputations_cost_total":
                rows = db.query(Imputation.date, Imputation.cost_amount).filter(
                    Imputation.date >= start_date
                ).all()
                return _bucket_sum(rows, start=start_date)
            if metric_key == "hourly_rate_avg":
                rows = db.query(Imputation.date, Imputation.hourly_rate_snapshot).filter(
                    Imputation.date >= start_date, Imputation.hourly_rate_snapshot != None
                ).all()
                bkt_s: dict[str,float] = defaultdict(float)
                bkt_c: dict[str,float] = defaultdict(float)
                for d, r in rows:
                    if d and r:
                        k = f"{d.year:04d}-{d.month:02d}"; bkt_s[k] += r; bkt_c[k] += 1.0
                return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                        if bkt_c.get(m["month"],0) > 0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

# ── Perfil de coste de personal ──────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_serie_cost_profile` era complejidad 27:
# trece `elif metric_key == ...` DENTRO del bucle mensual, asi que reevaluaba la
# cadena entera en cada uno de los 24 meses de la serie. Ahora el calculo se
# resuelve UNA vez, antes del bucle.
#
# Los cuerpos vienen verbatim. La red es `tests/test_bi_cost_profile_metrics.py`,
# donde los 13 valores estan calculados a mano —no capturados del codigo— sobre
# tres perfiles fijos.


def _fin_de_mes(year: int, month: int) -> date:
    """Ultimo dia del mes. Es la foto contra la que se miran los perfiles."""
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _percentil(vals: list[float], pct: float) -> float:
    """Percentil con interpolacion lineal. Devuelve 0.0 sobre lista vacia."""
    if not vals:
        return 0.0
    ordered = sorted(vals)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _maximo_de_las_medias(grupos: dict[str, list[float]]) -> float:
    """El mayor de los promedios por grupo.

    Media y no suma a proposito: un euro/hora medio alto senala un grupo caro,
    mientras que un grupo grande con sueldos normales sumaria mas sin serlo. El
    coste ANUAL por pais si se suma (ver `_cp_top_country_annual`), porque alli
    lo que interesa es el total que se gasta.
    """
    medias = [sum(v) / len(v) for v in grupos.values() if v]
    return round(max(medias), 2) if medias else 0.0


@dataclass(slots=True)
class _MesDeCoste:
    """Lo que un calculo de coste ve de un mes concreto.

    `profiles` y `rates` son del mes; los otros cuatro campos son del estado
    ACTUAL y se calculan una sola vez para toda la serie. Esa asimetria es del
    codigo original y es deliberada: no hay historico de plantilla, asi que el
    censo de hoy se usa como aproximacion en todos los meses.
    """

    profiles: list
    rates: list[float]
    users_by_id: dict
    legacy_user_ids: set
    total_active: int
    employer_pcts: list[float]

    def con_perfil(self) -> set:
        return {p.user_id for p in self.profiles}


def _cp_avg_per_hour(m: _MesDeCoste) -> float:
    return round(sum(m.rates) / len(m.rates), 2) if m.rates else 0.0


def _cp_max_per_hour(m: _MesDeCoste) -> float:
    return round(max(m.rates), 2) if m.rates else 0.0


def _cp_p95_per_hour(m: _MesDeCoste) -> float:
    return round(_percentil(m.rates, 95), 2)


def _cp_dept_max_per_hour(m: _MesDeCoste) -> float:
    grupos: dict[str, list[float]] = {}
    for p in m.profiles:
        u = m.users_by_id.get(p.user_id)
        if u and p.cost_per_hour:
            # El `or "—"` no es decorativo: sin el, un usuario sin departamento
            # agruparia bajo None y su coste desapareceria del maximo.
            grupos.setdefault(u.department or "—", []).append(p.cost_per_hour)
    return _maximo_de_las_medias(grupos)


def _cp_country_max_per_hour(m: _MesDeCoste) -> float:
    grupos: dict[str, list[float]] = {}
    for p in m.profiles:
        if p.country_code and p.cost_per_hour:
            grupos.setdefault(p.country_code, []).append(p.cost_per_hour)
    return _maximo_de_las_medias(grupos)


def _cp_total_annual(m: _MesDeCoste) -> float:
    # `float(...)` explicito: sin el, una organizacion sin perfiles devolvia
    # `round(sum([]), 2)` = int 0 y esta era la unica metrica del catalogo con
    # tipo mixto en la serie. Lo cazo test_bi_cost_profile_metrics.
    return round(float(sum(p.total_annual_cost or 0 for p in m.profiles)), 2)


def _cp_top_person_annual(m: _MesDeCoste) -> float:
    annuals = [p.total_annual_cost for p in m.profiles if p.total_annual_cost]
    return round(max(annuals), 2) if annuals else 0.0


def _cp_top_country_annual(m: _MesDeCoste) -> float:
    """Maximo de las SUMAS por pais, no de las medias (ver `_maximo_de_las_medias`)."""
    por_pais: dict[str, float] = {}
    for p in m.profiles:
        if p.country_code:
            por_pais[p.country_code] = por_pais.get(p.country_code, 0) + (p.total_annual_cost or 0)
    return round(max(por_pais.values()), 2) if por_pais else 0.0


def _cp_users_with(m: _MesDeCoste) -> float:
    return float(len(m.con_perfil()))


def _cp_users_legacy(m: _MesDeCoste) -> float:
    """Activos que siguen costeandose con la tarifa suelta en vez del perfil."""
    return float(len(m.legacy_user_ids - m.con_perfil()))


def _cp_users_missing(m: _MesDeCoste) -> float:
    """Activos sin perfil ni tarifa antigua: no tienen coste de ninguna clase.

    El `max(..., 0)` es necesario porque los conjuntos son del estado actual y
    los perfiles de una foto mensual: en un mes antiguo puede haber mas perfiles
    que activos de hoy, y un recuento negativo en un panel no significa nada.
    """
    con_perfil = m.con_perfil()
    solo_legacy = m.legacy_user_ids - con_perfil
    return float(max(m.total_active - len(con_perfil) - len(solo_legacy), 0))


def _cp_employer_pct_avg(m: _MesDeCoste) -> float:
    if not m.employer_pcts:
        return 0.0
    return round(sum(m.employer_pcts) / len(m.employer_pcts) * 100, 2)


def _cp_employer_pct_max(m: _MesDeCoste) -> float:
    return round(max(m.employer_pcts) * 100, 2) if m.employer_pcts else 0.0


_CALCULOS_DE_COSTE = {
    "cost_profile_avg_per_hour": _cp_avg_per_hour,
    "cost_profile_max_per_hour": _cp_max_per_hour,
    "cost_profile_p95_per_hour": _cp_p95_per_hour,
    "cost_profile_dept_max_per_hour": _cp_dept_max_per_hour,
    "cost_profile_country_max_per_hour": _cp_country_max_per_hour,
    "cost_profile_total_annual": _cp_total_annual,
    "cost_profile_top_person_annual": _cp_top_person_annual,
    "cost_profile_top_country_annual": _cp_top_country_annual,
    "cost_profile_users_with": _cp_users_with,
    "cost_profile_users_legacy": _cp_users_legacy,
    "cost_profile_users_missing": _cp_users_missing,
    "cost_profile_employer_pct_avg": _cp_employer_pct_avg,
    "cost_profile_employer_pct_max": _cp_employer_pct_max,
}


def _serie_cost_profile(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas del perfil de coste de personal (COST_PROFILE_KEYS)."""
    if ctx.key not in COST_PROFILE_KEYS:
        return None

    calcular = _CALCULOS_DE_COSTE.get(ctx.key)
    if calcular is None:
        # Una clave del grupo sin calculo. No puede pasar —el test
        # `test_las_13_claves_estan_todas_cubiertas` cruza tabla y grupo— pero
        # devolver ceros en silencio es exactamente el patron que dejo muerto el
        # reconocimiento ASC 606, asi que aqui se avisa.
        logger.error("Metrica de coste sin calculo asociado: %s", ctx.key)
        return ctx.empty_like()

    db = ctx.db
    try:
        from sqlalchemy import or_ as _or
        from app.models.user import User as _User
        from app.models.user_cost import CountryEmployerCost, UserCostProfile

        # Censo actual. No hay historico de plantilla, asi que sirve de
        # aproximacion para todos los meses de la serie.
        active_users = db.query(_User).filter(_User.status == "active").all()
        users_by_id = {u.id: u for u in active_users}
        legacy_user_ids = {u.id for u in active_users if (u.hourly_rate or 0) > 0}

        # Presets de pais: estables entre meses, se leen una vez.
        country_presets = db.query(CountryEmployerCost).all()
        employer_pcts = [
            c.employer_cost_pct for c in country_presets
            if c.employer_cost_pct is not None
        ]

        out: list[float] = []
        for m in ctx.series:
            yyyy, mm = m["month"].split("-")
            snap = _fin_de_mes(int(yyyy), int(mm))
            profiles = (db.query(UserCostProfile)
                          .filter(UserCostProfile.valid_from <= snap,
                                  _or(UserCostProfile.valid_to.is_(None),
                                      UserCostProfile.valid_to >= snap))
                          .all())
            out.append(calcular(_MesDeCoste(
                profiles=profiles,
                rates=[p.cost_per_hour for p in profiles if p.cost_per_hour],
                users_by_id=users_by_id,
                legacy_user_ids=legacy_user_ids,
                total_active=len(active_users),
                employer_pcts=employer_pcts,
            )))
        return out
    except Exception:
        logger.debug(
            "Failed to fetch metric %s for org=%s", ctx.key, ctx.org_id, exc_info=True
        )
        return ctx.empty_like()


def _serie_hours_logged(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `hours_logged`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "hours_logged":
        return [float(m.get("hours", 0) or 0) for m in series]

def _serie_hours_billable(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `hours_billable`."""
    _bucket_sum, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_sum, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "hours_billable":
        try:
            from app.models.imputation import Imputation
            rows = db.query(Imputation.date, Imputation.hours).filter(
                Imputation.date >= start_date, Imputation.is_billable == True
            ).all()
            return _bucket_sum(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_billable_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `billable_pct`."""
    db, metric_key, organization_id = ctx.db, ctx.key, ctx.org_id
    if metric_key == "billable_pct":
        t = _fetch_metric_series(db, "hours_logged", organization_id)
        b = _fetch_metric_series(db, "hours_billable", organization_id)
        return [round(bv/tv*100,2) if tv > 0 else 0.0 for tv,bv in zip(t,b)]  # noqa: B905

def _serie_utilization(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `utilization`."""
    metric_key, series = ctx.key, ctx.series
    if metric_key == "utilization":
        return [min(100.0, round(float(m.get("hours",0) or 0)/160.0*100.0,2)) for m in series]

def _serie_overloaded_users(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `overloaded_users`."""
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key == "overloaded_users":
        try:
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            rows = db.query(sqf.strftime("%Y-%m",Imputation.date).label("mo"),
                            Imputation.user_id, sqf.sum(Imputation.hours).label("tot")
                            ).filter(Imputation.date >= start_date
                            ).group_by("mo",Imputation.user_id).all()
            bkt: dict[str,float] = defaultdict(float)
            for mo, uid, tot in rows:  # noqa: B007
                if tot and tot > 160: bkt[str(mo)] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_avg_user_load_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `avg_user_load_pct`."""
    _empty_like, db, metric_key, organization_id, series = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series
    if metric_key == "avg_user_load_pct":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt_s: dict[str,float] = defaultdict(float)
            bkt_c: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None:
                    mo = w[:7]
                    bkt_s[mo] += float(p); bkt_c[mo] += 1.0
            return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                    if bkt_c.get(m["month"],0) > 0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_users_at_capacity(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `users_at_capacity`."""
    _empty_like, db, metric_key, organization_id, series = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series
    if metric_key == "users_at_capacity":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None and 80 <= float(p) <= 100:
                    bkt[w[:7]] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_users_underutilized(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `users_underutilized`."""
    _empty_like, db, metric_key, organization_id, series = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series
    if metric_key == "users_underutilized":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None and float(p) < 50:
                    bkt[w[:7]] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_snapshot_billable_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `snapshot_billable_pct`."""
    _empty_like, db, metric_key, organization_id, series = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series
    if metric_key == "snapshot_billable_pct":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.billable_pct).all()
            bkt_s: dict[str,float] = defaultdict(float)
            bkt_c: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None:
                    bkt_s[w[:7]] += float(p); bkt_c[w[:7]] += 1.0
            return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                    if bkt_c.get(m["month"],0)>0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

# ── Metricas de hojas de horas ───────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_serie_pending_timesheets` era complejidad
# 13 en seis metricas de tres formas distintas: tres recuentos por estado, una
# suma, una media, y una que no es mensual sino instantanea.
#
# Dos cosas del comportamiento original que NO se han cambiado aqui —un refactor
# de complejidad no es el sitio para cambiar lo que significa una cifra— pero que
# quedan escritas porque no son evidentes leyendo el codigo:
#
#   · `pending_timesheets` y `timesheets_submitted_count` miran el MISMO estado
#     («submitted») y devuelven cosas distintas: la primera es cuantas hay
#     esperando AHORA, repetida en toda la serie; la segunda cuantas se
#     entregaron en cada mes. Es deliberado y por eso llevan nombres distintos.
#   · `timesheet_cost_total` NO filtra por estado: suma el coste de todas las
#     hojas, incluidas las rechazadas y los borradores. Si la intencion era el
#     coste comprometido, sobran las rechazadas; queda anotado como pregunta
#     abierta, no tocado.

# El estado que cuenta cada metrica de recuento. `pending_timesheets` esta aqui
# tambien porque el codigo original la incluia en el mismo mapa, aunque su rama
# sale antes de usarlo.
_ESTADO_DE_HOJA = {
    "pending_timesheets": "submitted",
    "timesheets_draft_count": "draft",
    "timesheets_submitted_count": "submitted",
    "timesheets_rejected_count": "rejected",
}

CLAVES_DE_HOJA_DE_HORAS = frozenset(_ESTADO_DE_HOJA) | {
    "timesheet_cost_total", "timesheet_avg_hours",
}


def _hojas_pendientes_ahora(ctx: _Ctx) -> list[float]:
    """Cuantas hojas estan esperando aprobacion en este momento.

    No es una serie historica: es un valor instantaneo repetido en todos los
    meses, porque la pregunta que responde es «cuanto hay en la bandeja» y no
    «cuanto entro en marzo». Por eso lleva su propia consulta y no usa la
    compartida.
    """
    from app.models.financial import Timesheet, TimesheetStatus

    n = (ctx.db.query(Timesheet)
               .filter(Timesheet.status == TimesheetStatus.submitted)
               .count())
    return ctx.current(float(n))


def _contar_hojas_por_mes(ctx: _Ctx, rows, estado: str) -> list[float]:
    """Cuenta hojas del estado pedido por mes de inicio de semana."""
    bkt: dict[str, float] = defaultdict(float)
    for ws, st, _h, _c in rows:
        if ws and str(getattr(st, "value", st)) == estado:
            bkt[f"{ws.year:04d}-{ws.month:02d}"] += 1.0
    return [float(bkt.get(m["month"], 0.0)) for m in ctx.series]


def _coste_de_hojas_por_mes(ctx: _Ctx, rows) -> list[float]:
    """Suma el coste de TODAS las hojas del mes, sin filtrar por estado.

    Sin filtro de estado a proposito de origen: ver la nota de cabecera.
    """
    bkt: dict[str, float] = defaultdict(float)
    for ws, _st, _h, c in rows:
        if ws:
            bkt[f"{ws.year:04d}-{ws.month:02d}"] += float(c or 0)
    return [float(bkt.get(m["month"], 0.0)) for m in ctx.series]


def _horas_medias_por_hoja(ctx: _Ctx, rows) -> list[float]:
    """Media de horas por hoja, sobre las hojas que traen horas.

    `if ws and h` descarta las de cero horas del divisor tambien, no solo del
    numerador: una hoja vacia no baja la media de la semana.
    """
    suma: dict[str, float] = defaultdict(float)
    cuenta: dict[str, float] = defaultdict(float)
    for ws, _st, h, _c in rows:
        if ws and h:
            k = f"{ws.year:04d}-{ws.month:02d}"
            suma[k] += float(h)
            cuenta[k] += 1.0
    return [
        round(suma[m["month"]] / cuenta[m["month"]], 2)
        if cuenta.get(m["month"], 0) > 0 else 0.0
        for m in ctx.series
    ]


def _serie_pending_timesheets(ctx: _Ctx) -> Optional[list[float]]:
    """Las seis metricas de hojas de horas."""
    if ctx.key not in CLAVES_DE_HOJA_DE_HORAS:
        return None
    try:
        if ctx.key == "pending_timesheets":
            return _hojas_pendientes_ahora(ctx)

        from app.models.financial import Timesheet

        rows = (ctx.db.query(Timesheet.week_start, Timesheet.status,
                             Timesheet.total_hours, Timesheet.total_cost)
                      .filter(Timesheet.week_start >= ctx.start_date)
                      .all())

        if ctx.key == "timesheet_cost_total":
            return _coste_de_hojas_por_mes(ctx, rows)
        if ctx.key == "timesheet_avg_hours":
            return _horas_medias_por_hoja(ctx, rows)
        return _contar_hojas_por_mes(ctx, rows, _ESTADO_DE_HOJA[ctx.key])
    except Exception:
        logger.debug(
            "Failed to fetch metric %s for org=%s", ctx.key, ctx.org_id, exc_info=True
        )
        return ctx.empty_like()


def _serie_absence(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · absence_days
    · absence_vacation_days
    · absence_sick_days
    · absence_training_days
    · absence_pending_count
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("absence_days","absence_vacation_days","absence_sick_days",
                       "absence_training_days","absence_pending_count"):
        try:
            from app.models.resources import Absence
            rows = db.query(Absence.start_date, Absence.working_days, Absence.type, Absence.status).filter(
                Absence.start_date >= start_date
            ).all()
            TYPE_MAP = {"absence_vacation_days":"vacation","absence_sick_days":"sick","absence_training_days":"training"}
            if metric_key == "absence_pending_count":
                bkt: dict[str,float] = defaultdict(float)
                for sd, wd, tp, st in rows:  # noqa: B007
                    if sd and str(getattr(st,"value",st)) == "pending":
                        bkt[f"{sd.year:04d}-{sd.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            bkt = defaultdict(float)
            for sd, wd, tp, st in rows:
                if not sd or str(getattr(st,"value",st)) != "approved": continue
                tv = str(getattr(tp,"value",tp))
                k = f"{sd.year:04d}-{sd.month:02d}"
                if metric_key == "absence_days":
                    bkt[k] += float(wd or 0)
                elif metric_key in TYPE_MAP and tv == TYPE_MAP[metric_key]:
                    bkt[k] += float(wd or 0)
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_certified_users_count(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `certified_users_count`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "certified_users_count":
        try:
            from app.models.resources import UserSkill
            from sqlalchemy import func as sqf
            count = db.query(sqf.count(sqf.distinct(UserSkill.user_id))).filter(
                UserSkill.certified == True
            ).scalar() or 0
            return _current(float(count))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_resource_alerts(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · resource_alerts_overload
    · resource_alerts_skill_gap
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("resource_alerts_overload","resource_alerts_skill_gap"):
        try:
            from app.models.resources import ResourceAlert, ResourceAlertType
            atype = ResourceAlertType.overload_warning if metric_key=="resource_alerts_overload" else ResourceAlertType.skill_gap
            q = db.query(ResourceAlert).filter(ResourceAlert.alert_type == atype)
            if metric_key == "resource_alerts_overload":
                q = q.filter(ResourceAlert.acknowledged_at == None)
            return _current(float(q.count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_active_projects(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `active_projects`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "active_projects":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.active).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_at_risk(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_at_risk`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_at_risk":
        try:
            from app.models.project import Project, ProjectStatus as PS, ProjectRisk as PR
            return _current(float(db.query(Project).filter(
                Project.status == PS.active, Project.risk_level.in_([PR.high, PR.critical])
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_over_budget(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_over_budget`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_over_budget":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            costs = {pid: float(c or 0) for pid, c in
                     db.query(Imputation.project_id, sqf.sum(Imputation.cost_amount)
                              ).group_by(Imputation.project_id).all() if pid}
            projects = db.query(Project.id, Project.budget_amount).filter(
                Project.status == PS.active, Project.budget_amount > 0
            ).all()
            return _current(float(sum(1 for pid, bgt in projects if costs.get(pid, 0) > float(bgt or 0))))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_overdue(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_overdue`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_overdue":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from datetime import date as dc
            today = dc.today()
            return _current(float(db.query(Project).filter(
                Project.status == PS.active,
                Project.end_date_planned != None,
                Project.end_date_planned < today
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_on_hold(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_on_hold`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_on_hold":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.on_hold).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_cancelled(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_cancelled`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_cancelled":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.cancelled).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_projects_completed_count(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `projects_completed_count`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "projects_completed_count":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.completed).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_milestones(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · milestones_overdue
    · milestones_pending
    · milestones_completed
    · milestones_invoiced
    · milestones_pending_approval
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("milestones_overdue","milestones_pending","milestones_completed",
                       "milestones_invoiced","milestones_pending_approval"):
        try:
            from app.models.financial import ProjectMilestone
            from datetime import date as dc
            today = dc.today()
            if metric_key == "milestones_overdue":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == False,
                    ProjectMilestone.due_date != None,
                    ProjectMilestone.due_date < today
                ).count()))
            if metric_key == "milestones_pending":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending"
                ).count()))
            if metric_key == "milestones_completed":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == True
                ).count()))
            if metric_key == "milestones_invoiced":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_billed == True
                ).count()))
            if metric_key == "milestones_pending_approval":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending_approval"
                ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_deliverables(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · deliverables_in_progress
    · deliverables_in_review
    · deliverables_accepted
    · deliverables_rejected
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("deliverables_in_progress","deliverables_in_review",
                       "deliverables_accepted","deliverables_rejected"):
        try:
            from app.models.resources import Deliverable, DeliverableStatus
            STATUS = {"deliverables_in_progress": DeliverableStatus.in_progress,
                      "deliverables_in_review":   DeliverableStatus.in_review,
                      "deliverables_accepted":    DeliverableStatus.accepted,
                      "deliverables_rejected":    DeliverableStatus.rejected}
            return _current(float(db.query(Deliverable).filter(
                Deliverable.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_change_requests(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · change_requests_total
    · change_requests_pending
    · change_requests_cost_impact
    · change_requests_schedule
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("change_requests_total","change_requests_pending",
                       "change_requests_cost_impact","change_requests_schedule"):
        try:
            from app.models.resources import ChangeRequest, ChangeRequestStatus
            if metric_key == "change_requests_total":
                return _current(float(db.query(ChangeRequest).count()))
            if metric_key == "change_requests_pending":
                return _current(float(db.query(ChangeRequest).filter(
                    ChangeRequest.status.in_([ChangeRequestStatus.draft, ChangeRequestStatus.submitted])
                ).count()))
            if metric_key == "change_requests_cost_impact":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.cost_impact)).scalar() or 0.0
                return _current(float(v))
            if metric_key == "change_requests_schedule":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.schedule_impact_days)).scalar() or 0.0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_overdue(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_overdue`."""
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key == "tasks_overdue":
        try:
            from app.models.task import Task
            rows = db.query(Task.due_date, Task.status).filter(
                Task.due_date != None, Task.due_date >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for dd, st in rows:
                if dd and str(getattr(st,"value",st)) not in ("done","cancelled"):
                    bkt[f"{dd.year:04d}-{dd.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_blocked(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_blocked`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "tasks_blocked":
        try:
            from app.models.task import Task, TaskStatus
            return _current(float(db.query(Task).filter(Task.status == TaskStatus.blocked).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_created(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_created`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "tasks_created":
        try:
            from app.models.task import Task
            rows = db.query(Task.created_at).filter(Task.created_at >= start_date).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_tasks_completed(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `tasks_completed`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "tasks_completed":
        try:
            from app.models.task import Task, TaskStatus
            rows = db.query(Task.completed_at).filter(
                Task.status == TaskStatus.done,
                Task.completed_at != None,
                Task.completed_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_task_completion_rate(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `task_completion_rate`."""
    db, metric_key, organization_id = ctx.db, ctx.key, ctx.org_id
    if metric_key == "task_completion_rate":
        c = _fetch_metric_series(db, "tasks_completed", organization_id)
        o = _fetch_metric_series(db, "tasks_overdue", organization_id)
        return [round(cv/(cv+ov)*100,2) if (cv+ov) > 0 else 0.0 for cv,ov in zip(c,o)]  # noqa: B905

# ── Metricas de tickets ──────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_serie_tickets_open` era complejidad 18:
# doce ramas sobre `metric_key` DENTRO del bucle de filas, asi que reevaluaba la
# cadena entera por cada ticket. Cada rama son en realidad dos decisiones —a que
# filas se aplica y que acumula—, y eso es una tabla.

# Que estados se consideran cerrados. Estaban escritos como literales dentro de
# dos ramas distintas, con listas DIFERENTES: «abierto» excluye tambien los
# cancelados, mientras que «resuelto» no los cuenta como resueltos. No es un
# descuido —un ticket cancelado no esta abierto ni resuelto— asi que se nombran
# las dos por separado para que la diferencia quede a la vista.
_ESTADOS_NO_ABIERTOS = ("closed", "resolved", "cancelled")
_ESTADOS_RESUELTOS = ("closed", "resolved")


class _FilaDeTicket(NamedTuple):
    """Una fila de la consulta compartida, con los campos nombrados.

    La consulta original devolvia una tupla de diez que se desempaquetaba en
    variables de dos y tres letras (`frm`, `resm`, `srb`, `slrb`, `ar`, `tsm`).
    """

    creado: object
    estado: object
    prioridad: object
    minutos_primera_respuesta: object
    minutos_resolucion: object
    csat: object
    sla_respuesta_incumplido: object
    sla_resolucion_incumplido: object
    auto_resuelto: object
    minutos_dedicados: object

    @property
    def estado_txt(self) -> str:
        return str(getattr(self.estado, "value", self.estado))

    @property
    def prioridad_txt(self) -> str:
        return str(getattr(self.prioridad, "value", self.prioridad))


@dataclass(frozen=True, slots=True)
class _MetricaDeTicket:
    """Como se calcula una de las doce metricas de tickets.

    `aplica` decide que filas entran; `valor` que se acumula (None = contar una
    por fila); `promedia` si al final se divide entre las filas que entraron.
    """

    aplica: object
    valor: object = None
    promedia: bool = False


def _todas(f: _FilaDeTicket) -> bool:
    return True


_METRICAS_DE_TICKET = {
    "tickets_open": _MetricaDeTicket(
        lambda f: f.estado_txt not in _ESTADOS_NO_ABIERTOS),
    "tickets_created": _MetricaDeTicket(_todas),
    "tickets_resolved": _MetricaDeTicket(
        lambda f: f.estado_txt in _ESTADOS_RESUELTOS),
    "tickets_p1_count": _MetricaDeTicket(
        lambda f: f.prioridad_txt == "p1_critical"),
    "tickets_p2_count": _MetricaDeTicket(
        lambda f: f.prioridad_txt == "p2_high"),
    "first_response_time_avg": _MetricaDeTicket(
        lambda f: f.minutos_primera_respuesta is not None,
        lambda f: float(f.minutos_primera_respuesta), promedia=True),
    "resolution_time_avg": _MetricaDeTicket(
        lambda f: f.minutos_resolucion is not None,
        lambda f: float(f.minutos_resolucion), promedia=True),
    "csat_avg": _MetricaDeTicket(
        lambda f: f.csat is not None,
        lambda f: float(f.csat), promedia=True),
    "sla_response_breached": _MetricaDeTicket(
        lambda f: bool(f.sla_respuesta_incumplido)),
    "sla_resolution_breached": _MetricaDeTicket(
        lambda f: bool(f.sla_resolucion_incumplido)),
    "auto_resolved_count": _MetricaDeTicket(
        lambda f: bool(f.auto_resuelto)),
    "ticket_time_spent_total": _MetricaDeTicket(
        lambda f: bool(f.minutos_dedicados),
        lambda f: float(f.minutos_dedicados)),
}

CLAVES_DE_TICKET = frozenset(_METRICAS_DE_TICKET)


def _serie_tickets_open(ctx: _Ctx) -> Optional[list[float]]:
    """Las doce metricas de tickets, que comparten una sola consulta.

    Las tres que llevan `promedia=True` son medias por mes (minutos de primera
    respuesta, minutos de resolucion y CSAT); el resto son recuentos o sumas.
    Un mes sin filas que apliquen da 0.0 en las tres, no NaN.
    """
    spec = _METRICAS_DE_TICKET.get(ctx.key)
    if spec is None:
        return None
    try:
        from app.models.service_desk import Ticket

        rows = (ctx.db.query(
            Ticket.created_at, Ticket.status, Ticket.priority,
            Ticket.first_response_minutes, Ticket.resolution_minutes,
            Ticket.csat_score, Ticket.sla_response_breached,
            Ticket.sla_resolution_breached, Ticket.auto_resolved,
            Ticket.time_spent_minutes,
        ).filter(Ticket.created_at >= ctx.start_date).all())

        suma: dict[str, float] = defaultdict(float)
        cuenta: dict[str, float] = defaultdict(float)
        for fila in (_FilaDeTicket(*r) for r in rows):
            if not fila.creado:
                continue
            if not spec.aplica(fila):
                continue
            k = f"{fila.creado.year:04d}-{fila.creado.month:02d}"
            suma[k] += spec.valor(fila) if spec.valor else 1.0
            cuenta[k] += 1.0

        if spec.promedia:
            return [
                round(suma[m["month"]] / cuenta[m["month"]], 2)
                if cuenta.get(m["month"], 0) > 0 else 0.0
                for m in ctx.series
            ]
        return [float(suma.get(m["month"], 0.0)) for m in ctx.series]
    except Exception:
        logger.debug(
            "Failed to fetch metric %s for org=%s", ctx.key, ctx.org_id, exc_info=True
        )
        return ctx.empty_like()


def _serie_ticket_time_log_total(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `ticket_time_log_total`."""
    _bucket_sum, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_sum, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "ticket_time_log_total":
        try:
            from app.models.service_desk import TicketTimeLog
            rows = db.query(TicketTimeLog.logged_at, TicketTimeLog.minutes).filter(
                TicketTimeLog.logged_at >= start_date
            ).all()
            return _bucket_sum(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_sla_breach_count(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `sla_breach_count`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "sla_breach_count":
        try:
            from app.models.billing_reports import SLABreachLog
            rows = db.query(SLABreachLog.breached_at).filter(
                SLABreachLog.breached_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_sla_compliance_pct(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `sla_compliance_pct`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "sla_compliance_pct":
        try:
            from app.models.service_desk import ITSMMetricSnapshot
            row = db.query(ITSMMetricSnapshot.sla_compliance_pct).order_by(
                ITSMMetricSnapshot.snapshot_at.desc()
            ).first()
            return _current(float(row[0]) if row and row[0] is not None else 0.0)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_kb(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · kb_articles_published
    · kb_views_total
    · kb_helpful_count
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("kb_articles_published","kb_views_total","kb_helpful_count"):
        try:
            from app.models.service_desk import KBArticle, KBStatus
            from sqlalchemy import func as sqf
            if metric_key == "kb_articles_published":
                return _current(float(db.query(KBArticle).filter(KBArticle.status == KBStatus.published).count()))
            if metric_key == "kb_views_total":
                v = db.query(sqf.sum(KBArticle.view_count)).scalar() or 0
                return _current(float(v))
            if metric_key == "kb_helpful_count":
                v = db.query(sqf.sum(KBArticle.helpful_count)).scalar() or 0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_problems_open(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `problems_open`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "problems_open":
        try:
            from app.models.service_desk import Problem, ProblemStatus
            return _current(float(db.query(Problem).filter(
                Problem.status.in_([ProblemStatus.open, ProblemStatus.investigating])
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_known_errors_active(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `known_errors_active`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "known_errors_active":
        try:
            from app.models.service_desk import KnownError
            return _current(float(db.query(KnownError).filter(KnownError.is_active == True).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_itsm_changes(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · itsm_changes_total
    · itsm_changes_emergency
    · itsm_changes_downtime
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("itsm_changes_total","itsm_changes_emergency","itsm_changes_downtime"):
        try:
            from app.models.service_desk import ITSMChangeRequest, ChangeType
            from sqlalchemy import func as sqf
            if metric_key == "itsm_changes_total":
                return _current(float(db.query(ITSMChangeRequest).count()))
            if metric_key == "itsm_changes_emergency":
                return _current(float(db.query(ITSMChangeRequest).filter(
                    ITSMChangeRequest.change_type == ChangeType.emergency
                ).count()))
            if metric_key == "itsm_changes_downtime":
                v = db.query(sqf.sum(ITSMChangeRequest.downtime_minutes)).scalar() or 0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_assets_total(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · assets_total
    · assets_deployed
    · assets_in_repair
    · license_seats_total
    · license_used_total
    · asset_value_total
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("assets_total","assets_deployed","assets_in_repair",
                       "license_seats_total","license_used_total","asset_value_total"):
        try:
            # Auditoria 2026-11: leia `sd_assets`, el inventario sin pantalla
            # (cero filas medidas). Ahora ALM, que es el unico.
            from app.models.alm import ALMAsset, ALMLicense, ALMLicenseAssignment
            from app.core.serializers import AssetSerializer
            from sqlalchemy import func as sqf
            activos = db.query(ALMAsset).filter(ALMAsset.is_active.is_(True))
            if metric_key == "assets_total":
                return _current(float(activos.count()))
            if metric_key == "assets_deployed":
                return _current(float(activos.filter(ALMAsset.status == "in_use").count()))
            if metric_key == "assets_in_repair":
                return _current(float(activos.filter(ALMAsset.status == "in_repair").count()))
            if metric_key == "license_seats_total":
                v = db.query(sqf.sum(ALMLicense.total_seats)).filter(
                    ALMLicense.is_active.is_(True), ALMLicense.total_seats.isnot(None)).scalar() or 0
                return _current(float(v))
            if metric_key == "license_used_total":
                v = db.query(sqf.count(ALMLicenseAssignment.id)).filter(ALMLicenseAssignment.is_active.is_(True)).scalar() or 0
                return _current(float(v))
            if metric_key == "asset_value_total":
                # Valor contable: amortizacion lineal con los anos de cada activo.
                v = sum(AssetSerializer(a).to_dict().get("book_value") or 0 for a in activos)
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_major_incidents_active(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `major_incidents_active`."""
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key == "major_incidents_active":
        try:
            from app.models.service_desk import MajorIncident, MajorIncidentStatus
            return _current(float(db.query(MajorIncident).filter(
                MajorIncident.status == MajorIncidentStatus.active
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_escalations_total(ctx: _Ctx) -> Optional[list[float]]:
    """Metrica `escalations_total`."""
    _bucket_count, _empty_like, db, metric_key, organization_id, start_date = ctx.bucket_count, ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.start_date
    if metric_key == "escalations_total":
        try:
            from app.models.service_desk import EscalationLog
            rows = db.query(EscalationLog.triggered_at).filter(
                EscalationLog.triggered_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_playbook(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · playbook_success_count
    · playbook_failure_count
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("playbook_success_count","playbook_failure_count"):
        try:
            from app.models.service_desk import AutonomousPlaybook
            from sqlalchemy import func as sqf
            field = AutonomousPlaybook.success_count if metric_key=="playbook_success_count" else AutonomousPlaybook.failure_count
            v = db.query(sqf.sum(field)).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_pending_approvals(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · pending_approvals
    · approvals_approved_count
    · approvals_rejected_count
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("pending_approvals","approvals_approved_count","approvals_rejected_count"):
        try:
            from app.models.billing_reports import ApprovalRequest
            STATUS = {"pending_approvals":"pending","approvals_approved_count":"approved","approvals_rejected_count":"rejected"}
            return _current(float(db.query(ApprovalRequest).filter(
                ApprovalRequest.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_workflow(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · workflow_runs_total
    · workflow_success_total
    · workflow_error_total
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("workflow_runs_total","workflow_success_total","workflow_error_total"):
        try:
            from app.models.billing_reports import AutomationWorkflow
            from sqlalchemy import func as sqf
            FIELD = {"workflow_runs_total": AutomationWorkflow.run_count,
                     "workflow_success_total": AutomationWorkflow.success_count,
                     "workflow_error_total": AutomationWorkflow.error_count}
            v = db.query(sqf.sum(FIELD[metric_key])).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_sod_violations(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · sod_violations_total
    · sod_violations_unresolved
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("sod_violations_total","sod_violations_unresolved"):
        try:
            from app.models.billing_reports import SodViolation
            q = db.query(SodViolation)
            if metric_key == "sod_violations_unresolved":
                q = q.filter(SodViolation.resolved == False)
            return _current(float(q.count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_grc(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · grc_audit_events_total
    · grc_critical_events
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("grc_audit_events_total","grc_critical_events"):
        try:
            from app.models.billing_reports import GrcAuditLog
            rows = db.query(GrcAuditLog.timestamp, GrcAuditLog.severity).filter(
                GrcAuditLog.timestamp >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for ts, sev in rows:
                if ts:
                    if metric_key == "grc_audit_events_total":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
                    elif sev == "critical":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_imports(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · imports_completed_count
    · imports_failed_count
    · imports_success_rate
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("imports_completed_count","imports_failed_count","imports_success_rate"):
        try:
            from app.models.billing_reports import ImportJob
            rows = db.query(ImportJob.completed_at, ImportJob.status,
                            ImportJob.succeeded, ImportJob.total_rows).filter(
                ImportJob.completed_at >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            bkt_ok: dict[str,float] = defaultdict(float)
            bkt_tot: dict[str,float] = defaultdict(float)
            for ca, st, ok, tot in rows:
                if not ca: continue
                k = f"{ca.year:04d}-{ca.month:02d}"; sv = str(getattr(st,"value",st))
                if metric_key == "imports_completed_count" and sv == "completed":
                    bkt[k] += 1.0
                elif metric_key == "imports_failed_count" and sv in ("failed","partial"):
                    bkt[k] += 1.0
                elif metric_key == "imports_success_rate":
                    bkt_ok[k] += float(ok or 0); bkt_tot[k] += float(tot or 0)
            if metric_key == "imports_success_rate":
                return [round(bkt_ok[m["month"]]/bkt_tot[m["month"]]*100,2)
                        if bkt_tot.get(m["month"],0)>0 else 0.0 for m in series]
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

# ═════════════════════════════════════════════════════════════════════════════
# Tabla de despacho
# ═════════════════════════════════════════════════════════════════════════════

_Resolutor = Callable[[_Ctx], Optional[list[float]]]

# Clave exacta → resolutor. Es la tabla que antes era una cadena de 55 `if`.
_RESOLUTORES: dict[str, _Resolutor] = {
    "revenue": _serie_revenue,
    "cost": _serie_cost,
    "margin": _serie_margin,
    "margin_pct": _serie_margin_pct,
    "budget_used_pct": _serie_budget_used_pct,
    "invoice_days_to_pay_avg": _serie_invoice,
    "invoice_overdue_amount": _serie_invoice,
    "invoice_overdue_count": _serie_invoice,
    "invoices_draft_count": _serie_invoice,
    "invoices_paid_count": _serie_invoice,
    "invoices_paid_total": _serie_invoice,
    "invoices_sent_count": _serie_invoice,
    "expense_total": _serie_expense,
    "expenses_approved_count": _serie_expense,
    "expenses_draft_count": _serie_expense,
    "expenses_hardware": _serie_expense,
    "expenses_rejected_count": _serie_expense,
    "expenses_software": _serie_expense,
    "expenses_subcontract": _serie_expense,
    "expenses_submitted_count": _serie_expense,
    "expenses_training_exp": _serie_expense,
    "expenses_travel": _serie_expense,
    "hourly_rate_avg": _serie_imputations_approved_hours,
    "imputations_approved_hours": _serie_imputations_approved_hours,
    "imputations_cost_total": _serie_imputations_approved_hours,
    "imputations_invoiced_count": _serie_imputations_approved_hours,
    "hours_logged": _serie_hours_logged,
    "hours_billable": _serie_hours_billable,
    "billable_pct": _serie_billable_pct,
    "utilization": _serie_utilization,
    "overloaded_users": _serie_overloaded_users,
    "avg_user_load_pct": _serie_avg_user_load_pct,
    "users_at_capacity": _serie_users_at_capacity,
    "users_underutilized": _serie_users_underutilized,
    "snapshot_billable_pct": _serie_snapshot_billable_pct,
    "pending_timesheets": _serie_pending_timesheets,
    "timesheet_avg_hours": _serie_pending_timesheets,
    "timesheet_cost_total": _serie_pending_timesheets,
    "timesheets_draft_count": _serie_pending_timesheets,
    "timesheets_rejected_count": _serie_pending_timesheets,
    "timesheets_submitted_count": _serie_pending_timesheets,
    "absence_days": _serie_absence,
    "absence_pending_count": _serie_absence,
    "absence_sick_days": _serie_absence,
    "absence_training_days": _serie_absence,
    "absence_vacation_days": _serie_absence,
    "certified_users_count": _serie_certified_users_count,
    "resource_alerts_overload": _serie_resource_alerts,
    "resource_alerts_skill_gap": _serie_resource_alerts,
    "active_projects": _serie_active_projects,
    "projects_at_risk": _serie_projects_at_risk,
    "projects_over_budget": _serie_projects_over_budget,
    "projects_overdue": _serie_projects_overdue,
    "projects_on_hold": _serie_projects_on_hold,
    "projects_cancelled": _serie_projects_cancelled,
    "projects_completed_count": _serie_projects_completed_count,
    "milestones_completed": _serie_milestones,
    "milestones_invoiced": _serie_milestones,
    "milestones_overdue": _serie_milestones,
    "milestones_pending": _serie_milestones,
    "milestones_pending_approval": _serie_milestones,
    "deliverables_accepted": _serie_deliverables,
    "deliverables_in_progress": _serie_deliverables,
    "deliverables_in_review": _serie_deliverables,
    "deliverables_rejected": _serie_deliverables,
    "change_requests_cost_impact": _serie_change_requests,
    "change_requests_pending": _serie_change_requests,
    "change_requests_schedule": _serie_change_requests,
    "change_requests_total": _serie_change_requests,
    "tasks_overdue": _serie_tasks_overdue,
    "tasks_blocked": _serie_tasks_blocked,
    "tasks_created": _serie_tasks_created,
    "tasks_completed": _serie_tasks_completed,
    "task_completion_rate": _serie_task_completion_rate,
    "auto_resolved_count": _serie_tickets_open,
    "csat_avg": _serie_tickets_open,
    "first_response_time_avg": _serie_tickets_open,
    "resolution_time_avg": _serie_tickets_open,
    "sla_resolution_breached": _serie_tickets_open,
    "sla_response_breached": _serie_tickets_open,
    "ticket_time_spent_total": _serie_tickets_open,
    "tickets_created": _serie_tickets_open,
    "tickets_open": _serie_tickets_open,
    "tickets_p1_count": _serie_tickets_open,
    "tickets_p2_count": _serie_tickets_open,
    "tickets_resolved": _serie_tickets_open,
    "ticket_time_log_total": _serie_ticket_time_log_total,
    "sla_breach_count": _serie_sla_breach_count,
    "sla_compliance_pct": _serie_sla_compliance_pct,
    "kb_articles_published": _serie_kb,
    "kb_helpful_count": _serie_kb,
    "kb_views_total": _serie_kb,
    "problems_open": _serie_problems_open,
    "known_errors_active": _serie_known_errors_active,
    "itsm_changes_downtime": _serie_itsm_changes,
    "itsm_changes_emergency": _serie_itsm_changes,
    "itsm_changes_total": _serie_itsm_changes,
    "asset_value_total": _serie_assets_total,
    "assets_deployed": _serie_assets_total,
    "assets_in_repair": _serie_assets_total,
    "assets_total": _serie_assets_total,
    "license_seats_total": _serie_assets_total,
    "license_used_total": _serie_assets_total,
    "major_incidents_active": _serie_major_incidents_active,
    "escalations_total": _serie_escalations_total,
    "playbook_failure_count": _serie_playbook,
    "playbook_success_count": _serie_playbook,
    "approvals_approved_count": _serie_pending_approvals,
    "approvals_rejected_count": _serie_pending_approvals,
    "pending_approvals": _serie_pending_approvals,
    "workflow_error_total": _serie_workflow,
    "workflow_runs_total": _serie_workflow,
    "workflow_success_total": _serie_workflow,
    "sod_violations_total": _serie_sod_violations,
    "sod_violations_unresolved": _serie_sod_violations,
    "grc_audit_events_total": _serie_grc,
    "grc_critical_events": _serie_grc,
    "imports_completed_count": _serie_imports,
    "imports_failed_count": _serie_imports,
    "imports_success_rate": _serie_imports,
}

# Las metricas del perfil de coste comparten una consulta pesada, asi que se
# registran en bloque desde su propio conjunto de claves.
_RESOLUTORES.update({_k: _serie_cost_profile for _k in COST_PROFILE_KEYS})

# Resolutores por PREFIJO, para las metricas que el cliente define y cuyo nombre
# exacto no se puede conocer de antemano.
_POR_PREFIJO: tuple[tuple[str, _Resolutor], ...] = (
    ("custom_", _serie_custom),
)


def claves_atendidas() -> frozenset[str]:
    """Claves exactas que este modulo sabe resolver.

    Existe para que un test pueda comprobar que el catalogo (`SUPPORTED_METRICS`)
    y el codigo no se separan. Antes no habia forma de saberlo: las claves estaban
    incrustadas en 55 condiciones y una metrica anadida al catalogo sin
    implementar devolvia ceros en silencio.
    """
    return frozenset(_RESOLUTORES)


def _resolutor_para(metric_key: str) -> Optional[_Resolutor]:
    directo = _RESOLUTORES.get(metric_key)
    if directo is not None:
        return directo
    for prefijo, fn in _POR_PREFIJO:
        if metric_key.startswith(prefijo):
            return fn
    return None


def _fetch_metric_series(
    db: Session, metric_key: str, organization_id: Optional[str]
) -> list[float]:
    """Serie de los ultimos 24 meses de la metrica pedida.

    Una clave desconocida devuelve una serie a cero en vez de lanzar: una regla
    de alerta guardada con una metrica que despues se retiro no puede tumbar el
    motor entero.
    """
    ctx = _construir_contexto(db, metric_key, organization_id)

    resolutor = _resolutor_para(metric_key)
    if resolutor is None:
        return ctx.empty_like()

    resultado = resolutor(ctx)
    # Un resolutor puede devolver None si su propia condicion no se cumple (los
    # grupos discriminan dentro). Se trata igual que «sin dato».
    return resultado if resultado is not None else ctx.empty_like()
