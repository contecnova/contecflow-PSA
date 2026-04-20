from fastapi import APIRouter, Depends, status, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/cicd/pipeline", summary="Trigger CI/CD pipeline")
def trigger_pipeline(current_user: User = Depends(get_current_user)):
    return {"ok": True, "pipeline_id": "pipeline-123"}
