from fastapi import APIRouter

router = APIRouter()

@router.get("/users/ping", tags=["Admin"])
def ping_admin_users():
    return {"msg": "pong from admin users"}
