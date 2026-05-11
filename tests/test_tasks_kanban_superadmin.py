"""Regresión: el kanban devolvía 404 'Proyecto no encontrado' cuando un
superadmin de una organización distinta intentaba ver proyectos de otra
tenancy. La causa: project_for_user / task_query_for_user filtraban por
organization_id sin honrar el flag is_superadmin (otros servicios como
pipeline/approval/ai_provider sí lo respetaban).
"""
from tests.conftest import auth


def _new_org_with_project(db, *, org_id="other-org-test", project_id="other-org-proj-test"):
    """Crea una org distinta a la del admin del fixture, con un proyecto dentro."""
    from app.models.mfa import Organization
    from app.models.project import Project, ProjectStatus, ProjectType

    if not db.query(Organization).filter(Organization.id == org_id).first():
        db.add(Organization(id=org_id, name="Other Tenant", slug="other-tenant", is_active=True))
    if not db.query(Project).filter(Project.id == project_id).first():
        db.add(Project(
            id=project_id,
            organization_id=org_id,
            code="OTH-001",
            name="Proyecto en otra org",
            project_type=ProjectType.internal,
            status=ProjectStatus.active,
        ))
    db.commit()
    return org_id, project_id


def test_project_for_user_superadmin_bypasses_org_filter(db):
    """project_for_user devuelve proyectos de cualquier org cuando is_superadmin."""
    from app.services.tasks.queries import project_for_user
    from app.models.user import User
    _, project_id = _new_org_with_project(db)

    admin = db.query(User).filter(User.username == "admin").first()
    admin.is_superadmin = True
    db.commit()

    p = project_for_user(db, project_id, admin)
    assert p is not None, "El superadmin debería poder ver el proyecto de otra org"
    assert p.id == project_id


def test_project_for_user_non_super_still_isolated(db):
    """Sin is_superadmin, el aislamiento por organización se mantiene."""
    from app.services.tasks.queries import project_for_user
    from app.models.user import User
    _, project_id = _new_org_with_project(db)

    dev = db.query(User).filter(User.username == "dev_test").first()
    dev.is_superadmin = False  # explícito
    db.commit()

    p = project_for_user(db, project_id, dev)
    assert p is None, "Un user no-super NO debe ver proyectos de otra org"


def test_kanban_endpoint_works_for_superadmin_cross_org(client, admin_token, db):
    """End-to-end: GET /api/v1/tasks/kanban/{project_id} responde 200
    para un superadmin que intenta ver el kanban de un proyecto en otra org."""
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    admin.is_superadmin = True
    db.commit()

    _, project_id = _new_org_with_project(db)
    res = client.get(f"/api/v1/tasks/kanban/{project_id}",
                     headers=auth(admin_token))
    # Antes de la fix: 404 "Proyecto no encontrado"
    assert res.status_code == 200, res.text
    # El kanban devuelve un dict con columnas por status
    body = res.json()
    assert isinstance(body, dict)
    assert "todo" in body or "backlog" in body or len(body) > 0


def test_kanban_endpoint_still_forbidden_cross_org_non_super(client, dev_token, db):
    """Un user no-super sigue recibiendo 404 al intentar acceder cross-org."""
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    dev.is_superadmin = False
    db.commit()

    _, project_id = _new_org_with_project(db)
    res = client.get(f"/api/v1/tasks/kanban/{project_id}",
                     headers=auth(dev_token))
    assert res.status_code == 404
