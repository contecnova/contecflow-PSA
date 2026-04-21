from fastapi import APIRouter

router = APIRouter()

@router.get("/reports/ping", tags=["Billing"])
def ping_billing_reports():
    return {"msg": "pong from billing reports"}
