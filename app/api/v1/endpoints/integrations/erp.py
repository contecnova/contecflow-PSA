from fastapi import APIRouter

router = APIRouter()

@router.get("/erp/ping", tags=["Integrations"])
def ping_integrations_erp():
    return {"msg": "pong from integrations erp"}
