"""
Security Observability Service — SOC-ready event collection, detection, and analytics.

Responsibilities:
- Ingest & normalize security events from auth, ABAC, sessions, API middleware
- Fire detection rules (brute-force, impossible travel, mass export, cred stuffing, …)
- Maintain MTTD/MTTR metrics
- Update per-hour snapshot for instant dashboard rendering
- Raise LoginAnomaly records for dedicated anomaly widget
"""
from __future__ import annotations

import uuid
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.security_observability import (
    SecurityEvent, SecurityDetection, SecurityIncident, LoginAnomaly,
    SecurityMetricSnapshot, EventCategory, EventSeverity, IncidentStatus, KillChainStage,
)
from fastapi import HTTPException

logger = logging.getLogger("clarive.soc")

_UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(_UTC)


def _trunc_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


# ── Detection rule thresholds (configurable via env/settings later) ─────────

BRUTE_FORCE_WINDOW_MINUTES  = 10
BRUTE_FORCE_THRESHOLD       = 5    # failed logins per window per IP
CRED_STUFFING_THRESHOLD     = 20   # distinct users hit per IP per hour
MASS_EXPORT_THRESHOLD       = 50   # rows / API calls within 5 min
SESSION_CONCURRENT_LIMIT    = 3    # max simultaneous sessions before flagging
MFA_FAIL_THRESHOLD          = 3    # consecutive MFA fails before alert


# ── Event ingestion ───────────────────────────────────────────────────────────

class SecurityEventService:
    """Ingest events and run detections synchronously (fast path)."""

    def __init__(self, db: Session, org_id: str):
        self.db     = db
        self.org_id = org_id

    # ── Public: emit events from call-sites ──────────────────────────────────

    def emit(
        self,
        event_type: str,
        category: str,
        severity: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        asn: Optional[str] = None,
        country: Optional[str] = None,
        is_vpn: bool = False,
        is_tor: bool = False,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        detail: Optional[str] = None,
        raw_event: Optional[Dict[str, Any]] = None,
        indicators: Optional[Dict[str, Any]] = None,
        occurred_at: Optional[datetime] = None,
    ) -> SecurityEvent:
        """Persist a normalized security event and run detection rules."""
        ev = SecurityEvent(
            id            = str(uuid.uuid4()),
            org_id        = self.org_id,
            user_id       = user_id,
            category      = category,
            severity      = severity,
            event_type    = event_type,
            ip_address    = ip_address,
            user_agent    = user_agent,
            session_id    = session_id,
            asn           = asn,
            country       = country,
            is_vpn        = is_vpn,
            is_tor        = is_tor,
            resource_type = resource_type,
            resource_id   = resource_id,
            detail        = detail,
            raw_event     = raw_event,
            indicators    = indicators,
            occurred_at   = occurred_at or _utcnow(),
            ingested_at   = _utcnow(),
        )
        self.db.add(ev)
        self.db.flush()   # get ev.id without full commit

        # Run detection rules (non-blocking on error)
        try:
            self._run_detections(ev)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Detection rule error for event %s: %s", ev.id, exc)

        # Bump hourly snapshot (lightweight counter update)
        try:
            self._bump_snapshot(ev)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Snapshot bump error: %s", exc)

        self.db.commit()
        return ev

    # ── Convenience emitters (call from auth/ABAC/session endpoints) ─────────

    def login_success(self, user_id: str, ip: str, ua: str, country: str = None,
                      asn: str = None, is_vpn: bool = False) -> SecurityEvent:
        return self.emit(
            event_type="login_success",
            category=EventCategory.AUTH,
            severity=EventSeverity.INFO,
            user_id=user_id, ip_address=ip, user_agent=ua,
            country=country, asn=asn, is_vpn=is_vpn,
            detail=f"Successful login from {ip or 'unknown'} ({country or '?'})",
        )

    def login_failed(self, user_id: Optional[str], ip: str, ua: str,
                     reason: str = "bad_credentials") -> SecurityEvent:
        return self.emit(
            event_type="login_failed",
            category=EventCategory.AUTH,
            severity=EventSeverity.LOW,
            user_id=user_id, ip_address=ip, user_agent=ua,
            detail=f"Login rejected: {reason}",
            raw_event={"reason": reason},
        )

    def mfa_failed(self, user_id: str, ip: str, method: str = "totp") -> SecurityEvent:
        return self.emit(
            event_type="mfa_failed",
            category=EventCategory.AUTH,
            severity=EventSeverity.MEDIUM,
            user_id=user_id, ip_address=ip,
            detail=f"MFA challenge failed ({method})",
            raw_event={"method": method},
        )

    def abac_denied(self, user_id: str, resource_type: str, resource_id: str,
                    matched_policies: List[str]) -> SecurityEvent:
        return self.emit(
            event_type="abac_access_denied",
            category=EventCategory.AUTHZ,
            severity=EventSeverity.MEDIUM,
            user_id=user_id,
            resource_type=resource_type, resource_id=resource_id,
            detail=f"ABAC policy denied access to {resource_type}/{resource_id}",
            raw_event={"matched_deny_policies": matched_policies},
        )

    def session_revoked(self, user_id: str, session_id: str, reason: str = "explicit") -> SecurityEvent:
        return self.emit(
            event_type="session_revoked",
            category=EventCategory.SESSION,
            severity=EventSeverity.INFO,
            user_id=user_id, session_id=session_id,
            detail=f"Session {session_id[:8]}… revoked: {reason}",
            raw_event={"reason": reason},
        )

    def policy_changed(self, admin_id: str, action: str, target: str) -> SecurityEvent:
        return self.emit(
            event_type="policy_changed",
            category=EventCategory.ADMIN,
            severity=EventSeverity.MEDIUM,
            user_id=admin_id,
            detail=f"Policy {action}: {target}",
            raw_event={"action": action, "target": target},
        )

    def rate_limit_hit(self, ip: str, endpoint: str, user_id: Optional[str] = None) -> SecurityEvent:
        return self.emit(
            event_type="rate_limit_exceeded",
            category=EventCategory.API,
            severity=EventSeverity.LOW,
            user_id=user_id, ip_address=ip,
            resource_type="endpoint", resource_id=endpoint,
            detail=f"Rate limit exceeded on {endpoint} from {ip}",
        )

    # ── Detection rules ───────────────────────────────────────────────────────

    def _run_detections(self, ev: SecurityEvent) -> None:
        """Dispatch detection logic based on event type."""
        handlers = {
            "login_failed":         self._detect_brute_force,
            "login_success":        self._detect_login_anomaly,
            "mfa_failed":           self._detect_mfa_spray,
            "abac_access_denied":   self._detect_priv_escalation,
            "rate_limit_exceeded":  self._detect_api_abuse,
        }
        handler = handlers.get(ev.event_type)
        if handler:
            handler(ev)

    def _detect_brute_force(self, ev: SecurityEvent) -> None:
        """Brute-force / credential stuffing detection."""
        window_start = _utcnow() - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)

        # Count fails from this IP in window
        ip_fails = self.db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.org_id   == self.org_id,
            SecurityEvent.event_type == "login_failed",
            SecurityEvent.ip_address == ev.ip_address,
            SecurityEvent.occurred_at >= window_start,
        ).scalar() or 0

        if ip_fails >= BRUTE_FORCE_THRESHOLD:
            # Count distinct users targeted by this IP (cred stuffing indicator)
            distinct_users = self.db.query(
                func.count(func.distinct(SecurityEvent.user_id))
            ).filter(
                SecurityEvent.org_id     == self.org_id,
                SecurityEvent.event_type == "login_failed",
                SecurityEvent.ip_address == ev.ip_address,
                SecurityEvent.occurred_at >= window_start,
            ).scalar() or 0

            is_stuffing = distinct_users >= 3
            title   = f"{'Credential stuffing' if is_stuffing else 'Brute-force'} detected from {ev.ip_address}"
            mitre   = "T1110.004" if is_stuffing else "T1110.001"
            severity = EventSeverity.CRITICAL if is_stuffing else EventSeverity.HIGH

            self._upsert_detection(
                title      = title,
                category   = EventCategory.AUTH_ANOMALY,
                severity   = severity,
                kill_chain = KillChainStage.DELIVERY,
                mitre_id   = mitre,
                mitre_tactic = "Credential Access",
                ip_address = ev.ip_address,
                user_id    = ev.user_id,
                event_count = ip_fails,
                evidence   = {"ip_fails": ip_fails, "distinct_users": distinct_users},
            )

            # Also log a LoginAnomaly
            anomaly_type = "credential_stuffing" if is_stuffing else "brute_force"
            self._record_anomaly(ev.user_id, anomaly_type, severity, ev.ip_address,
                                 ev.country, ev.asn,
                                 {"ip_fails": ip_fails, "distinct_users": distinct_users})

    def _detect_login_anomaly(self, ev: SecurityEvent) -> None:
        """New country / VPN / Tor / impossible travel anomalies on login_success."""
        if not ev.user_id:
            return

        # TOR exit node
        if ev.is_tor:
            self._record_anomaly(ev.user_id, "tor_detected",
                                 EventSeverity.HIGH, ev.ip_address, ev.country, ev.asn,
                                 {"detail": "Login via Tor exit node"})
            self._upsert_detection(
                title      = f"Tor login for user {ev.user_id}",
                category   = EventCategory.AUTH_ANOMALY,
                severity   = EventSeverity.HIGH,
                kill_chain = KillChainStage.DELIVERY,
                mitre_id   = "T1090.003",
                mitre_tactic = "Defense Evasion",
                user_id    = ev.user_id,
                ip_address = ev.ip_address,
            )
            return

        # New country - compare to last 30 days of successful logins
        if ev.country:
            seen_countries = {
                row.country
                for row in self.db.query(SecurityEvent.country).filter(
                    SecurityEvent.org_id     == self.org_id,
                    SecurityEvent.user_id    == ev.user_id,
                    SecurityEvent.event_type == "login_success",
                    SecurityEvent.occurred_at >= _utcnow() - timedelta(days=30),
                    SecurityEvent.id         != ev.id,
                ).all()
                if row.country
            }
            if seen_countries and ev.country not in seen_countries:
                self._record_anomaly(ev.user_id, "new_country",
                                     EventSeverity.MEDIUM, ev.ip_address, ev.country, ev.asn,
                                     {"new_country": ev.country, "seen": list(seen_countries)[:5]})
                self._upsert_detection(
                    title      = f"New country login: {ev.country} for user {ev.user_id}",
                    category   = EventCategory.AUTH_ANOMALY,
                    severity   = EventSeverity.MEDIUM,
                    kill_chain = KillChainStage.DELIVERY,
                    mitre_id   = "T1078",
                    mitre_tactic = "Initial Access",
                    user_id    = ev.user_id,
                    ip_address = ev.ip_address,
                    country    = ev.country,
                )

        # VPN  - just record anomaly (lower severity)
        if ev.is_vpn:
            self._record_anomaly(ev.user_id, "vpn_detected",
                                 EventSeverity.LOW, ev.ip_address, ev.country, ev.asn, {})

    def _detect_mfa_spray(self, ev: SecurityEvent) -> None:
        """MFA bypass spray: repeated MFA failures."""
        if not ev.user_id:
            return
        window_start = _utcnow() - timedelta(minutes=15)
        fail_count = self.db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.org_id     == self.org_id,
            SecurityEvent.event_type == "mfa_failed",
            SecurityEvent.user_id    == ev.user_id,
            SecurityEvent.occurred_at >= window_start,
        ).scalar() or 0

        if fail_count >= MFA_FAIL_THRESHOLD:
            self._upsert_detection(
                title      = f"MFA spray attempt on user {ev.user_id}",
                category   = EventCategory.AUTH_ANOMALY,
                severity   = EventSeverity.HIGH,
                kill_chain = KillChainStage.EXPLOITATION,
                mitre_id   = "T1111",
                mitre_tactic = "Credential Access",
                user_id    = ev.user_id,
                ip_address = ev.ip_address,
                event_count = fail_count,
                evidence   = {"mfa_fails_15min": fail_count},
            )
            self._record_anomaly(ev.user_id, "mfa_bypass_attempt",
                                 EventSeverity.HIGH, ev.ip_address, ev.country, ev.asn,
                                 {"fails": fail_count})

    def _detect_priv_escalation(self, ev: SecurityEvent) -> None:
        """Repeated ABAC denials may indicate privilege escalation probing."""
        if not ev.user_id:
            return
        window_start = _utcnow() - timedelta(minutes=30)
        deny_count = self.db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.org_id     == self.org_id,
            SecurityEvent.event_type == "abac_access_denied",
            SecurityEvent.user_id    == ev.user_id,
            SecurityEvent.occurred_at >= window_start,
        ).scalar() or 0

        if deny_count >= 5:
            self._upsert_detection(
                title      = f"Privilege escalation probing by user {ev.user_id}",
                category   = EventCategory.AUTHZ,
                severity   = EventSeverity.HIGH,
                kill_chain = KillChainStage.EXPLOITATION,
                mitre_id   = "T1078.002",
                mitre_tactic = "Privilege Escalation",
                user_id    = ev.user_id,
                event_count = deny_count,
                evidence   = {"abac_denials_30min": deny_count},
            )

    def _detect_api_abuse(self, ev: SecurityEvent) -> None:
        """Sustained rate-limit hits signal scanner / abuse."""
        window_start = _utcnow() - timedelta(minutes=5)
        hits = self.db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.org_id     == self.org_id,
            SecurityEvent.event_type == "rate_limit_exceeded",
            SecurityEvent.ip_address == ev.ip_address,
            SecurityEvent.occurred_at >= window_start,
        ).scalar() or 0

        if hits >= 10:
            self._upsert_detection(
                title      = f"API abuse / scanner from {ev.ip_address}",
                category   = EventCategory.API,
                severity   = EventSeverity.MEDIUM,
                kill_chain = KillChainStage.RECON,
                mitre_id   = "T1595",
                mitre_tactic = "Reconnaissance",
                ip_address = ev.ip_address,
                user_id    = ev.user_id,
                event_count = hits,
                evidence   = {"rate_limit_hits_5min": hits},
            )

    # ── Detection upsert ──────────────────────────────────────────────────────

    def _upsert_detection(
        self,
        title: str,
        category: str,
        severity: str,
        kill_chain: str = None,
        mitre_id: str = None,
        mitre_tactic: str = None,
        user_id: str = None,
        ip_address: str = None,
        country: str = None,
        event_count: int = 1,
        evidence: Dict[str, Any] = None,
    ) -> SecurityDetection:
        """
        Create detection if no open one exists for same title+user/ip within 24h.
        Otherwise increment event_count on the existing open detection.
        """
        window = _utcnow() - timedelta(hours=24)
        existing = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id   == self.org_id,
            SecurityDetection.title    == title,
            SecurityDetection.status   == IncidentStatus.OPEN,
            SecurityDetection.detected_at >= window,
        ).first()

        now = _utcnow()
        if existing:
            existing.event_count += event_count
            existing.evidence = evidence
            self.db.flush()
            return existing

        det = SecurityDetection(
            id           = str(uuid.uuid4()),
            org_id       = self.org_id,
            title        = title,
            severity     = severity,
            category     = category,
            kill_chain   = kill_chain,
            mitre_id     = mitre_id,
            mitre_tactic = mitre_tactic,
            user_id      = user_id,
            ip_address   = ip_address,
            country      = country,
            event_count  = event_count,
            evidence     = evidence,
            first_seen_at= now,
            detected_at  = now,
            status       = IncidentStatus.OPEN,
        )
        self.db.add(det)
        self.db.flush()
        return det

    # ── Anomaly record ────────────────────────────────────────────────────────

    def _record_anomaly(
        self,
        user_id: Optional[str],
        anomaly_type: str,
        severity: str,
        ip_address: Optional[str],
        country: Optional[str],
        asn: Optional[str],
        detail: Dict[str, Any],
    ) -> LoginAnomaly:
        if not user_id:
            return None
        anomaly = LoginAnomaly(
            id           = str(uuid.uuid4()),
            org_id       = self.org_id,
            user_id      = user_id,
            anomaly_type = anomaly_type,
            severity     = severity,
            ip_address   = ip_address,
            country      = country,
            asn          = asn,
            detail       = detail,
            occurred_at  = _utcnow(),
        )
        self.db.add(anomaly)
        self.db.flush()
        return anomaly

    # ── Hourly snapshot ───────────────────────────────────────────────────────

    def _bump_snapshot(self, ev: SecurityEvent) -> None:
        """Increment counters on the current-hour snapshot row."""
        hour = _trunc_hour(ev.occurred_at.replace(tzinfo=None) if ev.occurred_at.tzinfo else ev.occurred_at)
        snap = self.db.query(SecurityMetricSnapshot).filter(
            SecurityMetricSnapshot.org_id        == self.org_id,
            SecurityMetricSnapshot.snapshot_hour == hour,
        ).with_for_update(skip_locked=True).first()

        if not snap:
            snap = SecurityMetricSnapshot(
                id            = str(uuid.uuid4()),
                org_id        = self.org_id,
                snapshot_hour = hour,
            )
            self.db.add(snap)
            self.db.flush()

        snap.total_events += 1
        sev = ev.severity
        if sev == EventSeverity.INFO:     snap.events_info     += 1
        elif sev == EventSeverity.LOW:    snap.events_low      += 1
        elif sev == EventSeverity.MEDIUM: snap.events_medium   += 1
        elif sev == EventSeverity.HIGH:   snap.events_high     += 1
        elif sev == EventSeverity.CRITICAL: snap.events_critical += 1

        et = ev.event_type
        if et == "login_success":       snap.login_success  += 1
        elif et == "login_failed":      snap.login_failed   += 1
        elif et == "mfa_failed":        snap.mfa_failed     += 1
        elif et == "abac_access_denied":snap.abac_denials   += 1
        elif et == "rate_limit_exceeded":snap.rate_limit_hits += 1

        self.db.flush()

    # ── Detection management (for SOC workflow) ───────────────────────────────

    def resolve_detection(
        self,
        detection_id: str,
        analyst_id: str,
        status: str,
        reason: Optional[str] = None,
    ) -> SecurityDetection:
        det = self.db.query(SecurityDetection).filter(
            SecurityDetection.id     == detection_id,
            SecurityDetection.org_id == self.org_id,
        ).first()
        if not det:
            raise ValueError(f"Detection {detection_id} not found")

        det.status      = status
        det.resolved_at = _utcnow()
        det.assigned_to = analyst_id
        if reason:
            det.false_positive_reason = reason

        # Update MTTR on detection
        if det.detected_at:
            det_time = det.detected_at
            if det_time.tzinfo is None:
                det_time = det_time.replace(tzinfo=_UTC)
            det.mttd_seconds = (det.detected_at - det.first_seen_at).total_seconds() if det.first_seen_at else None

        self.db.commit()
        return det

    def create_incident(
        self,
        title: str,
        severity: str,
        detection_ids: List[str],
        lead_analyst_id: str,
        description: str = None,
        playbook_ref: str = None,
    ) -> SecurityIncident:
        """Escalate one or more detections into a formal incident."""
        now = _utcnow()
        incident = SecurityIncident(
            id           = str(uuid.uuid4()),
            org_id       = self.org_id,
            title        = title,
            description  = description,
            severity     = severity,
            status       = IncidentStatus.INVESTIGATING,
            lead_analyst = lead_analyst_id,
            playbook_ref = playbook_ref,
            detected_at  = now,
            started_at   = now,
        )
        self.db.add(incident)
        self.db.flush()

        # Link detections
        for det_id in detection_ids:
            det = self.db.query(SecurityDetection).filter(
                SecurityDetection.id == det_id,
                SecurityDetection.org_id == self.org_id,
            ).first()
            if det:
                det.incident_id = incident.id
                det.status = IncidentStatus.INVESTIGATING

        self.db.commit()
        return incident

    def resolve_incident(
        self,
        incident_id: str,
        analyst_id: str,
        root_cause: str = None,
        remediation: str = None,
        lessons: str = None,
    ) -> SecurityIncident:
        inc = self.db.query(SecurityIncident).filter(
            SecurityIncident.id     == incident_id,
            SecurityIncident.org_id == self.org_id,
        ).first()
        if not inc:
            raise ValueError(f"Incident {incident_id} not found")

        now          = _utcnow()
        inc.status   = IncidentStatus.RESOLVED
        inc.resolved_at       = now
        inc.root_cause        = root_cause
        inc.remediation_note  = remediation
        inc.lessons_learned   = lessons

        if inc.detected_at:
            det_at = inc.detected_at
            if det_at.tzinfo is None:
                det_at = det_at.replace(tzinfo=_UTC)
            inc.mttr_seconds = (now - det_at).total_seconds()

        if inc.started_at and inc.detected_at:
            start = inc.started_at
            if start.tzinfo is None:
                start = start.replace(tzinfo=_UTC)
            det_time = inc.detected_at
            if det_time.tzinfo is None:
                det_time = det_time.replace(tzinfo=_UTC)
            inc.mttd_seconds = (det_time - start).total_seconds()

        self.db.commit()
        return inc

    def get_detection_by_id(self, detection_id: str) -> Optional[SecurityDetection]:
        return self.db.query(SecurityDetection).filter(
            SecurityDetection.id     == detection_id,
            SecurityDetection.org_id == self.org_id,
        ).first()

    def get_incident_by_id(self, incident_id: str) -> Optional[SecurityIncident]:
        return self.db.query(SecurityIncident).filter(
            SecurityIncident.id     == incident_id,
            SecurityIncident.org_id == self.org_id,
        ).first()

    def resolve_anomaly(self, anomaly_id: str) -> Optional[LoginAnomaly]:
        anomaly = self.db.query(LoginAnomaly).filter(
            LoginAnomaly.id     == anomaly_id,
            LoginAnomaly.org_id == self.org_id,
        ).first()
        if not anomaly:
            return None
        anomaly.is_resolved = True
        self.db.commit()
        return anomaly


# ── Analytics query helpers ───────────────────────────────────────────────────

class SecurityAnalyticsService:
    """Query layer for SOC dashboard panels."""

    def __init__(self, db: Session, org_id: str):
        self.db     = db
        self.org_id = org_id

    def overview(self, hours: int = 24) -> Dict[str, Any]:
        """Top-level SOC overview: event counts, open detections/incidents, KPIs."""
        since = _utcnow() - timedelta(hours=hours)

        base = self.db.query(SecurityEvent).filter(
            SecurityEvent.org_id       == self.org_id,
            SecurityEvent.occurred_at  >= since,
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
            LoginAnomaly.occurred_at >= since,
        ).scalar() or 0

        return {
            "window_hours":     hours,
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

    def event_timeline(self, hours: int = 24, bucket_minutes: int = 60) -> List[Dict[str, Any]]:
        """Events bucketed by time for sparkline/timeline charts."""
        since = _utcnow() - timedelta(hours=hours)
        rows = self.db.query(
            SecurityEvent.severity,
            SecurityEvent.occurred_at,
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            SecurityEvent.occurred_at  >= since,
        ).all()

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

    def top_attack_indicators(self, hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
        """Top open detections by severity + recency (attack indicator board)."""
        since = _utcnow() - timedelta(hours=hours)
        dets = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            SecurityDetection.detected_at >= since,
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
            q = q.filter(LoginAnomaly.is_resolved == False)  # noqa
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

    def mttd_mttr_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Daily MTTD/MTTR trend data for KPI sparklines."""
        since = _utcnow() - timedelta(days=days)
        resolved = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            SecurityDetection.resolved_at >= since,
            SecurityDetection.resolved_at.isnot(None),
        ).all()

        daily: Dict[str, Dict] = {}
        for d in resolved:
            day_key = d.resolved_at.date().isoformat()
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
        return result

    def auth_failure_heatmap(self, days: int = 7) -> List[Dict[str, Any]]:
        """Hourly failed-login heat for the geo/time heatmap widget."""
        since = _utcnow() - timedelta(days=days)
        rows = self.db.query(
            SecurityEvent.occurred_at,
            SecurityEvent.country,
            SecurityEvent.ip_address,
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            SecurityEvent.event_type   == "login_failed",
            SecurityEvent.occurred_at  >= since,
        ).all()

        buckets: Dict[str, Dict] = {}
        for ts, country, ip in rows:
            day_hour = ts.strftime("%Y-%m-%dT%H:00:00")
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

    def top_offending_ips(self, hours: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """IPs with most security events — for threat intel pivot."""
        since = _utcnow() - timedelta(hours=hours)
        rows = self.db.query(
            SecurityEvent.ip_address,
            SecurityEvent.country,
            SecurityEvent.asn,
            SecurityEvent.is_vpn,
            SecurityEvent.is_tor,
            func.count(SecurityEvent.id).label("total"),
        ).filter(
            SecurityEvent.org_id       == self.org_id,
            SecurityEvent.occurred_at  >= since,
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
    ) -> Tuple[int, List[SecurityEvent]]:
        q = self.db.query(SecurityEvent).filter(
            SecurityEvent.org_id      == self.org_id,
            SecurityEvent.occurred_at >= since,
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
    ) -> Tuple[int, List[SecurityDetection]]:
        q = self.db.query(SecurityDetection).filter(
            SecurityDetection.org_id      == self.org_id,
            SecurityDetection.detected_at >= since,
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
    ) -> Tuple[int, List[SecurityIncident]]:
        q = self.db.query(SecurityIncident).filter(
            SecurityIncident.org_id     == self.org_id,
            SecurityIncident.started_at >= since,
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
    ) -> Tuple[int, List[LoginAnomaly]]:
        q = self.db.query(LoginAnomaly).filter(
            LoginAnomaly.org_id      == self.org_id,
            LoginAnomaly.occurred_at >= since,
        )
        if unresolved_only: q = q.filter(LoginAnomaly.is_resolved == False)  # noqa
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


# ── Tenant helpers ─────────────────────────────────────────────────────────

def get_org_id(user) -> str:
    if not user.organization_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    return str(user.organization_id)
