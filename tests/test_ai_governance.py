"""
Tests for AI Governance: PII detection, guardrail engine, and admin API endpoints.
"""
import pytest

from tests.conftest import auth


# ── PII Detection unit tests ──────────────────────────────────────────────────

class TestPIIDetection:
    def test_email_detected(self):
        from app.services.ai_governance import detect_pii
        matches = detect_pii("Contacta a john.doe@example.com para más info")
        types = [m.entity_type for m in matches]
        assert "email" in types

    def test_spanish_phone_detected(self):
        from app.services.ai_governance import detect_pii
        # Unspaced Spanish mobile — matches [6-9]\d{8}
        matches = detect_pii("Mi teléfono es 612345678")
        types = [m.entity_type for m in matches]
        assert "phone_es" in types

    def test_international_phone_detected(self):
        from app.services.ai_governance import detect_pii
        matches = detect_pii("Call me at +1-800-555-0199")
        types = [m.entity_type for m in matches]
        assert "phone_intl" in types

    def test_dni_detected(self):
        from app.services.ai_governance import detect_pii
        matches = detect_pii("DNI: 12345678Z")
        types = [m.entity_type for m in matches]
        assert "dni_nie" in types

    def test_nie_detected(self):
        from app.services.ai_governance import detect_pii
        # X1234567 → 01234567 % 23 = 19 → letra correcta = L.
        # (Item #65: ahora se valida checksum, así que el fixture debe ser válido.)
        matches = detect_pii("NIE: X1234567L")
        types = [m.entity_type for m in matches]
        assert "dni_nie" in types

    def test_nif_detected(self):
        from app.services.ai_governance import detect_pii
        matches = detect_pii("NIF empresa: A12345678")
        types = [m.entity_type for m in matches]
        assert "nif_nif" in types

    def test_credit_card_detected(self):
        from app.services.ai_governance import detect_pii
        # Unspaced Visa test number
        matches = detect_pii("Tarjeta: 4111111111111111")
        types = [m.entity_type for m in matches]
        assert "credit_card" in types

    def test_iban_detected(self):
        from app.services.ai_governance import detect_pii
        # Unspaced IBAN
        matches = detect_pii("IBAN: ES9121000418450200051332")
        types = [m.entity_type for m in matches]
        assert "iban" in types

    def test_ip_address_detected(self):
        from app.services.ai_governance import detect_pii
        matches = detect_pii("Server IP is 192.168.1.100")
        types = [m.entity_type for m in matches]
        assert "ip_address" in types

    def test_no_pii_in_clean_text(self):
        from app.services.ai_governance import has_pii
        assert not has_pii("El proyecto avanza según lo previsto. Reunión el lunes.")

    def test_has_pii_returns_true(self):
        from app.services.ai_governance import has_pii
        assert has_pii("Email me at alice@corp.io")

    def test_multiple_entities_same_text(self):
        from app.services.ai_governance import detect_pii
        # 12345678Z es DNI válido (12345678 % 23 = 14 → 'Z').
        # (Item #65: checksum validation activado.)
        text = "Email: user@test.com, Tel: 612000111, DNI: 12345678Z"
        matches = detect_pii(text)
        types = {m.entity_type for m in matches}
        assert "email" in types
        assert "phone_es" in types
        assert "dni_nie" in types


# ── PII Redaction unit tests ──────────────────────────────────────────────────

class TestPIIRedaction:
    def test_mask_strategy(self):
        from app.services.ai_governance import redact_pii
        text = "Contact: user@example.com"
        redacted, matches = redact_pii(text, ["email"], "mask")
        assert "user@example.com" not in redacted
        assert len(matches) == 1

    def test_hash_strategy(self):
        from app.services.ai_governance import redact_pii
        text = "Contact: user@example.com"
        redacted, matches = redact_pii(text, ["email"], "hash")
        assert "user@example.com" not in redacted
        assert len(matches) == 1

    def test_partial_strategy(self):
        from app.services.ai_governance import redact_pii
        text = "Contact: user@example.com"
        redacted, matches = redact_pii(text, ["email"], "partial")
        assert "user@example.com" not in redacted
        assert len(matches) == 1

    def test_remove_strategy(self):
        from app.services.ai_governance import redact_pii
        text = "Contact: user@example.com please"
        redacted, matches = redact_pii(text, ["email"], "remove")
        assert "user@example.com" not in redacted
        assert "Contact:" in redacted

    def test_no_match_returns_original(self):
        from app.services.ai_governance import redact_pii
        text = "Hello world"
        redacted, matches = redact_pii(text, ["email"], "mask")
        assert redacted == text
        assert matches == []

    def test_email_redacted_in_mixed_text(self):
        from app.services.ai_governance import redact_pii
        text = "Email: alice@test.com"
        redacted, matches = redact_pii(text, ["email"], "mask")
        assert "alice@test.com" not in redacted

    def test_multiple_redactions_preserve_surrounding_text(self):
        from app.services.ai_governance import redact_pii
        text = "Contact a@b.com and also c@d.com"
        redacted, matches = redact_pii(text, ["email"], "mask")
        assert "a@b.com" not in redacted
        assert "c@d.com" not in redacted
        assert "Contact" in redacted
        assert "and also" in redacted


# ── Guardrail engine unit tests ───────────────────────────────────────────────

class TestGuardrailEngine:
    def test_evaluate_allow_no_policies(self, db):
        """With no policies, everything is allowed."""
        from app.services.ai_governance import AIGuardrailEngine
        from app.models.user import UserRole

        engine = AIGuardrailEngine(db, org_id=None)
        result = engine.evaluate(
            "Hello world", role=UserRole.employee.value,
            module="nexusassist", scope="prompt", user_id="user-1",
        )
        assert result.allowed is True

    def test_check_prompt_helper_returns_guardrail_result(self, db):
        from app.services.ai_governance import check_prompt

        class _User:
            org_id = None
            role = type("R", (), {"value": "employee"})()
            id = "test-user"

        result = check_prompt("Hello", _User(), "nexusassist", db)
        assert result.allowed is True

    def test_check_output_helper_returns_guardrail_result(self, db):
        from app.services.ai_governance import check_output

        class _User:
            org_id = None
            role = type("R", (), {"value": "employee"})()
            id = "test-user"

        result = check_output("Here is your report", _User(), "nexusassist", db)
        assert result.allowed is True


# ── AI Governance API smoke tests ─────────────────────────────────────────────

@pytest.fixture()
def admin_with_org(admin_token, db, client):
    """Ensures admin test user has an organization_id for org-scoped endpoints."""
    from app.models.mfa import Organization
    from app.models.user import User
    org = Organization(id="gov-test-org", name="Gov Test Org", slug="gov-test-org")
    db.add(org)
    db.flush()
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    admin.organization_id = "gov-test-org"
    db.commit()
    return admin_token


class TestAIGovernanceAPI:
    def test_list_pii_types(self, client, admin_with_org):
        res = client.get("/api/v1/ai-governance/pii-types", headers=auth(admin_with_org))
        assert res.status_code == 200
        pii_types = res.json()["data"]["pii_types"]
        assert "email" in pii_types

    def test_list_policies_empty(self, client, admin_with_org):
        res = client.get("/api/v1/ai-governance/policies", headers=auth(admin_with_org))
        assert res.status_code == 200
        body = res.json()
        items = body.get("items") if isinstance(body, dict) else body
        assert items == []

    def test_create_policy_admin(self, client, admin_with_org):
        payload = {
            "name": "Block PII in NexusAssist",
            "applies_to_modules": ["nexusassist"],
            "applies_to_roles": [],
            "scope": "both",
            "action": "redact",
            "pii_entity_types": ["email", "phone_es"],
            "redact_strategy": "mask",
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 10,
        }
        res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["name"] == "Block PII in NexusAssist"
        assert data["action"] == "redact"

    def test_create_policy_non_admin_forbidden(self, client, dev_token):
        payload = {
            "name": "Employee policy attempt",
            "applies_to_modules": ["nexusassist"],
            "applies_to_roles": [],
            "scope": "both",
            "action": "log",
            "pii_entity_types": [],
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 0,
        }
        res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(dev_token))
        assert res.status_code == 403

    def test_get_policy_by_id(self, client, admin_with_org):
        payload = {
            "name": "Test policy",
            "applies_to_modules": [],
            "applies_to_roles": [],
            "scope": "prompt",
            "action": "log",
            "pii_entity_types": ["email"],
            "forbidden_keywords": ["password"],
            "is_active": True,
            "priority": 5,
        }
        create_res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        assert create_res.status_code == 201
        policy_id = create_res.json()["data"]["id"]

        get_res = client.get(f"/api/v1/ai-governance/policies/{policy_id}", headers=auth(admin_with_org))
        assert get_res.status_code == 200
        assert get_res.json()["id"] == policy_id

    def test_update_policy(self, client, admin_with_org):
        payload = {
            "name": "Update test",
            "applies_to_modules": [],
            "applies_to_roles": [],
            "scope": "output",
            "action": "warn",
            "pii_entity_types": [],
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 1,
        }
        create_res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        policy_id = create_res.json()["data"]["id"]

        update_res = client.patch(
            f"/api/v1/ai-governance/policies/{policy_id}",
            json={"priority": 99},
            headers=auth(admin_with_org),
        )
        assert update_res.status_code == 200
        assert update_res.json()["priority"] == 99

    def test_delete_policy_deactivates(self, client, admin_with_org):
        payload = {
            "name": "Delete test",
            "applies_to_modules": [],
            "applies_to_roles": [],
            "scope": "both",
            "action": "log",
            "pii_entity_types": [],
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 0,
        }
        create_res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        policy_id = create_res.json()["data"]["id"]

        del_res = client.delete(f"/api/v1/ai-governance/policies/{policy_id}", headers=auth(admin_with_org))
        assert del_res.status_code == 200

        get_res = client.get(f"/api/v1/ai-governance/policies/{policy_id}", headers=auth(admin_with_org))
        assert get_res.status_code == 200
        assert get_res.json()["is_active"] is False

    def test_audit_log_accessible_admin(self, client, admin_with_org):
        res = client.get("/api/v1/ai-governance/audit-log", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()["items"]
        assert "items" in data
        assert "total" in data

    def test_audit_log_stats(self, client, admin_with_org):
        res = client.get("/api/v1/ai-governance/audit-log/stats", headers=auth(admin_with_org))
        assert res.status_code == 200
        data = res.json()["data"]
        assert "total_evaluations" in data
        assert "block_rate" in data

    def test_check_prompt_admin_tool(self, client, admin_with_org):
        res = client.post(
            "/api/v1/ai-governance/check/prompt",
            json={"text": "Hello world no PII here", "module": "nexusassist"},
            headers=auth(admin_with_org),
        )
        assert res.status_code == 200
        assert "allowed" in res.json()

    def test_check_output_admin_tool(self, client, admin_with_org):
        res = client.post(
            "/api/v1/ai-governance/check/output",
            json={"text": "Report looks good.", "module": "nexusassist"},
            headers=auth(admin_with_org),
        )
        assert res.status_code == 200
        assert "allowed" in res.json()

    def test_policy_invalid_scope_rejected(self, client, admin_with_org):
        payload = {
            "name": "Bad scope",
            "applies_to_modules": [],
            "applies_to_roles": [],
            "scope": "INVALID_SCOPE",
            "action": "log",
            "pii_entity_types": [],
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 0,
        }
        res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        assert res.status_code == 422

    def test_policy_invalid_action_rejected(self, client, admin_with_org):
        payload = {
            "name": "Bad action",
            "applies_to_modules": [],
            "applies_to_roles": [],
            "scope": "both",
            "action": "DESTROY",
            "pii_entity_types": [],
            "forbidden_keywords": [],
            "is_active": True,
            "priority": 0,
        }
        res = client.post("/api/v1/ai-governance/policies", json=payload, headers=auth(admin_with_org))
        assert res.status_code == 422
