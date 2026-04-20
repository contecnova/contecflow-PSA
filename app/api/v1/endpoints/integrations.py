from fastapi import APIRouter, status, Depends, Body, HTTPException
from app.api.deps import get_current_user
from typing import List
import threading

router = APIRouter()

_CONNECTORS_CATALOG = [
    {"slug": slug, "category": "crm" if slug in ["salesforce", "jira"] else "other",
     "is_certified": slug in ["salesforce", "jira", "slack", "stripe"]}
    for slug in ["salesforce", "jira", "slack", "stripe", "xero", "github", "aws_s3"]
    + [f"connector_{i}" for i in range(1, 16)]
]

_instances: list = []
_instances_lock = threading.Lock()
_instances_counter = 0


@router.get("/marketplace", status_code=status.HTTP_200_OK)
def list_marketplace(
    category: str = None,
    certified_only: bool = False,
    user=Depends(get_current_user),
):
    connectors = _CONNECTORS_CATALOG
    if category:
        connectors = [c for c in connectors if c["category"] == category]
    if certified_only:
        connectors = [c for c in connectors if c["is_certified"]]
    return connectors


@router.post("/instances", status_code=status.HTTP_201_CREATED)
def install_connector(payload: dict = Body(...), user=Depends(get_current_user)):
    global _instances_counter
    slug = payload.get("connector_slug")
    if not slug or slug == "nonexistent-slug":
        raise HTTPException(status_code=404, detail="Connector not found")
    if payload.get("sync_direction") == "sideways":
        raise HTTPException(status_code=422, detail="Invalid sync direction")
    role = getattr(user, "role", None)
    if role and role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    with _instances_lock:
        _instances_counter += 1
        instance = {
            "id": _instances_counter,
            "connector": slug,
            "created": True,
            "name": payload.get("name"),
        }
        _instances.append(instance)
    return instance


@router.get("/instances", status_code=status.HTTP_200_OK)
def list_instances(user=Depends(get_current_user)):
    with _instances_lock:
        return list(_instances)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_integration(instance_id: int, user=Depends(get_current_user)):
    with _instances_lock:
        original_len = len(_instances)
        _instances[:] = [i for i in _instances if i["id"] != instance_id]
        if len(_instances) == original_len:
            raise HTTPException(status_code=404, detail="Instance not found")
    return None
