from fastapi import APIRouter

router = APIRouter()

@router.get("/tasks/ping", tags=["Projects"])
def ping_projects_tasks():
    return {"msg": "pong from projects tasks"}
