"""
bpmn_processes.py — REST API for the BPMN Process Registry.

Endpoints:
  GET    /bpmn-processes                                  — list (with filters; `include_xml` adds the latest XML)
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
  GET    /bpmn-processes/{id}/validation                  — can the version be executed? (coded problems)
  POST   /bpmn-processes/{id}/versions/{version}/publish  — publish a version
  POST   /bpmn-processes/{id}/versions/{version}/retire   — retire a version (no new instances)
  POST   /bpmn-processes/{id}/simulate                    — dry run in memory (no database writes)

Revision BPM 2026-11-23 (docs/BPM.md): variables declaradas (`variables_schema`),
retirar versiones, simulacion, quien publica (segregacion de funciones) y
auditoria con acciones propias (PUBLISH, RETIRE).

Revision BPM 2026-11-16:
- las lecturas exigian solo `get_current_user`: un usuario del portal de
  clientes o un subcontratista leia los procesos de la organizacion. Ahora
  `require_internal_user`, como las instancias;
- los esquemas validan longitudes y el estado (`status` libre daba 500 al
  convertirlo al enum);
- cada cambio queda en la auditoria (`audit_log`).
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import requiere_capacidad
from app.core.abac_enforce import enforce_abac
from app.db.session import get_db
from app.models.bpmn_process import BPMNProcessStatus
from app.models.user import User
from app.core.responses import APIListResponse, APIResponse
from app.services import bpmn_engine as motor
from app.services.audit import auditar_y_confirmar
import app.services.bpmn_process_service as svc
from app.core.codigos_de_error import error_http

router = APIRouter(tags=["BPMN Processes"])

_CLAVE = r"^[A-Za-z0-9_.-]+$"


# ── Schemas ───────────────────────────────────────────────────────────────────
class ProcessIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    key: Optional[str] = Field(None, max_length=120, pattern=_CLAVE)
    category: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=5000)
    icon: Optional[str] = Field(None, max_length=40)
    owner: Optional[str] = Field(None, max_length=200)
    sla: Optional[str] = Field(None, max_length=120)
    bpmn_xml: Optional[str] = None
    variables_schema: Optional[list[dict]] = Field(None, max_length=200)


class ProcessUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    category: Optional[str] = Field(None, min_length=1, max_length=80)
    icon: Optional[str] = Field(None, max_length=40)
    owner: Optional[str] = Field(None, max_length=200)
    sla: Optional[str] = Field(None, max_length=120)
    status: Optional[BPMNProcessStatus] = None
    is_active: Optional[bool] = None
    variables_schema: Optional[list[dict]] = Field(None, max_length=200)


class VersionIn(BaseModel):
    bpmn_xml: str = Field(..., min_length=1)
    notes: Optional[str] = Field(None, max_length=500)


class DuplicateIn(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=255)


class SeedIn(BaseModel):
    force: bool = False


class SimulacionIn(BaseModel):
    version: Optional[int] = Field(None, ge=1)
    variables: Optional[dict] = None
    #: {id de compuerta: flow_id o [flow_ids]}
    decisions: Optional[dict] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
# Auditoria 2026-08 (hallazgo 22): la consulta vive en
# `services/bpmn_process_service.clave_unica`. El filtro por organizacion ya
# estaba y es el correcto: la unicidad de la clave es por organizacion.
_ensure_unique_key = svc.clave_unica
_slugify = svc.slugify


def _proceso_o_404(db: Session, process_id: str):
    proc = svc.get_process(db, process_id)
    if not proc:
        raise error_http(404, "no_encontrado", detail="Process not found", que="proceso")
    return proc


# ── List & catalogue ──────────────────────────────────────────────────────────
@router.get("", summary="List BPMN processes")
def list_processes(
    category: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    include_xml: bool = Query(False, description="Añade `latest_xml` (XML de la última versión) a cada proceso"),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.usar")),
):
    org_id = getattr(current_user, "organization_id", None)
    procs = svc.list_processes(db, organization_id=org_id, category=category,
                               include_inactive=include_inactive)
    xml = svc.anotar_versiones(db, procs, con_xml=include_xml)
    items = []
    for p in procs:
        item = svc.serialize_process(p)
        if include_xml:
            item["latest_xml"] = xml.get(p.id)
        items.append(item)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/catalogue", summary="Preview the seed catalogue")
def get_catalogue(_: User = Depends(requiere_capacidad("bpm.usar"))):
    items = [
        {"key": e["key"], "name": e["name"], "category": e["category"],
         "icon": e.get("icon"), "description": e.get("description"),
         "steps": e["steps"]}
        for e in svc.PROCESS_CATALOGUE
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/seed", summary="Seed every catalogued process for the current org")
def seed_processes(
    payload: SeedIn = Body(default=SeedIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    org_id = getattr(current_user, "organization_id", None)
    out = svc.seed_catalogue(db, organization_id=org_id, force=payload.force)
    auditar_y_confirmar(db, current_user, "CREATE", "bpmn_process", None, "seed", new_values=out)
    return APIResponse.ok(data=out)


# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.post("", summary="Create a new BPMN process")
def create_process(
    payload: ProcessIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    org_id = getattr(current_user, "organization_id", None)
    key = payload.key or _slugify(payload.name)
    key = _ensure_unique_key(db, key, org_id)
    proc = svc.create_process(
        db, name=payload.name.strip(), category=payload.category, key=key,
        description=payload.description, icon=payload.icon, owner=payload.owner, sla=payload.sla,
        bpmn_xml=payload.bpmn_xml, organization_id=org_id,
        created_by_user_id=current_user.id, is_seeded=False, source_kind="custom",
    )
    if payload.variables_schema:
        proc = svc.update_metadata(db, proc.id, variables_schema=payload.variables_schema)
    auditar_y_confirmar(db, current_user, "CREATE", "bpmn_process", proc.id, proc.name,
                        new_values={"key": proc.key, "category": proc.category})
    return APIResponse.ok(data=svc.serialize_process(proc, include_versions=True))


@router.get("/{process_id}", summary="Get a BPMN process with latest XML")
def get_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.usar")),
):
    proc = _proceso_o_404(db, process_id)
    latest = svc.get_latest_version(db, process_id)
    out = svc.serialize_process(proc, include_versions=True)
    out["latest"] = svc.serialize_version(latest) if latest else None
    return APIResponse.ok(data=out)


@router.patch("/{process_id}", summary="Update process metadata")
def update_process(
    process_id: str,
    payload: ProcessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    cambios = payload.model_dump(exclude_none=True)
    if "status" in cambios:
        cambios["status"] = cambios["status"].value
    proc = svc.update_metadata(db, process_id, **cambios)
    if not proc:
        raise error_http(404, "no_encontrado", detail="Process not found", que="proceso")
    auditar_y_confirmar(db, current_user, "UPDATE", "bpmn_process", proc.id, proc.name, new_values=cambios)
    return APIResponse.ok(data=svc.serialize_process(proc))


@router.delete("/{process_id}", summary="Delete a process (custom only)")
def delete_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    proc = _proceso_o_404(db, process_id)
    if proc.is_seeded:
        raise error_http(400, "proceso_semilla_no_eliminable", detail="Seeded processes cannot be deleted; archive instead.")
    enforce_abac(db, current_user, "bpmn_process", process_id, action="delete")
    nombre = proc.name
    svc.delete_process(db, process_id)
    auditar_y_confirmar(db, current_user, "DELETE", "bpmn_process", process_id, nombre)
    return APIResponse.ok(data={"ok": True, "message": "Proceso BPMN eliminado correctamente"})


@router.post("/{process_id}/duplicate", summary="Duplicate a process")
def duplicate_process(
    process_id: str,
    payload: DuplicateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    proc = svc.duplicate_process(db, process_id, new_name=payload.new_name.strip(),
                                  organization_id=getattr(current_user, "organization_id", None),
                                  created_by_user_id=current_user.id)
    if not proc:
        raise error_http(404, "no_encontrado", detail="Source process not found", que="proceso")
    auditar_y_confirmar(db, current_user, "CREATE", "bpmn_process", proc.id, proc.name,
                        new_values={"duplicated_from": process_id})
    return APIResponse.ok(data=svc.serialize_process(proc, include_versions=True))


# ── Versions ──────────────────────────────────────────────────────────────────
@router.post("/{process_id}/versions", summary="Save a new BPMN XML version")
def save_version(
    process_id: str,
    payload: VersionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    proc = _proceso_o_404(db, process_id)
    v = svc.save_new_version(db, process_id=process_id, bpmn_xml=payload.bpmn_xml,
                             notes=payload.notes, created_by_user_id=current_user.id)
    auditar_y_confirmar(db, current_user, "UPDATE", "bpmn_process", process_id, proc.name,
                        new_values={"version": v.version})
    out = svc.serialize_version(v, include_xml=False)
    # Para avisar en el editor de si lo guardado se puede ejecutar.
    out["validation"] = motor.validar(payload.bpmn_xml)
    return APIResponse.ok(data=out)


@router.get("/{process_id}/versions", summary="List versions of a process")
def list_versions(
    process_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("bpm.usar")),
):
    proc = _proceso_o_404(db, process_id)
    items = [svc.serialize_version(v, include_xml=False) for v in proc.versions]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/{process_id}/versions/{version}", summary="Get a specific version (with XML)")
def get_version(
    process_id: str,
    version: int,
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("bpm.usar")),
):
    v = svc.get_version(db, process_id, version)
    if not v:
        raise error_http(404, "no_encontrado", detail="Version not found", que="version")
    return APIResponse.ok(data=svc.serialize_version(v))


@router.get("/{process_id}/validation", summary="Can this version be executed? Problems with a code each")
def validate_version(
    process_id: str,
    version: Optional[int] = Query(None, ge=1, description="Por defecto, la que se ejecutaría (publicada o última)"),
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("bpm.usar")),
):
    proc = _proceso_o_404(db, process_id)
    v = svc.get_version(db, process_id, version) if version else motor.version_ejecutable(db, proc)
    if not v:
        raise error_http(404, "no_encontrado", detail="Version not found", que="version")
    return APIResponse.ok(data={"version": v.version, **motor.validar(v.bpmn_xml)})


@router.post("/{process_id}/versions/{version}/publish", summary="Publish a version")
def publish_version(
    process_id: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    v = svc.publish_version(db, process_id, version, user_id=current_user.id)
    if not v:
        raise error_http(404, "no_encontrado", detail="Version not found", que="version")
    auditar_y_confirmar(db, current_user, "PUBLISH", "bpmn_process", process_id, None,
                        new_values={"published_version": version})
    return APIResponse.ok(data=svc.serialize_version(v))


@router.post("/{process_id}/versions/{version}/retire", summary="Retire a version (running instances keep it)")
def retire_version(
    process_id: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bpm.gestionar")),
):
    v = svc.retire_version(db, process_id, version, user_id=current_user.id)
    if not v:
        raise error_http(404, "no_encontrado", detail="Version not found", que="version")
    auditar_y_confirmar(db, current_user, "RETIRE", "bpmn_process", process_id, None,
                        new_values={"retired_version": version})
    return APIResponse.ok(data=svc.serialize_version(v))


@router.post("/{process_id}/simulate", summary="Dry run of a version in memory (nothing is written)")
def simulate(
    process_id: str,
    payload: SimulacionIn = Body(default_factory=SimulacionIn),
    db: Session = Depends(get_db),
    _: User = Depends(requiere_capacidad("bpm.usar")),
):
    proc = _proceso_o_404(db, process_id)
    v = svc.get_version(db, process_id, payload.version) if payload.version else svc.get_latest_version(db, proc.id)
    if not v:
        raise error_http(404, "no_encontrado", detail="Version not found", que="version")
    return APIResponse.ok(data={"version": v.version,
                                **motor.simular(v.bpmn_xml, payload.variables or {}, payload.decisions or {})})
