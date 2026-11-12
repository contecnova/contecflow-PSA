import logging

from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.services.ai_copilot_service import get_ai_gantt_suggestions
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.core.errores import ErrorDeDominio

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/projects/{project_id}/gantt-suggestions", summary="Get Gantt suggestions")
def get_gantt_suggestions(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return APIResponse.ok(data=get_ai_gantt_suggestions(project_id, db))
    except (HTTPException, ErrorDeDominio):
        raise  # preserve the original status/detail
    except Exception:
        logger.exception("Gantt suggestions failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail="Error generating gantt suggestions")
