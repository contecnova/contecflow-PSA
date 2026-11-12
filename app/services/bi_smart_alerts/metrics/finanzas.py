"""Series financieras: ingresos, coste, margen, facturas, gastos y perfil de coste.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app.services.bi_smart_alerts.metrics._contexto import _Ctx, logger


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
