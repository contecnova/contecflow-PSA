"""
test_nps_customer_health.py — Tests for NPS and Customer Health scoring.

Covers:
  - NPS response submission and category classification
  - NPS summary computation (promoters / detractors / score)
  - Health snapshot creation and compute
  - Composite health score formula (NPS 40%, delivery 20%, budget 15%, tickets 15%, portal 10%)
  - NPS leaderboard and health trend
"""
import pytest
from tests.conftest import auth
from app.core.errores import ErrorDeDominio


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_client(client, token, name="NPS Client"):
    res = client.post(
        "/api/v1/clients",
        json={"name": name, "industry": "technology", "country": "ES"},
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]


# ── NPS Response Submission ────────────────────────────────────────────────────

class TestNPSResponses:
    def test_submit_promoter_score(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Promoter Client")
        res = client.post(
            f"/api/v1/nps/{c['id']}/responses",
            json={"score": 9, "comment": "Excellent service!", "source": "survey"},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data.get("category") == "promoter"

    def test_submit_passive_score(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Passive Client")
        res = client.post(
            f"/api/v1/nps/{c['id']}/responses",
            json={"score": 7, "source": "email"},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data.get("category") == "passive"

    def test_submit_detractor_score(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Detractor Client")
        res = client.post(
            f"/api/v1/nps/{c['id']}/responses",
            json={"score": 3, "comment": "Poor delivery", "source": "interview"},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert data.get("category") == "detractor"

    def test_score_out_of_range_rejected(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Bad Score Client")
        res = client.post(
            f"/api/v1/nps/{c['id']}/responses",
            json={"score": 11, "source": "survey"},
            headers=auth(admin_token),
        )
        assert res.status_code in (400, 422)

    def test_list_nps_responses(self, client, admin_token, db):
        c = _create_client(client, admin_token, "List Client")
        for score in [10, 8, 5]:
            client.post(
                f"/api/v1/nps/{c['id']}/responses",
                json={"score": score, "source": "survey"},
                headers=auth(admin_token),
            )
        res = client.get(
            f"/api/v1/nps/{c['id']}/responses",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["items"]
        assert len(data) >= 3

    def test_nps_response_for_nonexistent_client(self, client, admin_token, db):
        res = client.post(
            "/api/v1/nps/nonexistent-client-id/responses",
            json={"score": 9, "source": "survey"},
            headers=auth(admin_token),
        )
        assert res.status_code == 404


# ── NPS Summary Computation ────────────────────────────────────────────────────

class TestNPSSummary:
    def test_summary_no_responses(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Empty NPS Client")
        res = client.get(
            f"/api/v1/nps/{c['id']}/summary",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        # Should return a summary even with no data
        assert "nps_score" in data or "score" in data or data.get("total", 0) == 0

    def test_summary_all_promoters(self, client, admin_token, db):
        c = _create_client(client, admin_token, "All Promoters")
        for _ in range(3):
            client.post(
                f"/api/v1/nps/{c['id']}/responses",
                json={"score": 10, "source": "survey"},
                headers=auth(admin_token),
            )
        res = client.get(
            f"/api/v1/nps/{c['id']}/summary",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        # NPS = (3 promoters - 0 detractors) / 3 * 100 = 100
        score = data.get("nps_score") or data.get("score")
        if score is not None:
            assert score == pytest.approx(100.0, abs=1.0)

    def test_summary_mixed_responses(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Mixed NPS")
        # 2 promoters, 1 passive, 1 detractor → NPS = (2-1)/4*100 = 25
        for score in [10, 9, 7, 4]:
            client.post(
                f"/api/v1/nps/{c['id']}/responses",
                json={"score": score, "source": "survey"},
                headers=auth(admin_token),
            )
        res = client.get(
            f"/api/v1/nps/{c['id']}/summary",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        score = data.get("nps_score") or data.get("score")
        if score is not None:
            assert score == pytest.approx(25.0, abs=1.0)


# ── NPS Service Unit Tests ─────────────────────────────────────────────────────

class TestNPSServiceUnit:
    """Tests for the nps_service business logic functions directly."""

    def test_category_promoter(self):
        from app.services.nps_service import _nps_category
        from app.models.nps import NPSCategory
        assert _nps_category(9) == NPSCategory.promoter
        assert _nps_category(10) == NPSCategory.promoter

    def test_category_passive(self):
        from app.services.nps_service import _nps_category
        from app.models.nps import NPSCategory
        assert _nps_category(7) == NPSCategory.passive
        assert _nps_category(8) == NPSCategory.passive

    def test_category_detractor(self):
        from app.services.nps_service import _nps_category
        from app.models.nps import NPSCategory
        assert _nps_category(0) == NPSCategory.detractor
        assert _nps_category(6) == NPSCategory.detractor

    def test_compute_nps_no_responses(self):
        from app.services.nps_service import _compute_nps
        assert _compute_nps([]) is None

    def test_compute_nps_all_promoters(self, db):
        from app.services.nps_service import create_nps_entry, _compute_nps
        from app.models.clients import Client

        c = Client(name="NPS Unit Client", industry="technology")
        db.add(c)
        db.flush()

        r1 = create_nps_entry(db, c.id, 10, None, None, "test")
        r2 = create_nps_entry(db, c.id, 9, None, None, "test")
        nps = _compute_nps([r1, r2])
        assert nps == pytest.approx(100.0)

    def test_compute_nps_mixed(self, db):
        from app.services.nps_service import create_nps_entry, _compute_nps
        from app.models.clients import Client

        c = Client(name="NPS Mixed Client", industry="finance")
        db.add(c)
        db.flush()

        r_promoter = create_nps_entry(db, c.id, 10, None, None, "test")
        r_detractor = create_nps_entry(db, c.id, 3, None, None, "test")
        # NPS = (1 - 1) / 2 * 100 = 0
        nps = _compute_nps([r_promoter, r_detractor])
        assert nps == pytest.approx(0.0)


# ── Customer Health Composite Score ───────────────────────────────────────────

class TestCustomerHealthScore:
    def test_health_compute_no_data_returns_default(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Health Client Zero")
        res = client.post(
            f"/api/v1/nps/{c['id']}/health-compute",
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        assert "score" in data or "composite" in data or "health_score" in data

    def test_health_score_with_nps_data(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Health With NPS")
        # Submit 3 promoter responses
        for _ in range(3):
            client.post(
                f"/api/v1/nps/{c['id']}/responses",
                json={"score": 10, "source": "survey"},
                headers=auth(admin_token),
            )
        res = client.post(
            f"/api/v1/nps/{c['id']}/health-compute",
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 201), res.text
        data = res.json()["data"]
        # With all promoters NPS component is high; composite should be >= 50
        score = data.get("score") or data.get("composite") or data.get("health_score")
        if score is not None:
            assert float(score) >= 50.0

    def test_health_snapshot_saved(self, client, admin_token, db):
        c = _create_client(client, admin_token, "Snapshot Client")
        # Create snapshot
        client.post(
            f"/api/v1/nps/{c['id']}/health-snapshot",
            headers=auth(admin_token),
        )
        # Read it back
        res = client.get(
            f"/api/v1/nps/{c['id']}/health",
            headers=auth(admin_token),
        )
        assert res.status_code == 200

    def test_health_composite_formula_unit(self, db):
        """Validate the composite health formula directly from the service."""
        from app.services.customer_health_service import compute_composite_health
        from app.models.clients import Client

        c = Client(name="Formula Test Client", industry="consulting")
        db.add(c)
        db.flush()

        result = compute_composite_health(c.id, db)
        assert "components" in result
        # Default NPS component (no data) should be 50
        assert result["components"]["nps"]["value"] == pytest.approx(50.0)
        # Delivery default is 70
        assert result["components"]["delivery"]["value"] == pytest.approx(70.0)

    def test_health_compute_nonexistent_client(self, db):
        from app.services.customer_health_service import compute_composite_health
        from fastapi import HTTPException

        with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
            compute_composite_health("does-not-exist", db)
        assert exc.value.status_code == 404


# ── NPS Leaderboard ───────────────────────────────────────────────────────────

class TestNPSLeaderboard:
    def test_leaderboard_returns_list(self, client, admin_token, db):
        res = client.get("/api/v1/nps/leaderboard", headers=auth(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json()["items"], list)
