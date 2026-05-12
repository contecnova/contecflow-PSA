from fastapi import APIRouter, status, Depends, HTTPException
from app.api.deps import get_current_user
from app.services.ai_copilot_service import get_ai_gantt_suggestions, get_ai_timesheet_anomalies
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/gantt/{project_id}", status_code=status.HTTP_200_OK)
def gantt_suggestions(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return get_ai_gantt_suggestions(project_id, db, current_user=user)
    except HTTPException as e:
        if e.status_code == 404:
            raise
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/timesheets/{user_id}", status_code=status.HTTP_200_OK)
def timesheet_anomalies(user_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return get_ai_timesheet_anomalies(user_id, db)
    except HTTPException as e:
        if e.status_code == 404:
            raise
        raise HTTPException(status_code=500, detail=str(e))
