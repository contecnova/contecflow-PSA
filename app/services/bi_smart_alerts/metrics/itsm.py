"""Series de service desk: tickets, SLA, base de conocimiento, problemas, cambios, activos e incidentes.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple, Optional

from app.services.bi_smart_alerts.metrics._contexto import _Ctx, logger


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
            q = db.query(ITSMMetricSnapshot.sla_compliance_pct)
            if organization_id:   # revisión 2026-11: la instantánea es por empresa
                q = q.filter(ITSMMetricSnapshot.organization_id == organization_id)
            row = q.order_by(ITSMMetricSnapshot.snapshot_at.desc()).first()
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
