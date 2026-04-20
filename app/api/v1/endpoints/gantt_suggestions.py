from fastapi import APIRouter, Depends, status, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/projects/{project_id}/gantt-suggestions", summary="Get Gantt suggestions")
def get_gantt_suggestions(project_id: str, current_user: User = Depends(get_current_user)):
    # Stub: return minimal suggestions for test contract
    return {"suggestions": [], "suggestions_count": 0}
