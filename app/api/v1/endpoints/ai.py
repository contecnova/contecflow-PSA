from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/suggestions/gantt/{project_id}", summary="AI Gantt suggestions")
def gantt_suggestions(project_id: str, current_user: User = Depends(get_current_user)):
    # Stub: return empty suggestions
    return {"suggestions": []}

@router.get("/suggestions/timesheets/{user_id}", summary="AI Timesheet anomalies")
def timesheet_anomalies(user_id: str, current_user: User = Depends(get_current_user)):
    # Stub: return empty anomalies
    return {"anomalies": []}
