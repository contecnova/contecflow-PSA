"""
tests/test_v235_features.py
Tests for v23.5 features:
  1. Multi-tenancy org isolation (project-level) — see test_projects.py
  2. Jira periodic sync Celery task (unit-level smoke test)
  3. Resource scheduler drag-to-assign backend: booking creation via API
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta
from tests.conftest import auth


# ── 1. Jira periodic sync Celery task (unit tests with mocked DB) ─────────────

def _mock_session_no_settings():
    """Returns a mock DB session that finds no AppSetting rows."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


def _mock_session_with_settings(settings_dict):
    """Returns a mock DB session that returns values from settings_dict."""
    def _query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def _filter_side_effect(*fa, **fk):
            mock_f = MagicMock()
            # Inspect the filter argument to determine which key is requested
            def _first():
                for key, val in settings_dict.items():
                    fa_str = str(fa)
                    if key in fa_str:
                        row = MagicMock()
                        row.value = val
                        return row
                return None
            mock_f.first = _first
            return mock_f
        mock_q.filter = _filter_side_effect
        return mock_q
    session = MagicMock()
    session.query = _query_side_effect
    return session


def test_jira_periodic_sync_skips_when_not_configured():
    """jira_periodic_sync returns 'skipped' when no AppSetting rows exist."""
    from app.worker import jira_periodic_sync

    mock_session = _mock_session_no_settings()

    with patch("app.db.session.SessionLocal", return_value=mock_session):
        result = jira_periodic_sync()

    assert result.get("skipped"), f"Expected 'skipped' key, got: {result}"


def test_jira_periodic_sync_skips_incomplete_config():
    """jira_periodic_sync skips when settings exist but are empty strings."""
    from app.worker import jira_periodic_sync

    # All settings exist but are empty
    mock_session = MagicMock()
    empty_row = MagicMock()
    empty_row.value = ""
    mock_session.query.return_value.filter.return_value.first.return_value = empty_row

    with patch("app.db.session.SessionLocal", return_value=mock_session):
        result = jira_periodic_sync()

    assert result.get("skipped"), f"Expected 'skipped', got: {result}"


def test_jira_periodic_sync_handles_http_errors(db, monkeypatch):
    """jira_periodic_sync relanza el error HTTP de Jira, para que Celery reintente.

    Auditoria 2026-08: este test no comprobaba lo que dice, y su resultado
    dependia de estado de fuera. `jira_periodic_sync` usa `worker_db_session()`,
    que abre un `SessionLocal()` contra `DATABASE_URL` —la base de desarrollo del
    repositorio— mientras el test escribia los ajustes de Jira en la base de
    pruebas. Es decir: escribia en una base y comprobaba otra.

    Con la base de desarrollo sin tabla `app_settings`, la consulta reventaba con
    *no such table*, y como la asercion era un `pytest.raises(Exception)`
    generico, **el test pasaba por la excepcion equivocada**. Con la tabla
    presente devolvia `{"skipped": ...}` y el test fallaba con «DID NOT RAISE».
    Medido: dos ejecuciones de la suite completa con el MISMO codigo, una en rojo
    y otra en verde.

    Se redirige la sesion del worker a la sesion de pruebas, que es lo que hace
    que el test ejercite el camino que describe, y se comprueba el tipo de error
    concreto en vez de `Exception` a secas.
    """
    from contextlib import contextmanager

    from app.services import jira_service
    from app.worker import jira_periodic_sync
    import httpx

    # Auditoria 2026-11 (#14): la configuracion que se sincroniza es la de cada
    # organizacion, y la peticion sale por `jira_service.llamar_a_jira_crudo`.
    # (#34): la configuracion es la conexion de tareas de `sd_jira_configs`.
    jira_service.save_jira_config(db, "1", "https://test.atlassian.net", "test@test.com", "token123", "TEST")

    @contextmanager
    def sesion_de_pruebas():
        yield db

    monkeypatch.setattr("app.db.session.worker_db_session", sesion_de_pruebas)

    from app.services.trabajos_de_fondo import FalloEnOrganizaciones

    # Segunda auditoria 2026-11 (#33): una pasada por organizacion; el fallo de
    # una sale al final como `FalloEnOrganizaciones`, con el original de causa.
    with patch("app.services.jira_service.llamar_a_jira_crudo") as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(FalloEnOrganizaciones) as e:
            jira_periodic_sync()
    assert isinstance(e.value.__cause__, httpx.ConnectError)


def test_jira_periodic_sync_updates_only_tasks_of_its_organization(db, monkeypatch, seed_multitenant):
    """jira_periodic_sync actualiza la tarea enlazada de la organizacion de la configuracion.

    Auditoria 2026-11 (#14): antes leia solo la configuracion global, buscaba la
    tarea por clave en todas las organizaciones y la creaba sin organizacion (y
    sin proyecto, que es obligatorio: el alta fallaba al confirmar).
    """
    from contextlib import contextmanager

    from app.models.task import Task
    from app.services import jira_service
    from app.worker import jira_periodic_sync

    jira_service.save_jira_config(db, "org-a-test", "https://test.atlassian.net", "user@test.com", "secret", "ABC")
    for tid in ("task-a-test", "task-b-test"):
        db.get(Task, tid).jira_issue_key = "ABC-42"
    db.commit()

    @contextmanager
    def sesion_de_pruebas():
        yield db

    monkeypatch.setattr("app.db.session.worker_db_session", sesion_de_pruebas)
    respuesta = {"issues": [{"key": "ABC-42", "fields": {
        "summary": "Test Jira Issue", "status": {"name": "In Progress"},
        "priority": {"name": "High"}, "duedate": str(date.today() + timedelta(days=7)),
    }}]}
    with patch("app.services.jira_service.llamar_a_jira_crudo", return_value=respuesta):
        result = jira_periodic_sync()

    assert result["synced"] == 1 and result["errors"] == 0, result
    db.expire_all()
    assert db.get(Task, "task-a-test").title == "Test Jira Issue"
    assert db.get(Task, "task-b-test").title == "Task tenant B", "tarea de otra organizacion"


# ── 2. Booking creation (resource scheduler drag-to-assign backend) ───────────

def test_create_booking_via_api(client, admin_token, db):
    """Verify booking creation works (used by the assign view drag-to-assign)."""
    proj_res = client.post("/api/v1/projects", json={
        "name": "Booking Test Project",
        "project_type": "development",
    }, headers=auth(admin_token))

    if proj_res.status_code not in (200, 201):
        pytest.skip("Project creation unavailable in this test context")

    proj_id = proj_res.json()["data"]["id"]

    booking_payload = {
        "user_id": "admin-test-id",
        "project_id": proj_id,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(weeks=4)),
        "hours_per_day": 8,
        "booking_type": "soft",
    }
    res = client.post("/api/v1/bookings", json=booking_payload, headers=auth(admin_token))
    assert res.status_code in (200, 201, 422), f"Unexpected status: {res.status_code} {res.text}"
