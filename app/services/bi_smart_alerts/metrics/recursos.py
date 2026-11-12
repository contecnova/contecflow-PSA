"""Series de personas: horas, carga, hojas de horas, ausencias, certificaciones y alertas de recursos.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.services.bi_smart_alerts.metrics._contexto import _Ctx, logger


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
