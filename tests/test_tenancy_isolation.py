"""org_scoped_or_404 — the shared cross-tenant isolation gate used by the
service_desk / integrations routers (Jira config, workflow blueprints, CMDB
discovery, AI ticket actions). A row from another org must look like a 404.
"""
import pytest
from fastapi import HTTPException

from app.core.tenancy import org_scoped_or_404, assert_same_org
from app.models.workflow_designer import WorkflowBlueprint
from app.core.errores import ErrorDeDominio


class _User:
    def __init__(self, org, is_superadmin=False):
        self.organization_id = org
        self.is_superadmin = is_superadmin


def _mk_blueprint(db, org_id):
    # Auditoria 2026-08: `fila_global` para el caso `org_id=None`. Desde que la
    # suite corre con la semantica de produccion, el sellado del `flush` rellena
    # la organizacion de la sesion en toda fila nueva que venga con None — que
    # es justo lo contrario de lo que quiere probar `test_null_org_row_is_global`.
    from contextlib import nullcontext
    from tests.conftest import fila_global

    with (fila_global(db) if org_id is None else nullcontext()):
        bp = WorkflowBlueprint(name="BP", process_type="ticket", organization_id=org_id)
        db.add(bp)
        db.commit()
    db.refresh(bp)
    return bp


def test_same_org_row_is_returned(db):
    bp = _mk_blueprint(db, "org-A")
    got = org_scoped_or_404(db, WorkflowBlueprint, bp.id, _User("org-A"))
    assert got.id == bp.id


def test_other_org_row_is_404(db):
    bp = _mk_blueprint(db, "org-A")
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        org_scoped_or_404(db, WorkflowBlueprint, bp.id, _User("org-B"))
    assert exc.value.status_code == 404


def test_missing_row_is_404(db):
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        org_scoped_or_404(db, WorkflowBlueprint, "does-not-exist", _User("org-A"))
    assert exc.value.status_code == 404


def test_superadmin_bypasses_org(db):
    bp = _mk_blueprint(db, "org-A")
    got = org_scoped_or_404(db, WorkflowBlueprint, bp.id, _User("org-Z", is_superadmin=True))
    assert got.id == bp.id


def test_null_org_row_is_global(db):
    bp = _mk_blueprint(db, None)
    got = org_scoped_or_404(db, WorkflowBlueprint, bp.id, _User("org-A"))
    assert got.id == bp.id


def test_assert_same_org_raises_on_mismatch():
    with pytest.raises((HTTPException, ErrorDeDominio)):
        assert_same_org(_User("org-A"), "org-B")
    # matching / null / superadmin pass silently
    assert_same_org(_User("org-A"), "org-A")
    assert_same_org(_User("org-A"), None)
    assert_same_org(_User("org-Z", is_superadmin=True), "org-B")
