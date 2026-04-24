from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import get_current_user
from app.services.ai_copilot_service import get_ai_gantt_suggestions
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User

router = APIRouter()

@router.get("/projects/{project_id}/gantt-suggestions", summary="Get Gantt suggestions")
def get_gantt_suggestions(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return get_ai_gantt_suggestions(project_id, db)
    except HTTPException as e:
        if e.status_code == 404:
            raise
        raise HTTPException(status_code=500, detail=str(e))
