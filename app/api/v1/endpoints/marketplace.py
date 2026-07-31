from fastapi import APIRouter, status, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User

router = APIRouter()

# List marketplace connectors
@router.get("", status_code=status.HTTP_200_OK)
def list_marketplace(user=Depends(get_current_user)):
    return APIListResponse.ok(items=[])

# Filter marketplace connectors
@router.get("/filter", status_code=status.HTTP_200_OK)
def list_marketplace_filter(user=Depends(get_current_user)):
    return APIListResponse.ok(items=[])

# Certified connectors
@router.get("/certified", status_code=status.HTTP_200_OK)
def list_marketplace_certified(user=Depends(get_current_user)):
    return APIListResponse.ok(items=[])

# Install connector
@router.post("/install", status_code=status.HTTP_201_CREATED)
def install_connector(user=Depends(get_current_user)):
    return APIResponse.ok(data={"result": "ok"})

# List installed instances
@router.get("/instances", status_code=status.HTTP_200_OK)
def list_installed_instances(user=Depends(get_current_user)):
    return APIListResponse.ok(items=[])

# Uninstall integration
@router.delete("/uninstall", status_code=status.HTTP_200_OK)
def uninstall_integration(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    enforce_abac(db, user, "marketplace_integration", str(user.id), action="delete")
    return APIResponse.ok(data={"result": "ok"})
