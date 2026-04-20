from fastapi import APIRouter, status, Depends
from app.api.deps import get_current_user

router = APIRouter()

@router.get("/gantt/{project_id}", status_code=status.HTTP_200_OK)
def gantt_suggestions(project_id: str, user=Depends(get_current_user)):
    # Dummy: always return 2 suggestions
    return [
        {"type": "overdue", "task_id": "tsk-1", "message": "Task is overdue"},
        {"type": "empty", "task_id": "tsk-2", "message": "No tasks in project"}
    ]

@router.get("/timesheets/{user_id}", status_code=status.HTTP_200_OK)
def timesheet_anomalies(user_id: str, user=Depends(get_current_user)):
    # Dummy: always return 1 anomaly
    return {"anomalies": [{"type": "high_hours", "day": "2026-04-20", "hours": 12}]}
