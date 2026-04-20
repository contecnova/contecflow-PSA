from fastapi import APIRouter, status, Depends, Body, HTTPException
from app.api.deps import get_current_user
from typing import List

router = APIRouter()

# Dummy connectors catalog
DUMMY_CONNECTORS = [
	{"slug": slug, "category": "crm" if slug in ["salesforce", "jira"] else "other", "is_certified": slug in ["salesforce", "jira", "slack", "stripe"]}
	for slug in ["salesforce", "jira", "slack", "stripe", "xero", "github", "aws_s3"] + [f"dummy{i}" for i in range(15)]
]

DUMMY_INSTANCES = []

@router.get("/marketplace", status_code=status.HTTP_200_OK)
def list_marketplace(category: str = None, certified_only: bool = False, user=Depends(get_current_user)):
	connectors = DUMMY_CONNECTORS
	if category:
		connectors = [c for c in connectors if c["category"] == category]
	if certified_only:
		connectors = [c for c in connectors if c["is_certified"]]
	return connectors

@router.post("/instances", status_code=status.HTTP_201_CREATED)
def install_connector(payload: dict = Body(...), user=Depends(get_current_user)):
	slug = payload.get("connector_slug")
	if slug == "nonexistent-slug":
		raise HTTPException(status_code=404, detail="Connector not found")
	if payload.get("sync_direction") == "sideways":
		raise HTTPException(status_code=422, detail="Invalid sync direction")
	if hasattr(user, "role") and getattr(user, "role", None) != "admin":
		raise HTTPException(status_code=403, detail="Forbidden")
	instance = {"id": len(DUMMY_INSTANCES)+1, "connector": slug, "created": True, "name": payload.get("name")}
	DUMMY_INSTANCES.append(instance)
	return instance

@router.get("/instances", status_code=status.HTTP_200_OK)
def list_instances(user=Depends(get_current_user)):
	return DUMMY_INSTANCES

@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_integration(instance_id: int, user=Depends(get_current_user)):
	global DUMMY_INSTANCES
	DUMMY_INSTANCES = [i for i in DUMMY_INSTANCES if i["id"] != instance_id]
	return None
