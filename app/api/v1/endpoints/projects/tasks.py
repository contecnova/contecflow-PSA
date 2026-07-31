from fastapi import APIRouter

from app.core.responses import APIResponse

router = APIRouter()

@router.get("/tasks/ping", tags=["Projects"])
def ping_projects_tasks():
    return APIResponse.ok(data={"msg": "pong from projects tasks"})
