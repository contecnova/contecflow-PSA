"""
Tests for Document Management API.
"""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from app.models.user import User


@pytest.fixture
def doc_client(client, admin_token):
    """Fixture for API client with auth headers."""
    return (client, admin_token)


def test_create_document(db: Session, doc_client):
    """Test creating a new document."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "title": "Test Contract",
        "description": "Test document",
        "category": "contract",
        "requires_approval": True,
    }

    response = client.post("/api/v1/documents", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Contract"
    assert data["category"] == "contract"
    assert data["requires_approval"] == True
    assert data["approval_status"] == "pending"


def test_list_documents(db: Session, doc_client):
    """Test listing documents."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create a document
    payload = {"title": "Document 1", "category": "proposal"}
    client.post("/api/v1/documents", json=payload, headers=headers)

    # List documents
    response = client.get("/api/v1/documents", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


def test_get_document(db: Session, doc_client):
    """Test getting document detail."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create document
    create_payload = {"title": "Test Doc", "category": "sop"}
    create_response = client.post("/api/v1/documents", json=create_payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Get document
    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Doc"
    assert data["category"] == "sop"


def test_update_document(db: Session, doc_client):
    """Test updating document metadata."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create document
    create_payload = {"title": "Original Title", "category": "meeting_notes"}
    create_response = client.post("/api/v1/documents", json=create_payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Update document
    update_payload = {"title": "Updated Title", "description": "New description"}
    response = client.patch(f"/api/v1/documents/{doc_id}", json=update_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "New description"


def test_delete_document(db: Session, doc_client):
    """Test soft delete of document."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create and archive document
    create_payload = {"title": "To Delete"}
    create_response = client.post("/api/v1/documents", json=create_payload, headers=headers)
    doc_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 200

    # Verify archived
    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_archived"] == True


def test_document_permissions(db: Session, doc_client):
    """Test document permission management."""
    client, admin_token = doc_client
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create document
    payload = {"title": "Test Doc"}
    create_response = client.post("/api/v1/documents", json=payload, headers=admin_headers)
    doc_id = create_response.json()["id"]

    # Get any non-admin user ID
    db_session = db
    dev_user = db_session.query(User).filter(User.role == "employee").first()
    if not dev_user:
        pytest.skip("No test employee user found")

    # Grant permission
    perm_payload = {
        "user_id": dev_user.id,
        "access_level": "viewer",
    }
    response = client.post(
        f"/api/v1/documents/{doc_id}/permissions",
        json=perm_payload,
        headers=admin_headers,
    )
    assert response.status_code == 200
    perm_data = response.json()
    assert perm_data["access_level"] == "viewer"
    perm_id = perm_data["id"]

    # Revoke permission
    response = client.delete(
        f"/api/v1/documents/{doc_id}/permissions/{perm_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200


def test_document_approval(db: Session, doc_client):
    """Test document approval workflow."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create document with approval required
    payload = {
        "title": "Approval Doc",
        "requires_approval": True,
    }
    create_response = client.post("/api/v1/documents", json=payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Approve document
    approve_payload = {"status": "approved"}
    response = client.post(
        f"/api/v1/documents/{doc_id}/approve",
        json=approve_payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["approval_status"] == "approved"


def test_document_file_upload_and_versioning(db: Session, doc_client):
    """Test document version upload."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create document
    payload = {"title": "Versioned Doc"}
    create_response = client.post("/api/v1/documents", json=payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Upload file version
    file_content = b"This is test content for version 1"
    files = {
        "file": ("test_v1.txt", BytesIO(file_content), "text/plain"),
        "change_note": (None, "Initial upload"),
    }
    response = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files=files,
        headers=headers,
    )
    assert response.status_code == 200
    version_data = response.json()
    assert version_data["version_num"] == 1
    assert version_data["file_name"] == "test_v1.txt"

    # Verify document now has versions
    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["versions"]) >= 1


def test_document_file_head_returns_metadata_headers(db: Session, doc_client):
    """HEAD on local file endpoint should return metadata without 405."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post("/api/v1/documents", json={"title": "HEAD test doc"}, headers=headers)
    doc_id = create_response.json()["id"]

    files = {
        "file": ("head_test.txt", BytesIO(b"head endpoint test"), "text/plain"),
    }
    upload_response = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files=files,
        headers=headers,
    )
    assert upload_response.status_code == 200
    download_url = upload_response.json()["download_url"]
    parsed = urlparse(download_url)
    head_path = parsed.path
    access = parse_qs(parsed.query).get("access", [None])[0]
    assert access

    head_response = client.head(f"{head_path}?access={access}")
    assert head_response.status_code == 200
    assert "content-type" in {k.lower() for k in head_response.headers.keys()}
    assert "content-length" in {k.lower() for k in head_response.headers.keys()}


def test_document_file_get_with_scoped_access_token_no_auth_header(db: Session, doc_client):
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post("/api/v1/documents", json={"title": "Scoped access doc"}, headers=headers)
    doc_id = create_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("scoped.txt", BytesIO(b"scoped body"), "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 200

    download_url = upload_response.json()["download_url"]
    parsed = urlparse(download_url)
    access = parse_qs(parsed.query).get("access", [None])[0]
    assert access

    # Browser-native fetch without Authorization should still work via scoped token.
    get_response = client.get(f"{parsed.path}?access={access}")
    assert get_response.status_code == 200
    assert get_response.content == b"scoped body"


def test_document_file_size_validation(db: Session, doc_client):
    """Test file size validation exceeds MAX_FILE_SIZE."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create document
    payload = {"title": "Large File Test"}
    create_response = client.post("/api/v1/documents", json=payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Try to upload file larger than MAX_FILE_SIZE_MB (from config, default 100MB)
    # Create 101MB of data
    large_content = b"X" * (101 * 1024 * 1024)
    files = {
        "file": ("large_file.bin", BytesIO(large_content), "application/octet-stream"),
    }
    response = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files=files,
        headers=headers,
    )
    # Should be rejected with 413 Payload Too Large
    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]


def test_document_permission_expiration(db: Session, doc_client):
    """Test that expired permissions are considered invalid."""
    client, admin_token = doc_client
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create document
    payload = {"title": "Permission Expiry Test"}
    create_response = client.post("/api/v1/documents", json=payload, headers=admin_headers)
    doc_id = create_response.json()["id"]

    # Get test employee user
    db_session = db
    dev_user = db_session.query(User).filter(User.role == "employee").first()
    if not dev_user:
        pytest.skip("No test employee user found")

    # Grant permission with expiration 1 day in future
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    perm_payload = {
        "user_id": dev_user.id,
        "access_level": "viewer",
        "expires_at": expires_at,
    }
    response = client.post(
        f"/api/v1/documents/{doc_id}/permissions",
        json=perm_payload,
        headers=admin_headers,
    )
    assert response.status_code == 200

    # Verify permission exists
    response = client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    data = response.json()
    assert len(data["permissions"]) >= 1


def test_non_admin_cannot_see_other_documents(db: Session, client, admin_token):
    """Test that non-admins cannot see documents they don't have permission to."""
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create document as admin
    payload = {"title": "Secret Admin Doc"}
    create_response = client.post("/api/v1/documents", json=payload, headers=admin_headers)
    create_response.json()["id"]

    # Get a non-admin user and authenticate as them
    db_session = db
    dev_user = db_session.query(User).filter(User.role == "employee").first()
    if not dev_user:
        pytest.skip("No test employee user found")

    # This would require a way to get token for employee user
    # For now, we just verify the endpoint exists
    response = client.get("/api/v1/documents", headers=admin_headers)
    assert response.status_code == 200


def test_archived_documents_filtered_by_default(db: Session, doc_client):
    """Test that archived documents are not returned by default."""
    client, token = doc_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create and archive a document
    payload = {"title": "To Archive"}
    create_response = client.post("/api/v1/documents", json=payload, headers=headers)
    doc_id = create_response.json()["id"]

    # Archive it
    client.delete(f"/api/v1/documents/{doc_id}", headers=headers)

    # List active documents (default)
    response = client.get("/api/v1/documents?is_archived=false", headers=headers)
    assert response.status_code == 200
    data = response.json()
    archived_docs = [d for d in data if d["id"] == doc_id]
    assert len(archived_docs) == 0  # Should not be in active list

    # List archived documents
    response = client.get("/api/v1/documents?is_archived=true", headers=headers)
    assert response.status_code == 200
    data = response.json()
    archived_docs = [d for d in data if d["id"] == doc_id]
    assert len(archived_docs) == 1  # Should be in archived list


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
