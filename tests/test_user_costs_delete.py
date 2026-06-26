from datetime import date

from app.models.user_cost import CountryEmployerCost
from app.models.user_cost import UserCostProfile
from app.models.user import User
from tests.conftest import auth


def _get_admin_user_id(db):
    row = db.query(User).filter(User.username == "admin").first()
    assert row is not None
    return row.id


def test_delete_country_preset_hard_and_hidden(client, admin_token, db):
    created = client.post(
        "/api/v1/user-costs/countries",
        headers=auth(admin_token),
        json={
            "country_code": "ZZ",
            "country_name": "Delete Country",
            "currency": "EUR",
            "employer_cost_pct": 0.31,
            "productive_hours_year": 1700,
        },
    )
    assert created.status_code == 200
    preset_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/user-costs/countries/{preset_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get("/api/v1/user-costs/countries", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(c["id"] != preset_id for c in listed.json()["items"])

    row = db.query(CountryEmployerCost).filter(CountryEmployerCost.id == preset_id).first()
    assert row is None


def test_delete_user_cost_profile_hard_and_hidden(client, admin_token, db):
    user_id = _get_admin_user_id(db)
    created = client.post(
        f"/api/v1/user-costs/users/{user_id}/profiles",
        headers=auth(admin_token),
        json={
            "valid_from": date.today().isoformat(),
            "gross_annual_salary": 42000,
            "employer_cost_pct": 0.32,
            "extra_annual_costs": 1000,
            "productive_hours_year": 1700,
            "currency": "EUR",
            "notes": "profile-delete-test",
        },
    )
    assert created.status_code in (200, 201)
    profile_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/user-costs/profiles/{profile_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get(
        f"/api/v1/user-costs/users/{user_id}/profiles",
        headers=auth(admin_token),
    )
    assert listed.status_code == 200
    assert all(p["id"] != profile_id for p in listed.json()["items"])

    row = db.query(UserCostProfile).filter(UserCostProfile.id == profile_id).first()
    assert row is None
