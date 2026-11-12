import logging

from fastapi import APIRouter, status, Depends, HTTPException
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.services.ai_copilot_service import get_ai_gantt_suggestions, get_ai_timesheet_anomalies
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.errores import ErrorDeDominio

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/gantt/{project_id}", status_code=status.HTTP_200_OK)
def gantt_suggestions(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return APIResponse.ok(data=get_ai_gantt_suggestions(project_id, db, current_user=user))
    except (HTTPException, ErrorDeDominio):
        raise  # preserve the original status/detail
    except Exception:
        logger.exception("AI gantt suggestions failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail="Error generating gantt suggestions")

@router.get("/timesheets/{user_id}", status_code=status.HTTP_200_OK)
def timesheet_anomalies(user_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return APIResponse.ok(data=get_ai_timesheet_anomalies(user_id, db, current_user=user))
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception:
        logger.exception("AI timesheet anomalies failed for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Error analysing timesheet anomalies")
