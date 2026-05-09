"""
Test soft-delete pattern consistency across 4 critical resource types:
- Workflow States + Transitions
- Deliverables
- Imputations
"""
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.models.custom_fields import WorkflowState, WorkflowTransition
from app.models.resources import Deliverable, DeliverableStatus
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.user import User
from app.services.custom_fields_service import delete_workflow_state, delete_transition, get_workflow
from app.services.deliverable_service import delete_deliverable, get_deliverable, list_project_deliverables
from app.services.imputation_service import delete_imputation_record, get_imputation_by_id
from datetime import date


class TestWorkflowSoftDelete:
    """Workflow State and Transition soft-delete tests"""

    def test_workflow_state_soft_delete(self, db: Session, test_project: Project, test_user: User):
        """Verify workflow state is soft-deleted (not hard-deleted)"""
        # Create state
        state = WorkflowState(
            project_id=test_project.id,
            name="Test State",
            value="test_state",
            is_active=True
        )
        db.add(state)
        db.commit()
        state_id = state.id

        # Soft-delete via service
        result = delete_workflow_state(test_project.id, state_id, db)
        assert result["ok"] is True

        # Verify soft-deleted (is_active = False, but record exists)
        deleted_state = db.query(WorkflowState).filter(WorkflowState.id == state_id).first()
        assert deleted_state is not None, "State should still exist in DB"
        assert deleted_state.is_active is False, "State should be marked inactive"

        # Verify list_workflow excludes inactive states
        workflow = get_workflow(test_project.id, db)
        state_ids = [s["id"] for s in workflow["states"]]
        assert state_id not in state_ids, "Deleted state should not appear in listing"

    def test_workflow_transition_soft_delete(self, db: Session, test_project: Project, test_user: User):
        """Verify workflow transition is soft-deleted"""
        # Create two states
        s1 = WorkflowState(project_id=test_project.id, name="S1", value="s1", is_active=True)
        s2 = WorkflowState(project_id=test_project.id, name="S2", value="s2", is_active=True)
        db.add_all([s1, s2])
        db.commit()

        # Create transition
        trans = WorkflowTransition(
            project_id=test_project.id,
            from_state_id=s1.id,
            to_state_id=s2.id,
            is_active=True
        )
        db.add(trans)
        db.commit()
        trans_id = trans.id

        # Soft-delete via service
        result = delete_transition(test_project.id, trans_id, db)
        assert result["ok"] is True

        # Verify soft-deleted
        deleted_trans = db.query(WorkflowTransition).filter(WorkflowTransition.id == trans_id).first()
        assert deleted_trans is not None
        assert deleted_trans.is_active is False

        # Verify not in workflow listing
        workflow = get_workflow(test_project.id, db)
        for state in workflow["states"]:
            trans_ids = [t["id"] for t in state.get("transitions_from", [])]
            assert trans_id not in trans_ids

    def test_workflow_state_prevents_duplicate_in_active(self, db: Session, test_project: Project, test_user: User):
        """Verify cannot create duplicate active states with same value"""
        state1 = WorkflowState(
            project_id=test_project.id,
            name="State",
            value="state",
            is_active=True
        )
        db.add(state1)
        db.commit()

        # Try to create duplicate
        from fastapi import HTTPException
        from app.schemas.custom_fields import WorkflowStateIn

        with pytest.raises(HTTPException) as exc_info:
            payload = WorkflowStateIn(name="State 2", value="state")
            from app.services.custom_fields_service import create_workflow_state
            create_workflow_state(test_project.id, payload, db)
        assert exc_info.value.status_code == 400


class TestDeliverableSoftDelete:
    """Deliverable soft-delete tests"""

    def test_deliverable_soft_delete(self, db: Session, test_project: Project, test_user: User):
        """Verify deliverable is soft-deleted"""
        # Create deliverable
        deliv = Deliverable(
            project_id=test_project.id,
            code="DEL-001",
            name="Test Deliverable",
            status=DeliverableStatus.planned,
            is_active=True
        )
        db.add(deliv)
        db.commit()
        deliv_id = deliv.id

        # Soft-delete
        delete_deliverable(db, deliv)

        # Verify soft-deleted
        result = db.query(Deliverable).filter(Deliverable.id == deliv_id).first()
        assert result is not None
        assert result.is_active is False

        # Verify not in list
        delivs = list_project_deliverables(db, test_project.id)
        deliv_ids = [d.id for d in delivs]
        assert deliv_id not in deliv_ids

    def test_deliverable_get_filters_inactive(self, db: Session, test_project: Project, test_user: User):
        """Verify get_deliverable filters by is_active"""
        deliv = Deliverable(
            project_id=test_project.id,
            code="DEL-002",
            name="Test",
            status=DeliverableStatus.planned,
            is_active=False
        )
        db.add(deliv)
        db.commit()

        # Should not be found
        result = get_deliverable(db, deliv.id, test_project.id)
        assert result is None


class TestImputationSoftDelete:
    """Imputation soft-delete tests"""

    def test_imputation_soft_delete(self, db: Session, test_project: Project, test_user: User):
        """Verify imputation is soft-deleted"""
        imp = Imputation(
            user_id=test_user.id,
            project_id=test_project.id,
            date=date.today(),
            hours=8.0,
            is_active=True
        )
        db.add(imp)
        db.commit()
        imp_id = imp.id

        # Soft-delete
        delete_imputation_record(db, imp)

        # Verify soft-deleted
        result = db.query(Imputation).filter(Imputation.id == imp_id).first()
        assert result is not None
        assert result.is_active is False

        # Verify not retrievable
        retrieved = get_imputation_by_id(db, imp_id)
        assert retrieved is None

    def test_imputation_list_filters_inactive(self, db: Session, test_project: Project, test_user: User):
        """Verify list queries filter by is_active"""
        from app.services.imputation_service import get_week_summary

        imp1 = Imputation(
            user_id=test_user.id,
            project_id=test_project.id,
            date=date.today(),
            hours=8.0,
            is_active=True
        )
        imp2 = Imputation(
            user_id=test_user.id,
            project_id=test_project.id,
            date=date.today(),
            hours=4.0,
            is_active=False  # Soft-deleted
        )
        db.add_all([imp1, imp2])
        db.commit()

        # Get week summary should only include active
        summary = get_week_summary(None, test_user, db)
        assert summary.total_hours == 8.0, "Should only count active imputations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
