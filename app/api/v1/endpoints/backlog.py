from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/projects/{project_id}/backlog", summary="Get project backlog")
def get_project_backlog(project_id: str, current_user: User = Depends(get_current_user)):
    # Stub: return minimal backlog for the project
    return {"project_id": project_id, "items": []}
