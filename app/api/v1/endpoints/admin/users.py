from fastapi import APIRouter

from app.core.responses import APIResponse

router = APIRouter()

@router.get("/users/ping", tags=["Admin"])
def ping_admin_users():
    return APIResponse.ok(data={"msg": "pong from admin users"})
