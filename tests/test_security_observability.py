"""
Security Observability tests.

Covers:
- SecurityEventService: emit, convenience emitters, detection rule triggers
- SecurityAnalyticsService: overview, timelines, anomaly feed, MTTD/MTTR
- Security incident workflow: create, escalate, resolve
- SOC API endpoints (smoke tests)
"""
import time
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.mfa import Organization
from app.models.security_observability import (
    SecurityDetection, LoginAnomaly,
    EventCategory, EventSeverity, IncidentStatus, KillChainStage,
)
from app.services.security_observability import (
    SecurityEventService, SecurityAnalyticsService,
)

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def soc_org(db: Session) -> Organization:
    uid = str(int(time.time() * 1000))
    org = Organization(id=f"soc-org-{uid}", name="SOC Test", slug=f"soc-{uid}")
    db.add(org)
    db.commit()
    return org


@pytest.fixture
def soc_user(db: Session, soc_org: Organization) -> User:
    uid = str(int(time.time() * 1000))
    user = User(
        id              = f"soc-user-{uid}",
        email           = f"soc-{uid}@example.com",
        hashed_password = "hashed",
        username        = f"soc-{uid}",
        full_name       = "SOC Analyst",
        organization_id = soc_org.id,
        role            = "admin",
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def svc(db: Session, soc_org: Organization) -> SecurityEventService:
    return SecurityEventService(db=db, org_id=soc_org.id)


@pytest.fixture
def analytics(db: Session, soc_org: Organization) -> SecurityAnalyticsService:
    return SecurityAnalyticsService(db=db, org_id=soc_org.id)


# ── Service: basic emit ───────────────────────────────────────────────────────

class TestSecurityEventService:

    def test_emit_stores_event(self, db: Session, svc: SecurityEventService):
        ev = svc.emit(
            event_type = "login_success",
            category   = EventCategory.AUTH,
            severity   = EventSeverity.INFO,
            ip_address = "1.2.3.4",
            country    = "ES",
        )
        assert ev.id is not None
        assert ev.event_type == "login_success"
        assert ev.category == EventCategory.AUTH
        assert ev.severity == EventSeverity.INFO

    def test_emit_login_success(self, db: Session, svc: SecurityEventService, soc_user: User):
        ev = svc.login_success(
            user_id = soc_user.id,
            ip      = "10.0.0.1",
            ua      = "Mozilla/5.0",
            country = "US",
        )
        assert ev.event_type == "login_success"
        assert ev.user_id == soc_user.id

    def test_emit_login_failed(self, db: Session, svc: SecurityEventService):
        ev = svc.login_failed(
            user_id = None,
            ip      = "5.5.5.5",
            ua      = "curl/7.88",
            reason  = "bad_credentials",
        )
        assert ev.event_type == "login_failed"
        assert ev.severity == EventSeverity.LOW

    def test_emit_mfa_failed(self, db: Session, svc: SecurityEventService, soc_user: User):
        ev = svc.mfa_failed(user_id=soc_user.id, ip="8.8.8.8")
        assert ev.event_type == "mfa_failed"
        assert ev.category == EventCategory.AUTH

    def test_emit_abac_denied(self, db: Session, svc: SecurityEventService, soc_user: User):
        ev = svc.abac_denied(
            user_id         = soc_user.id,
            resource_type   = "project",
            resource_id     = "proj-1",
            matched_policies= ["deny-external"],
        )
        assert ev.event_type == "abac_access_denied"
        assert ev.category == EventCategory.AUTHZ

    def test_emit_rate_limit_hit(self, db: Session, svc: SecurityEventService):
        ev = svc.rate_limit_hit(ip="9.9.9.9", endpoint="/api/v1/projects")
        assert ev.event_type == "rate_limit_exceeded"
        assert ev.category == EventCategory.API


# ── Service: detection rules ──────────────────────────────────────────────────

class TestDetectionRules:

    def test_brute_force_detection_triggered(self, db: Session, svc: SecurityEventService):
        """5+ failed logins from same IP triggers brute-force detection."""
        ip = "203.0.113.42"
        for _ in range(6):
            svc.login_failed(user_id=None, ip=ip, ua="attacker")

        det = db.query(SecurityDetection).filter(
            SecurityDetection.org_id   == svc.org_id,
            SecurityDetection.ip_address == ip,
        ).first()
        assert det is not None
        assert det.mitre_id in ("T1110.001", "T1110.004")
        assert det.severity in (EventSeverity.HIGH, EventSeverity.CRITICAL)

    def test_brute_force_increments_existing_detection(self, db: Session, svc: SecurityEventService):
        """Subsequent brute-force events don't duplicate detections."""
        ip = "198.51.100.1"
        for _ in range(10):
            svc.login_failed(user_id=None, ip=ip, ua="attacker")

        dets = db.query(SecurityDetection).filter(
            SecurityDetection.org_id    == svc.org_id,
            SecurityDetection.ip_address == ip,
        ).all()
        assert len(dets) == 1   # upserted, not duplicated

    def test_mfa_spray_detection(self, db: Session, svc: SecurityEventService, soc_user: User):
        """3+ MFA failures on single user triggers detection."""
        for _ in range(4):
            svc.mfa_failed(user_id=soc_user.id, ip="192.0.2.1")

        det = db.query(SecurityDetection).filter(
            SecurityDetection.org_id  == svc.org_id,
            SecurityDetection.user_id == soc_user.id,
            SecurityDetection.mitre_id == "T1111",
        ).first()
        assert det is not None
        assert det.kill_chain == KillChainStage.EXPLOITATION

    def test_tor_login_detection(self, db: Session, svc: SecurityEventService, soc_user: User):
        """Login via Tor exit node creates detection + anomaly."""
        svc.emit(
            event_type = "login_success",
            category   = EventCategory.AUTH,
            severity   = EventSeverity.HIGH,
            user_id    = soc_user.id,
            ip_address = "185.220.101.1",
            is_tor     = True,
        )
        det = db.query(SecurityDetection).filter(
            SecurityDetection.org_id  == svc.org_id,
            SecurityDetection.mitre_id == "T1090.003",
        ).first()
        assert det is not None

        anomaly = db.query(LoginAnomaly).filter(
            LoginAnomaly.org_id    == svc.org_id,
            LoginAnomaly.user_id   == soc_user.id,
            LoginAnomaly.anomaly_type == "tor_detected",
        ).first()
        assert anomaly is not None

    def test_priv_escalation_detection(self, db: Session, svc: SecurityEventService, soc_user: User):
        """5+ ABAC denials from same user triggers privilege-escalation detection."""
        for _ in range(6):
            svc.abac_denied(
                user_id         = soc_user.id,
                resource_type   = "budget",
                resource_id     = "b-1",
                matched_policies= ["deny-role"],
            )

        det = db.query(SecurityDetection).filter(
            SecurityDetection.org_id  == svc.org_id,
            SecurityDetection.mitre_id == "T1078.002",
        ).first()
        assert det is not None
        assert det.severity == EventSeverity.HIGH


# ── Service: incident management ──────────────────────────────────────────────

class TestIncidentManagement:

    def test_create_incident(self, db: Session, svc: SecurityEventService, soc_user: User):
        inc = svc.create_incident(
            title           = "Account takeover campaign",
            severity        = EventSeverity.HIGH,
            detection_ids   = [],
            lead_analyst_id = soc_user.id,
            description     = "Suspected ATO from multiple IPs",
        )
        assert inc.id is not None
        assert inc.status == IncidentStatus.INVESTIGATING

    def test_resolve_incident_sets_mttr(self, db: Session, svc: SecurityEventService, soc_user: User):
        inc = svc.create_incident(
            title="Test incident",
            severity=EventSeverity.MEDIUM,
            detection_ids=[],
            lead_analyst_id=soc_user.id,
        )
        # Simulate some time passing (mutate detected_at to be earlier)
        inc.detected_at = datetime.utcnow() - timedelta(hours=2)
        db.commit()

        resolved = svc.resolve_incident(
            incident_id = inc.id,
            analyst_id  = soc_user.id,
            root_cause  = "Brute-force from botnet",
            remediation = "IP block applied",
            lessons     = "Enable geo-blocking",
        )
        assert resolved.status == IncidentStatus.RESOLVED
        assert resolved.mttr_seconds is not None
        assert resolved.mttr_seconds > 0
        assert resolved.root_cause is not None

    def test_detection_links_to_incident(self, db: Session, svc: SecurityEventService, soc_user: User):
        """Creating an incident with detection_ids links them."""
        ip = "198.18.0.42"
        for _ in range(6):
            svc.login_failed(user_id=None, ip=ip, ua="bot")

        det = db.query(SecurityDetection).filter(
            SecurityDetection.org_id     == svc.org_id,
            SecurityDetection.ip_address == ip,
        ).first()
        assert det is not None

        inc = svc.create_incident(
            title           = "Brute-force incident",
            severity        = EventSeverity.HIGH,
            detection_ids   = [det.id],
            lead_analyst_id = soc_user.id,
        )

        db.refresh(det)
        assert det.incident_id == inc.id
        assert det.status == IncidentStatus.INVESTIGATING


# ── Analytics ─────────────────────────────────────────────────────────────────

class TestSecurityAnalytics:

    def test_overview_returns_keys(self, db: Session, analytics: SecurityAnalyticsService,
                                   svc: SecurityEventService, soc_user: User):
        svc.login_success(soc_user.id, "1.1.1.1", "UA", "US")
        svc.login_failed(None, "2.2.2.2", "UA")

        result = analytics.overview(hours=24)
        assert "total_events" in result
        assert "auth_failure_rate" in result
        assert "open_detections" in result
        assert "open_incidents" in result
        assert "events_by_severity" in result
        assert result["total_events"] >= 2

    def test_event_timeline_buckets(self, db: Session, analytics: SecurityAnalyticsService,
                                    svc: SecurityEventService, soc_user: User):
        svc.login_success(soc_user.id, "3.3.3.3", "UA", "DE")
        result = analytics.event_timeline(hours=2, bucket_minutes=60)
        assert isinstance(result, list)

    def test_login_anomaly_feed_returns_list(self, db: Session, analytics: SecurityAnalyticsService,
                                             svc: SecurityEventService, soc_user: User):
        svc.emit(
            event_type="login_success", category=EventCategory.AUTH,
            severity=EventSeverity.HIGH, user_id=soc_user.id,
            ip_address="185.220.101.2", is_tor=True,
        )
        feed = analytics.login_anomaly_feed(hours=24)
        assert isinstance(feed, list)

    def test_top_attack_indicators(self, db: Session, analytics: SecurityAnalyticsService,
                                   svc: SecurityEventService):
        ip = "10.99.0.1"
        for _ in range(6):
            svc.login_failed(user_id=None, ip=ip, ua="test")
        indicators = analytics.top_attack_indicators(hours=24, limit=5)
        assert isinstance(indicators, list)

    def test_top_offending_ips(self, db: Session, analytics: SecurityAnalyticsService,
                               svc: SecurityEventService):
        for _ in range(3):
            svc.login_failed(None, "77.77.77.77", "UA")
        ips = analytics.top_offending_ips(hours=24, limit=10)
        assert any(r["ip_address"] == "77.77.77.77" for r in ips)

    def test_auth_failure_rate(self, db: Session, analytics: SecurityAnalyticsService,
                               svc: SecurityEventService, soc_user: User):
        svc.login_success(soc_user.id, "4.4.4.4", "UA")
        svc.login_failed(None, "5.5.5.5", "UA")
        svc.login_failed(None, "5.5.5.5", "UA")
        result = analytics.overview(hours=1)
        assert result["auth_failure_rate"] > 0


# ── API smoke tests ───────────────────────────────────────────────────────────

class TestSOCEndpoints:
    """Light smoke tests — verify routing and auth guards work."""

    def _auth_headers(self, db: Session) -> dict:
        uid = str(int(time.time() * 1000))
        org = Organization(id=f"api-org-{uid}", name="API Org", slug=f"api-{uid}")
        db.add(org)
        db.commit()
        response = client.post("/api/v1/auth/register", json={
            "email":    f"soc-api-{uid}@test.com",
            "password": "TestPass123!",
            "username": f"soc-api-{uid}",
            "full_name":"SOC API User",
            "organization_id": org.id,
        })
        if response.status_code not in (200, 201):
            pytest.skip("Auth register unavailable in test environment")
        token = response.json().get("access_token")
        if not token:
            pytest.skip("No token returned from register")
        return {"Authorization": f"Bearer {token}"}

    def test_soc_overview_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/overview")
        assert resp.status_code == 401

    def test_soc_events_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/events")
        assert resp.status_code == 401

    def test_soc_detections_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/detections")
        assert resp.status_code == 401

    def test_soc_incidents_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/incidents")
        assert resp.status_code == 401

    def test_soc_anomalies_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/login-anomalies")
        assert resp.status_code == 401

    def test_soc_attack_indicators_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/metrics/attack-indicators")
        assert resp.status_code == 401

    def test_soc_mttd_mttr_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/metrics/mttd-mttr")
        assert resp.status_code == 401

    def test_soc_auth_heatmap_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/metrics/auth-heatmap")
        assert resp.status_code == 401

    def test_soc_top_ips_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/metrics/top-ips")
        assert resp.status_code == 401

    def test_soc_timeline_unauthorized(self):
        resp = client.get("/api/v1/security-observability/soc/metrics/timeline")
        assert resp.status_code == 401

    def test_manual_event_ingest_unauthorized(self):
        resp = client.post("/api/v1/security-observability/soc/events", json={
            "event_type": "manual", "category": "system", "severity": "info"
        })
        assert resp.status_code == 401
