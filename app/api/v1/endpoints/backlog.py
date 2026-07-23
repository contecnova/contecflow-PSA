from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.deps import get_db
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.project_service import get_project_scoped_or_404
from app.services.sprint_service import serialize_task

router = APIRouter()


@router.get("/projects/{project_id}/backlog", summary="Get project backlog")
def get_project_backlog(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backlog del proyecto: tareas en estado 'backlog' (aisladas por organización).

    Ordenadas por prioridad y fecha de creación. Devuelve la lista serializada más
    el total, en vez del stub vacío anterior.
    """
    # Aísla por organización y devuelve 404 si el proyecto no es accesible.
    get_project_scoped_or_404(db, project_id, current_user)

    tasks = (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.status == TaskStatus.backlog)
        .order_by(Task.priority.desc(), Task.created_at.asc())
        .all()
    )
    items = [serialize_task(t) for t in tasks]
    return {"project_id": project_id, "items": items, "total": len(items)}
