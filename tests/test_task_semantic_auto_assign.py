from app.models.project import Project, ProjectType, ProjectStatus, ProjectMember
from app.models.semantic_engine import SemConfig
from app.models.user import User
from app.schemas.tasks import TaskCreate
from app.services.task_service import create_task_record


def _make_project(db, pm_id: str) -> Project:
    project = Project(
        id="proj-sem-auto-1",
        organization_id="1",
        code="PRJ-SEM-AUTO-1",
        name="Semantic Auto Assign Project",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        pm_id=pm_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_task_auto_assign_enabled_assigns_on_create(db, monkeypatch):
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    project = _make_project(db, pm_id=pm.id)

    db.add(ProjectMember(project_id=project.id, user_id=pm.id))
    db.add(SemConfig(auto_assign_tasks=True, auto_assign_tickets=False, threshold_task=0.6))
    db.commit()

    def _fake_suggest(self, title, description, candidate_user_ids, priority="medium"):
        _ = (title, description, priority)
        assert pm.id in candidate_user_ids
        return {
            "suggested_user_id": pm.id,
            "confidence": 0.9,
            "needs_review": False,
            "engine_mode": "semantic",
            "top_scores": {pm.id: 0.9},
            "reasoning": "test",
        }

    monkeypatch.setattr("app.services.task_service.SemanticAssigner.suggest_for_task", _fake_suggest)

    payload = TaskCreate(
        title="Task semantic auto-assign",
        description="Should auto assign",
        project_id=project.id,
    )
    task = create_task_record(db, payload, admin)

    assert task.assignee_id == pm.id


def test_task_auto_assign_disabled_does_not_assign(db, monkeypatch):
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    project = _make_project(db, pm_id=pm.id)

    db.add(ProjectMember(project_id=project.id, user_id=pm.id))
    db.add(SemConfig(auto_assign_tasks=False, auto_assign_tickets=False, threshold_task=0.6))
    db.commit()

    def _fake_suggest(self, title, description, candidate_user_ids, priority="medium"):
        _ = (title, description, candidate_user_ids, priority)
        return {
            "suggested_user_id": pm.id,
            "confidence": 0.9,
            "needs_review": False,
            "engine_mode": "semantic",
            "top_scores": {pm.id: 0.9},
            "reasoning": "test",
        }

    monkeypatch.setattr("app.services.task_service.SemanticAssigner.suggest_for_task", _fake_suggest)

    payload = TaskCreate(
        title="Task no auto-assign",
        description="Should remain unassigned",
        project_id=project.id,
    )
    task = create_task_record(db, payload, admin)

    assert task.assignee_id is None


def test_task_auto_assign_enabled_but_needs_review_keeps_unassigned(db, monkeypatch):
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    project = _make_project(db, pm_id=pm.id)

    db.add(ProjectMember(project_id=project.id, user_id=pm.id))
    db.add(SemConfig(auto_assign_tasks=True, auto_assign_tickets=False, threshold_task=0.6))
    db.commit()

    def _fake_suggest(self, title, description, candidate_user_ids, priority="medium"):
        _ = (title, description, candidate_user_ids, priority)
        return {
            "suggested_user_id": pm.id,
            "confidence": 0.45,
            "needs_review": True,
            "engine_mode": "semantic",
            "top_scores": {pm.id: 0.45},
            "reasoning": "below threshold",
        }

    monkeypatch.setattr("app.services.task_service.SemanticAssigner.suggest_for_task", _fake_suggest)

    payload = TaskCreate(
        title="Task needs review",
        description="Should not auto assign",
        project_id=project.id,
    )
    task = create_task_record(db, payload, admin)

    assert task.assignee_id is None
