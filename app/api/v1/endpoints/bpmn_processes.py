"""
bpmn_processes.py — REST API for the BPMN Process Registry.

Endpoints:
  GET    /bpmn-processes                                  — list (with filters)
  POST   /bpmn-processes                                  — create new process
  GET    /bpmn-processes/catalogue                        — preview seed catalogue
  POST   /bpmn-processes/seed                             — seed all catalogued processes
  GET    /bpmn-processes/{id}                             — get one (latest version XML included)
  PATCH  /bpmn-processes/{id}                             — update metadata
  DELETE /bpmn-processes/{id}                             — delete (custom only)
  POST   /bpmn-processes/{id}/duplicate                   — duplicate
  POST   /bpmn-processes/{id}/versions                    — save new BPMN XML version
  GET    /bpmn-processes/{id}/versions                    — list versions
  GET    /bpmn-processes/{id}/versions/{version}          — get a specific version XML
  POST   /bpmn-processes/{id}/versions/{version}/publish  — publish a version
"""
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.db.session import get_db
from app.models.bpmn_process import BPMNProcess
from app.models.user import User
import app.services.bpmn_process_service as svc

router = APIRouter(tags=["BPMN Processes"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ProcessIn(BaseModel):
    name: str
    key: Optional[str] = None
    category: str
    description: Optional[str] = None
    icon: Optional[str] = None
    bpmn_xml: Optional[str] = None


class ProcessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class VersionIn(BaseModel):
    bpmn_xml: str
    notes: Optional[str] = None


class DuplicateIn(BaseModel):
    new_name: str


class SeedIn(BaseModel):
    force: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return s.strip("_")[:120] or "process"


def _ensure_unique_key(db: Session, key: str, organization_id: Optional[str]) -> str:
    base = key
    n = 1
    while (db.query(BPMNProcess)
            .filter(BPMNProcess.key == key,
                    BPMNProcess.organization_id == organization_id).first()):
        n += 1
        key = f"{base}_{n}"
    return key


# ── List & catalogue ──────────────────────────────────────────────────────────
@router.get("", summary="List BPMN processes")
def list_processes(
    category: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    procs = svc.list_processes(db, organization_id=org_id, category=category,
                               include_inactive=include_inactive)
    return [svc.serialize_process(p) for p in procs]


@router.get("/catalogue", summary="Preview the seed catalogue")
def get_catalogue(_: User = Depends(get_current_user)):
    return [
        {"key": e["key"], "name": e["name"], "category": e["category"],
         "icon": e.get("icon"), "description": e.get("description"),
         "steps": e["steps"]}
        for e in svc.PROCESS_CATALOGUE
    ]


@router.post("/seed", summary="Seed every catalogued process for the current org")
def seed_processes(
    payload: SeedIn = Body(default=SeedIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.seed_catalogue(db, organization_id=org_id, force=payload.force)


# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.post("", summary="Create a new BPMN process")
def create_process(
    payload: ProcessIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    org_id = getattr(current_user, "organization_id", None)
    key = payload.key or _slugify(payload.name)
    key = _ensure_unique_key(db, key, org_id)
    proc = svc.create_process(
        db, name=payload.name, category=payload.category, key=key,
        description=payload.description, icon=payload.icon,
        bpmn_xml=payload.bpmn_xml, organization_id=org_id,
        created_by_user_id=current_user.id, is_seeded=False, source_kind="custom",
    )
    return svc.serialize_process(proc, include_versions=True)


@router.get("/{process_id}", summary="Get a BPMN process with latest XML")
def get_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = svc.get_process(db, process_id)
    if not proc:
        raise HTTPException(404, "Process not found")
    latest = svc.get_latest_version(db, process_id)
    out = svc.serialize_process(proc, include_versions=True)
    out["latest"] = svc.serialize_version(latest) if latest else None
    return out


@router.patch("/{process_id}", summary="Update process metadata")
def update_process(
    process_id: str,
    payload: ProcessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    proc = svc.update_metadata(db, process_id, **payload.model_dump(exclude_none=True))
    if not proc:
        raise HTTPException(404, "Process not found")
    return svc.serialize_process(proc)


@router.delete("/{process_id}", summary="Delete a process (custom only)")
def delete_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    proc = svc.get_process(db, process_id)
    if not proc:
        raise HTTPException(404, "Process not found")
    if proc.is_seeded:
        raise HTTPException(400, "Seeded processes cannot be deleted; archive instead.")
    enforce_abac(db, current_user, "bpmn_process", process_id, action="delete")
    svc.delete_process(db, process_id)
    return {"ok": True, "message": "Proceso BPMN eliminado correctamente"}


@router.post("/{process_id}/duplicate", summary="Duplicate a process")
def duplicate_process(
    process_id: str,
    payload: DuplicateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    proc = svc.duplicate_process(db, process_id, new_name=payload.new_name,
                                  created_by_user_id=current_user.id)
    if not proc:
        raise HTTPException(404, "Source process not found")
    return svc.serialize_process(proc, include_versions=True)


# ── Versions ──────────────────────────────────────────────────────────────────
@router.post("/{process_id}/versions", summary="Save a new BPMN XML version")
def save_version(
    process_id: str,
    payload: VersionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    proc = svc.get_process(db, process_id)
    if not proc:
        raise HTTPException(404, "Process not found")
    v = svc.save_new_version(db, process_id=process_id, bpmn_xml=payload.bpmn_xml,
                             notes=payload.notes, created_by_user_id=current_user.id)
    return svc.serialize_version(v)


@router.get("/{process_id}/versions", summary="List versions of a process")
def list_versions(
    process_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proc = svc.get_process(db, process_id)
    if not proc:
        raise HTTPException(404, "Process not found")
    return [svc.serialize_version(v, include_xml=False) for v in proc.versions]


@router.get("/{process_id}/versions/{version}", summary="Get a specific version (with XML)")
def get_version(
    process_id: str,
    version: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    v = svc.get_version(db, process_id, version)
    if not v:
        raise HTTPException(404, "Version not found")
    return svc.serialize_version(v)


@router.post("/{process_id}/versions/{version}/publish", summary="Publish a version")
def publish_version(
    process_id: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    v = svc.publish_version(db, process_id, version)
    if not v:
        raise HTTPException(404, "Version not found")
    return svc.serialize_version(v)
