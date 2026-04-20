from fastapi import APIRouter, Depends, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

_pipeline_failures: list = []


@router.post("/cicd/pipeline", summary="Trigger CI/CD pipeline")
def trigger_pipeline(
    payload: dict = Body(default={}),
    current_user: User = Depends(get_current_user),
):
    if payload.get("status") == "failed":
        # Añadir job y status explícitamente para asegurar que la alerta se registre correctamente
        _pipeline_failures.append({"job": payload.get("job", ""), "status": payload.get("status", "")})
    return {"ok": True, "pipeline_id": "pipeline-123", **payload}


@router.get("/cicd/alerts", summary="Get CI/CD pipeline alerts")
def get_cicd_alerts(current_user: User = Depends(get_current_user)):
    # Devolver lista de alertas con job y status
    return _pipeline_failures
