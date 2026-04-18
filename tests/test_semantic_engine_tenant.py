import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.user import User
from app.models.semantic_engine import SemProfile
from app.db.session import get_db

client = TestClient(app)

def test_list_profiles_with_users_tenant_filter(db):
    # Crear dos usuarios en diferentes organizaciones
    org1 = "org-1"
    org2 = "org-2"
    user1 = User(id="u1", full_name="User Org1", organization_id=org1, is_active=True)
    user2 = User(id="u2", full_name="User Org2", organization_id=org2, is_active=True)
    db.add(user1)
    db.add(user2)
    db.commit()
    # Crear perfiles semánticos para ambos
    profile1 = SemProfile(user_id="u1", profile_text="Perfil Org1")
    profile2 = SemProfile(user_id="u2", profile_text="Perfil Org2")
    db.add(profile1)
    db.add(profile2)
    db.commit()
    # Simular login como user1 (org1)
    db.info["organization_id"] = org1
    response = client.get("/api/v1/semantic-engine/profiles")
    assert response.status_code == 200
    data = response.json()
    # Solo debe aparecer el perfil de user1
    assert any(p["user_id"] == "u1" for p in data)
    assert not any(p["user_id"] == "u2" for p in data)
    # Simular login como user2 (org2)
    db.info["organization_id"] = org2
    response = client.get("/api/v1/semantic-engine/profiles")
    assert response.status_code == 200
    data = response.json()
    assert any(p["user_id"] == "u2" for p in data)
    assert not any(p["user_id"] == "u1" for p in data)
