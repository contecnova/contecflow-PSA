import os
# Forzar modo 'plain' para claves JWT en tests (no KMS)
os.environ["KMS_PROVIDER"] = ""
os.environ["AWS_KMS_KEY_ID"] = ""

"""
conftest.py — Fixtures compartidos para toda la suite de tests de Clarive.
Usa SQLite en memoria para aislamiento total.
"""
import os
import secrets
import pytest
from fastapi.testclient import TestClient

# Disable rate limiting for the entire test suite
os.environ["TESTING"] = "1"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Variables de entorno necesarias para pydantic-settings en tests
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-not-production-use")
os.environ.setdefault("CLIENT_PORTAL_SECRET", "test-client-portal-secret-unit-tests-only")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-for-unit-tests")
os.environ.setdefault("INBOUND_EMAIL_SECRET", "test-inbound-email-secret-for-unit-tests")
os.environ.setdefault("ANTHROPIC_API_URL", "https://api.anthropic.test")
os.environ.setdefault("OPENAI_API_URL", "https://api.openai.test")
os.environ.setdefault("GEMINI_API_URL", "https://api.gemini.test")
os.environ.setdefault("DEEPSEEK_API_URL", "https://api.deepseek.test")
os.environ.setdefault("GROQ_API_URL", "https://api.groq.test")
os.environ.setdefault("MISTRAL_API_URL", "https://api.mistral.test")
os.environ.setdefault("MISTRAL_DOCS_URL", "https://docs.mistral.ai")
os.environ.setdefault("XERO_API_BASE", "https://api.xero.test")
os.environ.setdefault("ANTHROPIC_DOCS_URL", "https://www.anthropic.com/docs")
os.environ.setdefault("OPENAI_DOCS_URL", "https://platform.openai.com/docs")
os.environ.setdefault("GEMINI_DOCS_URL", "https://developers.google.com/ai")
os.environ.setdefault("QB_API_BASE", "https://api.quickbooks.test")
os.environ.setdefault("BASE_URL", "http://localhost:8000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("BACKEND_URL", "http://localhost:8000")
os.environ.setdefault("OLLAMA_BASE_URL", "https://api.ollama.test")
os.environ.setdefault("OLLAMA_DOCS_URL", "https://ollama.com/docs")
os.environ.setdefault("PDF_STORAGE_PATH", "/tmp")
os.environ.setdefault("SUPERADMIN_EMAIL", "admin@clarive.com")
# Generate a strong random test password once per session — not committed to source.
_TEST_PASSWORD = secrets.token_urlsafe(20)
os.environ.setdefault("SUPERADMIN_PASSWORD", _TEST_PASSWORD)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, UserRole, UserStatus
from app.models.mfa import Organization

# ── BD en memoria para tests ───────────────────────────────────────────────────
TEST_DB_URL = "sqlite://"  # In-memory — totalmente aislado entre tests
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    # Para SQLite in-memory: mantener una sola conexión durante todo el test
    poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="function", autouse=True)

def db():
    """Crea tablas y datos base antes de cada test; las borra al final."""
    from app import models as _models  # noqa: F401 — registra todos los modelos en Base.metadata
    Base.metadata.create_all(bind=engine)
    session = TestSession()

    # Admin
    admin_hashed = get_password_hash(_TEST_PASSWORD)
    print(f"[DEBUG] TEST_PASSWORD: {_TEST_PASSWORD}")
    print(f"[DEBUG] ADMIN HASHED PASSWORD: {admin_hashed}")
    admin = User(
        id="admin-test-id",
        username="admin",
        email="admin@clarive.com",
        full_name="Admin Test",
        role=UserRole.admin,
        status=UserStatus.active,
        is_active=True,
        hashed_password=admin_hashed,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # PM
    pm = User(
        id="pm-test-id",
        username="pm_test",
        email="pm@clarive.com",
        full_name="PM Test",
        role=UserRole.pm,
        status=UserStatus.active,
        is_active=True,
        hashed_password=get_password_hash(_TEST_PASSWORD),
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # Employee (anteriormente developer)
    dev = User(
        id="dev-test-id",
        username="dev_test",
        email="dev@clarive.com",
        full_name="Dev Test",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        hourly_rate=50.0,
        hashed_password=get_password_hash(_TEST_PASSWORD),
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # HR user
    hr = User(
        id="hr-test-id",
        username="hr_test",
        email="hr@clarive.com",
        full_name="HR Test",
        role=UserRole.hr,
        status=UserStatus.active,
        is_active=True,
        hashed_password=get_password_hash(_TEST_PASSWORD),
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    org = Organization(
        id=1,
        name="Test Organization",
        slug="test-org",
        is_active=True,
    )
    session.add(org)
    # Associate admin user with org
    admin.organization_id = 1
    pm.organization_id = 1
    dev.organization_id = 1
    hr.organization_id = 1
    session.add_all([admin, pm, dev, hr])
    session.commit()
    session.close()

    # --- Inicializar el cache global de claves JWT para la app ---
    from app.services.key_management import refresh_caches
    db_session = TestSession()

    refresh_caches(db_session)
    # Debug print the JWT keyring value after initialization
    from sqlalchemy import text as _text
    row = db_session.execute(_text("SELECT value FROM app_settings WHERE key='security.jwt_keyring'")).first()
    print(f"[DEBUG] JWT keyring value after refresh_caches: {row}")

    yield db_session
    db_session.close()

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client():
    return TestClient(app)


@pytest.fixture(scope="function")
def admin_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": _TEST_PASSWORD})
    assert res.status_code == 200, f"Login admin falló: {res.text}"
    return res.json()["access_token"]


@pytest.fixture(scope="function")
def pm_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "pm_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(scope="function")
def dev_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "dev_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(scope="function")
def hr_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "hr_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}

# Export the test password so individual test modules can use it for direct login calls
TEST_PASSWORD = _TEST_PASSWORD

@pytest.fixture(scope="function")
def seed_multitenant(db):
    """
    Inicializa datos multi-tenant limpios para pruebas de aislamiento:
    - Crea dos organizaciones (ORG_A, ORG_B)
    - Asocia admin, pm, dev, hr a ORG_A
    - Crea un usuario outsider en ORG_B
    - Crea proyectos y tareas en ambas organizaciones
    """
    from app.models.mfa import Organization
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.task import Task, TaskPriority, TaskStatus
    from app.models.user import User, UserRole, UserStatus
    from app.core.security import get_password_hash
    
    ORG_A_ID = "org-a-test"
    ORG_B_ID = "org-b-test"
    PROJECT_A_ID = "project-a-test"
    PROJECT_B_ID = "project-b-test"
    TASK_A_ID = "task-a-test"
    TASK_B_ID = "task-b-test"
    OUTSIDER_ID = "outsider-test-id"

    # Limpiar tablas relevantes
    db.query(Task).delete()
    db.query(Project).delete()
    db.query(Organization).delete()
    db.query(User).filter(User.id == OUTSIDER_ID).delete()
    db.commit()

    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    db.add_all([org_a, org_b])
    db.flush()

    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    dev = db.query(User).filter(User.id == "dev-test-id").first()
    hr = db.query(User).filter(User.id == "hr-test-id").first()
    for user in (admin, pm, dev, hr):
        user.organization_id = ORG_A_ID

    outsider = User(
        id=OUTSIDER_ID,
        username="outsider",
        email="outsider@example.com",
        full_name="Outsider User",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        organization_id=ORG_B_ID,
        hourly_rate=999.0,
        hashed_password=get_password_hash(TEST_PASSWORD),
    )
    db.add(outsider)
    db.flush()

    project_a = Project(
        id=PROJECT_A_ID,
        organization_id=ORG_A_ID,
        code="PRJ-TA",
        name="Tenant Project A",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        pm_id=pm.id,
        created_by=admin.id,
    )
    project_b = Project(
        id=PROJECT_B_ID,
        organization_id=ORG_B_ID,
        code="PRJ-TB",
        name="Tenant Project B",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        created_by=OUTSIDER_ID,
    )
    db.add_all([project_a, project_b])
    db.flush()

    task_a = Task(
        id=TASK_A_ID,
        code="TSK-TA001",
        project_id=PROJECT_A_ID,
        title="Task tenant A",
        assignee_id=dev.id,
        reporter_id=admin.id,
        created_by=admin.id,
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
    )
    task_b = Task(
        id=TASK_B_ID,
        code="TSK-TB001",
        project_id=PROJECT_B_ID,
        title="Task tenant B",
        assignee_id=OUTSIDER_ID,
        reporter_id=OUTSIDER_ID,
        created_by=OUTSIDER_ID,
        status=TaskStatus.todo,
        priority=TaskPriority.high,
    )
    db.add_all([task_a, task_b])
    db.commit()
    yield
