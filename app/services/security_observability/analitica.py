"""Analitica de seguridad: tendencias, resumenes y paneles.

Parte de `app.services.security_observability` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.

Periodo libre (16-11-2026): los paneles aceptan ``p`` (``app.core.periodo.Periodo``)
para cualquier intervalo ``[p.desde, p.hasta)``; sin ``p`` siguen usando
``hours``/``days`` hasta ahora, como antes. Los listados paginados aceptan
``until`` (exclusivo) ademas de ``since``.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from app.models.security_observability import (
    SecurityEvent,
    SecurityDetection,
    SecurityIncident,
    LoginAnomaly,
    IncidentStatus,
)

from app.services.security_observability._comun import _utcnow


def _ventana(col, p, *, hours: Optional[float] = None, days: Optional[float] = None,
             since: Optional[datetime] = None, until: Optional[datetime] = None) -> list:
    """Condiciones de la ventana: la del periodo si llega, si no la historica."""
    if p is not None:
        from app.core.periodo import filtro_de_periodo
        return [filtro_de_periodo(col, p)]
    if since is None:
        since = _utcnow() - (timedelta(hours=hours) if hours is not None else timedelta(days=days or 0))
    conds = [col >= since]
    if until is not None:
        conds.append(col < until)
    return conds


# ── Analytics query helpers ───────────────────────────────────────────────────

class SecurityAnalyticsService:
    """Query layer for SOC dashboard panels."""

    def __init__(self, db: Session, org_id: str):
        self.db     = db
        self.org_id = org_id

    def overview(self, hours: int = 24, p=None) -> Dict[str, Any]:
        """Top-level SOC overview: event counts, open detections/incidents, KPIs.

        Con ``p``: eventos y anomalias del periodo. Las detecciones/incidentes
        abiertos son estado actual y MTTD/MTTR siguen siendo de los ultimos 30
        dias (no dependen del periodo).
        """
        base = self.db.query(SecurityEvent).filter(
            SecurityEvent.org_id       == self.org_id,
            *_ventana(SecurityEvent.occurred_at, p, hours=hours),
        )

        total    = base.count()
        by_sev   = {}
        for sev in ["info", "low", "medium", "high", "critical"]:
            by_sev[sev] = base.filter(SecurityEvent.severity == sev).count()

        # Auth failure rate
        logins_total   = base.filter(SecurityEvent.event_type.in_(["login_success", "login_failed"])).count()
        logins_failed  = base.filter(SecurityEvent.event_type == "login_failed").count()
        auth_fail_rate = round(logins_failed / logins_total, 4) if logins_total > 0 else 0.0

        # Open detections
        open_dets = self.db.query(func.count(SecurityDetection.id)).filter(
            SecurityDetection.org_id  == self.org_id,
            SecurityDetection.status  == IncidentStatus.OPEN,
        ).scalar() or 0

        critical_dets = self.db.query(func.count(SecurityDetection.id)).filter(
            SecurityDetection.org_id  == self.org_id,
            SecurityDetection.status  == IncidentStatus.OPEN,
            SecurityDetection.severity.in_(["high", "critical"]),
        ).scalar() or 0

        # MTTD/MTTR (last 30 days)
        mttd_avg = self._avg_mttd(days=30)
        mttr_avg = self._avg_mttr(days=30)

        # Open incidents
        open_inc = self.db.query(func.count(SecurityIncident.id)).filter(
            SecurityIncident.org_id == self.org_id,
            SecurityIncident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]),
        ).scalar() or 0

        # Anomalies last 24h
        anomalies = self.db.query(func.count(LoginAnomaly.id)).filter(
            LoginAnomaly.org_id      == self.org_id,
            *_ventana(LoginAnomaly.occurred_at, p, hours=hours),
        ).scalar() or 0

        salida = {
            "window_hours":     round(p.dias * 24, 2) if p is not None else hours,
            "total_events":     total,
            "events_by_severity": by_sev,
            "auth_failure_rate":  auth_fail_rate,
            "open_detections":    open_dets,
            "critical_detections": critical_dets,
            "open_incidents":     open_inc,
            "login_anomalies":    anomalies,
            "avg_mttd_seconds":   mttd_avg,
            "avg_mttr_seconds":   mttr_avg,
        }
        if p is not None:
            salida["periodo"] = p.a_dict()
        return salida

    def event_timeline(self, hours: int = 24, bucket_minutes: int = 60, p=None,
                       por_minutos: bool = False) -> List[Dict[str, Any]]:
        """Events bucketed by time for sparkline/timeline charts.

        Con ``p`` (y sin ``por_minutos``) la serie va por tramos de
        ``p.granularidad`` en la zona del periodo, rellena con ceros; cada punto
        lleva ``t`` (ISO con desfase), ``clave`` y, por compatibilidad, ``ts``.
        ``por_minutos`` conserva el agrupado historico de ``bucket_minutes``
        dentro del periodo.
        """
        rows = self.db.query(
            SecurityEvent.severity,
            SecurityEvent.occurred_at,
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            *_ventana(SecurityEvent.occurred_at, p, hours=hours),
        ).all()

        if p is not None and not por_minutos:
            ceros = {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
            tramos: Dict[str, Dict[str, int]] = {}
            for sev, ts in rows:
                k = p.clave(ts)
                if k is None:
                    continue
                fila = tramos.setdefault(k, dict(ceros))
                fila[sev] = fila.get(sev, 0) + 1
            serie = p.rellenar(tramos, vacio=ceros)
            for punto in serie:
                punto["ts"] = punto["t"]
            return serie

        buckets: Dict[str, Dict[str, int]] = {}
        for sev, ts in rows:
            bucket_ts = ts.replace(
                minute=(ts.minute // bucket_minutes) * bucket_minutes,
                second=0, microsecond=0
            )
            key = bucket_ts.isoformat()
            if key not in buckets:
                buckets[key] = {"ts": key, "info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
            buckets[key][sev] = buckets[key].get(sev, 0) + 1

        return sorted(buckets.values(), key=lambda x: x["ts"])

    def top_attack_indicators(self, hours: int = 24, limit: int = 10, p=None) -> List[Dict[str, Any]]:
        """Top open detections by severity + recency (attack indicator board)."""
        dets = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            *_ventana(SecurityDetection.detected_at, p, hours=hours),
        ).order_by(
            SecurityDetection.severity.desc(),
            SecurityDetection.detected_at.desc(),
        ).limit(limit).all()

        return [
            {
                "id":            d.id,
                "title":         d.title,
                "severity":      d.severity,
                "category":      d.category,
                "mitre_id":      d.mitre_id,
                "mitre_tactic":  d.mitre_tactic,
                "kill_chain":    d.kill_chain,
                "event_count":   d.event_count,
                "status":        d.status,
                "user_id":       d.user_id,
                "ip_address":    d.ip_address,
                "detected_at":   d.detected_at.isoformat() if d.detected_at else None,
            }
            for d in dets
        ]

    def login_anomaly_feed(self, hours: int = 24, unresolved_only: bool = True) -> List[Dict[str, Any]]:
        """Login anomaly feed for the dedicated anomaly panel."""
        since = _utcnow() - timedelta(hours=hours)
        q = self.db.query(LoginAnomaly).filter(
            LoginAnomaly.org_id      == self.org_id,
            LoginAnomaly.occurred_at >= since,
        )
        if unresolved_only:
            q = q.filter(LoginAnomaly.is_resolved == False)
        q = q.order_by(LoginAnomaly.occurred_at.desc()).limit(100)

        return [
            {
                "id":           a.id,
                "user_id":      a.user_id,
                "anomaly_type": a.anomaly_type,
                "severity":     a.severity,
                "ip_address":   a.ip_address,
                "country":      a.country,
                "detail":       a.detail,
                "occurred_at":  a.occurred_at.isoformat(),
                "is_resolved":  a.is_resolved,
            }
            for a in q.all()
        ]

    def mttd_mttr_trend(self, days: int = 30, p=None) -> List[Dict[str, Any]]:
        """Daily MTTD/MTTR trend data for KPI sparklines.

        Con ``p``: tramos de ``p.granularidad`` (por fecha de resolucion), todos
        los tramos del periodo (los vacios con 0 detecciones); cada punto lleva
        ``t``, ``clave`` y ``date`` (dia del tramo, compatibilidad).
        """
        resolved = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            *_ventana(SecurityDetection.resolved_at, p, days=days),
            SecurityDetection.resolved_at.isnot(None),
        ).all()

        daily: Dict[str, Dict] = {}
        for d in resolved:
            day_key = p.clave(d.resolved_at) if p is not None else d.resolved_at.date().isoformat()
            if day_key not in daily:
                daily[day_key] = {"date": day_key, "mttd_sum": 0, "mttr_sum": 0, "count": 0}
            if d.first_seen_at and d.detected_at:
                daily[day_key]["mttd_sum"] += (d.detected_at - d.first_seen_at).total_seconds()
            if d.detected_at and d.resolved_at:
                daily[day_key]["mttr_sum"] += (d.resolved_at - d.detected_at).total_seconds()
            daily[day_key]["count"] += 1

        result = []
        for v in sorted(daily.values(), key=lambda x: x["date"]):
            n = max(v["count"], 1)
            result.append({
                "date":             v["date"],
                "avg_mttd_seconds": round(v["mttd_sum"] / n, 1),
                "avg_mttr_seconds": round(v["mttr_sum"] / n, 1),
                "detections":       v["count"],
            })
        if p is None:
            return result
        por_clave = {r.pop("date"): r for r in result}
        serie = p.rellenar(por_clave, vacio={"avg_mttd_seconds": 0.0, "avg_mttr_seconds": 0.0, "detections": 0})
        for punto in serie:
            punto["date"] = punto["clave"][:10]
        return serie

    def auth_failure_heatmap(self, days: int = 7, p=None) -> List[Dict[str, Any]]:
        """Hourly failed-login heat for the geo/time heatmap widget.

        Con ``p``: tramos de ``p.granularidad`` en la zona del periodo y ``ts``
        es el inicio del tramo en ISO con desfase (solo tramos con datos: es un
        mapa de calor por pais, no una serie).
        """
        rows = self.db.query(
            SecurityEvent.occurred_at,
            SecurityEvent.country,
            SecurityEvent.ip_address,
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            SecurityEvent.event_type   == "login_failed",
            *_ventana(SecurityEvent.occurred_at, p, days=days),
        ).all()

        buckets: Dict[str, Dict] = {}
        for ts, country, ip in rows:
            day_hour = p.instante_de_clave(p.clave(ts)) if p is not None else ts.strftime("%Y-%m-%dT%H:00:00")
            key = f"{day_hour}|{country or 'unknown'}"
            if key not in buckets:
                buckets[key] = {"ts": day_hour, "country": country or "unknown", "count": 0, "unique_ips": set()}
            buckets[key]["count"] += 1
            if ip:
                buckets[key]["unique_ips"].add(ip)

        return [
            {
                "ts": v["ts"],
                "country": v["country"],
                "count": v["count"],
                "unique_ips": len(v["unique_ips"]),
            }
            for v in sorted(buckets.values(), key=lambda x: x["ts"])
        ]

    def top_offending_ips(self, hours: int = 24, limit: int = 20, p=None) -> List[Dict[str, Any]]:
        """IPs with most security events — for threat intel pivot."""
        rows = self.db.query(
            SecurityEvent.ip_address,
            SecurityEvent.country,
            SecurityEvent.asn,
            SecurityEvent.is_vpn,
            SecurityEvent.is_tor,
            func.count(SecurityEvent.id).label("total"),
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            *_ventana(SecurityEvent.occurred_at, p, hours=hours),
            SecurityEvent.ip_address.isnot(None),
        ).group_by(
            SecurityEvent.ip_address,
            SecurityEvent.country,
            SecurityEvent.asn,
            SecurityEvent.is_vpn,
            SecurityEvent.is_tor,
        ).order_by(text("total DESC")).limit(limit).all()

        return [
            {
                "ip_address": r.ip_address,
                "country":    r.country,
                "asn":        r.asn,
                "is_vpn":     r.is_vpn,
                "is_tor":     r.is_tor,
                "total_events": r.total,
            }
            for r in rows
        ]

    # helper calculations
    def list_events_paginated(
        self,
        since: datetime,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        until: Optional[datetime] = None,
    ) -> Tuple[int, List[SecurityEvent]]:
        q = self.db.query(SecurityEvent).filter(
            SecurityEvent.org_id      == self.org_id,
            *_ventana(SecurityEvent.occurred_at, None, since=since, until=until),
        )
        if category:   q = q.filter(SecurityEvent.category   == category)
        if severity:   q = q.filter(SecurityEvent.severity   == severity)
        if event_type: q = q.filter(SecurityEvent.event_type == event_type)
        if user_id:    q = q.filter(SecurityEvent.user_id    == user_id)
        if ip_address: q = q.filter(SecurityEvent.ip_address == ip_address)
        total = q.count()
        items = q.order_by(SecurityEvent.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return total, items

    def list_detections_paginated(
        self,
        since: datetime,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        until: Optional[datetime] = None,
    ) -> Tuple[int, List[SecurityDetection]]:
        q = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            *_ventana(SecurityDetection.detected_at, None, since=since, until=until),
        )
        if status:   q = q.filter(SecurityDetection.status   == status)
        if severity: q = q.filter(SecurityDetection.severity == severity)
        total = q.count()
        items = q.order_by(SecurityDetection.detected_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return total, items

    def list_incidents_paginated(
        self,
        since: datetime,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        until: Optional[datetime] = None,
    ) -> Tuple[int, List[SecurityIncident]]:
        q = self.db.query(SecurityIncident).filter(
            SecurityIncident.org_id     == self.org_id,
            *_ventana(SecurityIncident.started_at, None, since=since, until=until),
        )
        if status_filter:
            q = q.filter(SecurityIncident.status == status_filter)
        total = q.count()
        items = q.order_by(SecurityIncident.started_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return total, items

    def list_login_anomalies_paginated(
        self,
        since: datetime,
        anomaly_type: Optional[str] = None,
        severity: Optional[str] = None,
        unresolved_only: bool = True,
        page: int = 1,
        page_size: int = 50,
        until: Optional[datetime] = None,
    ) -> Tuple[int, List[LoginAnomaly]]:
        q = self.db.query(LoginAnomaly).filter(
            LoginAnomaly.org_id      == self.org_id,
            *_ventana(LoginAnomaly.occurred_at, None, since=since, until=until),
        )
        if unresolved_only: q = q.filter(LoginAnomaly.is_resolved == False)
        if anomaly_type:    q = q.filter(LoginAnomaly.anomaly_type == anomaly_type)
        if severity:        q = q.filter(LoginAnomaly.severity     == severity)
        total = q.count()
        items = q.order_by(LoginAnomaly.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return total, items

    # helper calculations
    def _avg_mttd(self, days: int = 30) -> Optional[float]:
        since = _utcnow() - timedelta(days=days)
        rows = self.db.query(
            SecurityDetection.first_seen_at,
            SecurityDetection.detected_at,
        ).filter(
            SecurityDetection.org_id      == self.org_id,
            SecurityDetection.detected_at >= since,
            SecurityDetection.first_seen_at.isnot(None),
        ).all()
        if not rows:
            return None
        vals = [(d - f).total_seconds() for f, d in rows if f and d and d >= f]
        return round(sum(vals) / len(vals), 1) if vals else None

    def _avg_mttr(self, days: int = 30) -> Optional[float]:
        since = _utcnow() - timedelta(days=days)
        rows = self.db.query(
            SecurityDetection.detected_at,
            SecurityDetection.resolved_at,
        ).filter(
            SecurityDetection.org_id      == self.org_id,
            SecurityDetection.resolved_at >= since,
            SecurityDetection.resolved_at.isnot(None),
            SecurityDetection.detected_at.isnot(None),
        ).all()
        if not rows:
            return None
        vals = [(r - d).total_seconds() for d, r in rows if d and r and r >= d]
        return round(sum(vals) / len(vals), 1) if vals else None
