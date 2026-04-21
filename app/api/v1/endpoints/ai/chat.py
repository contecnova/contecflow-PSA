from fastapi import APIRouter

router = APIRouter()

@router.get("/chat/ping", tags=["AI"])
def ping_ai_chat():
    return {"msg": "pong from ai chat"}
