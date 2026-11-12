"""Registro y deteccion de eventos de seguridad (fuerza bruta, MFA, exportaciones, sesiones).

Parte de `app.services.security_observability` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.security_observability import (
    SecurityEvent, SecurityDetection, SecurityIncident, LoginAnomaly,
    SecurityMetricSnapshot, EventCategory, EventSeverity, IncidentStatus, KillChainStage,
)

from app.services.security_observability._comun import _UTC, _utcnow, logger


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

# ── Contadores de la instantanea horaria ─────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). Esto eran dos cadenas de `elif` dentro de
# `_bump_snapshot`, cinco ramas cada una, que hacian lo mismo cinco veces:
# elegir un contador y sumarle uno. Medido con un barrido por AST sobre las 81
# funciones que quedaban por encima del umbral, **era la ultima que escondia una
# tabla de despacho**; las otras 80 son largas pero lineales.
#
# Un severidad o un tipo de evento que no este en su tabla **no suma nada y no
# falla**, que es lo que hacia la cadena de `elif` sin `else`. Se conserva a
# proposito: el contador total (`total_events`) sigue subiendo, asi que un tipo
# nuevo aparece en el total aunque todavia no tenga columna propia — y eso es
# preferible a que registrar un evento reviente por un enumerado nuevo.

_CONTADOR_POR_SEVERIDAD = {
    EventSeverity.INFO:     "events_info",
    EventSeverity.LOW:      "events_low",
    EventSeverity.MEDIUM:   "events_medium",
    EventSeverity.HIGH:     "events_high",
    EventSeverity.CRITICAL: "events_critical",
}

# La clave es el `event_type` tal cual se guarda; el valor, el nombre de la
# columna. No coinciden en tres de los cinco (`abac_access_denied` cuenta en
# `abac_denials`), asi que la tabla no es reducible a una regla de nombres.
_CONTADOR_POR_TIPO = {
    "login_success":       "login_success",
    "login_failed":        "login_failed",
    "mfa_failed":          "mfa_failed",
    "abac_access_denied":  "abac_denials",
    "rate_limit_exceeded": "rate_limit_hits",
}


def _sumar_uno(fila, campo) -> None:
    """Incrementa un contador de la instantanea, o no hace nada si no hay."""
    if campo:
        setattr(fila, campo, getattr(fila, campo) + 1)


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
        except Exception as exc:
            logger.warning("Detection rule error for event %s: %s", ev.id, exc)

        # Bump hourly snapshot (lightweight counter update)
        try:
            self._bump_snapshot(ev)
        except Exception as exc:
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
        _sumar_uno(snap, _CONTADOR_POR_SEVERIDAD.get(ev.severity))
        _sumar_uno(snap, _CONTADOR_POR_TIPO.get(ev.event_type))

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

        # Auditoria 2026-08: aqui se calculaba el tiempo hasta la deteccion y
        # se asignaba a `det.mttd_seconds`, una columna que **no existe** en
        # `security_detections`. Es una **asignacion**, asi que SQLAlchemy no se
        # queja: se quedaba un atributo de Python que no persiste, y el calculo
        # se tiraba a la basura en cada resolucion.
        #
        # **No se inventa la columna.** El dato es derivable en cualquier
        # momento de `detected_at - first_seen_at`, que ya se guardan las dos,
        # asi que anadir una columna seria duplicar informacion. Lo que si hacia
        # falta era dejar de fingir que se guarda: el bloque entero, y con el la
        # normalizacion de zona horaria que solo servia para esto, se quitan.
        #
        # Si el tiempo hasta la deteccion hace falta en una consulta, se calcula
        # en la lectura; anadir la columna es una decision de producto.

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
