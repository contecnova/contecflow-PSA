"""Service Desk — CMDB subdomain router."""
from fastapi import APIRouter, Depends, Query, Body, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import json
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.core.tenancy import org_scoped_or_404
from app.services.cmdb.models import aprobar_linea_base
from app.models.cmdb import CMDBDiscoveryProvider, CMDBDiscoveryJob
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import CIIn
from app.services.service_desk.cmdb_service import (
    list_cmdb_items, serialize_cmdb_items, enforce_ci_org_constraints,
    build_ci, get_scoped_ci_or_404, apply_ci_update, get_ci_deprecation_impact_payload,
    delete_ci, ci_changelog,
)
from app.services.service_desk.cmdb_clases import campos as campos_de_clase, guardar_clase
from app.services.service_desk.cmdb_relation_service import (
    get_ci_relations_payload, build_ci_relation, delete_ci_relation, get_ci_impact_payload,
    get_ci_topology_graph_payload, get_dependency_graph_d3, get_blast_radius_summary,
)
from app.services.service_desk.cmdb_discovery_service import (
    crear_proveedor,
    jobs_de_un_proveedor,
    proveedores_visibles,
    run_discovery_for_provider,
    run_all_active_discoveries,
    run_due_discoveries,
    get_drift_report,
    get_reconciliation_health,
    deduplicate_candidates,
    auto_merge_duplicates,
)

router = APIRouter()


def _org(user: User) -> Optional[str]:
    """La organizacion a la que se acota; `None` solo para el superadministrador.

    Un usuario sin organizacion no ve nada: "-" no casa con ninguna.
    """
    return None if user.is_superadmin else (user.organization_id or "-")


class DiscoveryProviderIn(BaseModel):
    name: str
    provider_type: str  # aws|azure|gcp|kubernetes|vsphere
    config: dict | None = None
    is_active: bool = True
    scan_interval_minutes: int = 60


class DiscoveryProviderPatch(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    scan_interval_minutes: Optional[int] = None


def _serialize_discovery_provider(p: CMDBDiscoveryProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider_type": p.provider_type,
        "is_active": p.is_active,
        "scan_interval_minutes": getattr(p, "scan_interval_minutes", 60),
        "next_run_at": getattr(p, "next_run_at", None),
        "last_run_at": p.last_run_at,
        "last_run_status": p.last_run_status,
        "created_at": p.created_at,
    }


def _serialize_discovery_job(j: CMDBDiscoveryJob) -> dict:
    return {
        "id": j.id,
        "provider_id": j.provider_id,
        "status": j.status,
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "cis_created": j.cis_created,
        "cis_updated": j.cis_updated,
        "cis_deactivated": j.cis_deactivated,
        "error_message": j.error_message,
        "summary_json": j.summary_json,
        "triggered_by": j.triggered_by,
    }


@router.get("/cmdb", summary="Inventario CMDB")
def list_cmdb(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(None, description="Busca en nombre, codigo, host e IP"),
    ci_type: Optional[str] = Query(None), status: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(
        items=serialize_cmdb_items(list_cmdb_items(db, current_user, page, page_size,
                                                   q=q, ci_type=ci_type, status=status)),
        page=page, page_size=page_size,
    )


@router.post("/cmdb", summary="Crear CI")
def create_ci(payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_ci_org_constraints(db, current_user, payload, is_update=False)
    ci = build_ci(db, payload, current_user)
    _commit_or_rollback(db); db.refresh(ci)
    return APIResponse.ok(data={"id": ci.id, "code": ci.code})


@router.patch("/cmdb/{ci_id}", summary="Actualizar CI")
def update_ci(ci_id: str, payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    ci = get_scoped_ci_or_404(db, current_user, ci_id)
    enforce_ci_org_constraints(db, current_user, payload, is_update=True)
    apply_ci_update(db, ci, payload, current_user)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.delete("/cmdb/{ci_id}", summary="Borrar CI (logico: lo que lo cita lo conserva)")
def remove_ci(ci_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    delete_ci(db, get_scoped_ci_or_404(db, current_user, ci_id), current_user)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/cmdb/class-fields", summary="Datos propios de cada clase de CI (de la organización)")
def get_class_fields(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=campos_de_clase(db, current_user.organization_id))


@router.put("/cmdb/class-fields/{ci_type}", summary="Sustituir los datos propios de una clase de CI")
def put_class_fields(ci_type: str, payload: list[dict] = Body(...), db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin)):
    datos = guardar_clase(db, current_user.organization_id, ci_type, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data=datos)


@router.get("/cmdb/{ci_id}/changelog", summary="Historial de cambios del CI")
def get_ci_changelog(ci_id: str, limit: int = Query(100, ge=1, le=500),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=ci_changelog(db, get_scoped_ci_or_404(db, current_user, ci_id), limit))


@router.get("/cmdb/{ci_id}/relations", summary="Relaciones del CI (impacto)")
def get_ci_relations(ci_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=get_ci_relations_payload(db, current_user, ci_id))


@router.post("/cmdb/relations", summary="Crear relación entre CIs")
def create_ci_relation(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rel = build_ci_relation(db, current_user, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": rel.id, "ok": True})


@router.delete("/cmdb/relations/{relation_id}", summary="Quitar una relación entre CIs")
def remove_ci_relation(relation_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    delete_ci_relation(db, current_user, relation_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/cmdb/{ci_id}/impact", summary="Análisis de impacto — CIs afectados si este falla")
def get_ci_impact(
    ci_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_ci_impact_payload(db, current_user, ci_id, max_depth=max_depth, limit=limit))


@router.get("/cmdb/{ci_id}/topology", summary="Topología CMDB navegable alrededor de un CI")
def get_ci_topology(
    ci_id: str,
    radius: int = Query(2, ge=1, le=5),
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_ci_topology_graph_payload(db, current_user, ci_id, radius=radius, limit=limit))


@router.get("/cmdb/discovery/providers", summary="Listar proveedores discovery CMDB")
def list_discovery_providers(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    return APIListResponse.ok(items=[
        _serialize_discovery_provider(p)
        for p in proveedores_visibles(db, current_user)
    ])


@router.post("/cmdb/discovery/providers", summary="Crear proveedor discovery CMDB")
def create_discovery_provider(
    payload: DiscoveryProviderIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = crear_proveedor(db, current_user, payload.model_dump())
    _commit_or_rollback(db)
    db.refresh(provider)
    return APIResponse.ok(data=_serialize_discovery_provider(provider))


@router.patch("/cmdb/discovery/providers/{provider_id}", summary="Actualizar proveedor discovery CMDB")
def patch_discovery_provider(
    provider_id: str,
    payload: DiscoveryProviderPatch,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = org_scoped_or_404(db, CMDBDiscoveryProvider, provider_id, current_user, detail="Provider not found")

    data = payload.model_dump(exclude_none=True)
    if "name" in data:
        provider.name = data["name"]
    if "is_active" in data:
        provider.is_active = data["is_active"]
    if "config" in data:
        provider.config_json = json.dumps(data["config"] or {})
    if "scan_interval_minutes" in data:
        provider.scan_interval_minutes = max(1, data["scan_interval_minutes"])
        # Recalculate next_run_at if provider has already run
        if provider.last_run_at:
            from datetime import timedelta
            provider.next_run_at = provider.last_run_at + timedelta(
                minutes=provider.scan_interval_minutes
            )
    provider.updated_at = datetime.now(timezone.utc)

    _commit_or_rollback(db)
    db.refresh(provider)
    return APIResponse.ok(data=_serialize_discovery_provider(provider))


@router.post("/cmdb/discovery/providers/{provider_id}/run", summary="Ejecutar discovery para proveedor")
def run_discovery_provider_now(
    provider_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    provider = org_scoped_or_404(db, CMDBDiscoveryProvider, provider_id, current_user, detail="Provider not found")
    job = run_discovery_for_provider(db, provider)
    return APIResponse.ok(data={"ok": True, "job": _serialize_discovery_job(job)})


@router.get("/cmdb/discovery/providers/{provider_id}/jobs", summary="Listar jobs de discovery")
def list_discovery_jobs(
    provider_id: str,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    # La comprobacion de a quien pertenece el proveedor vive ahora dentro de
    # `jobs_de_un_proveedor`, donde no se puede olvidar.
    jobs, total = jobs_de_un_proveedor(
        db, current_user, provider_id, page=page, page_size=page_size)
    return APIListResponse.ok(
        items=[_serialize_discovery_job(j) for j in jobs],
        total=total, page=page, page_size=page_size,
    )


@router.post("/cmdb/discovery/run-all", summary="Ejecutar discovery para todos los proveedores activos")
def run_discovery_all(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    return APIResponse.ok(data={"ok": True, "results": run_all_active_discoveries(db)})


@router.get("/cmdb/discovery/reconciliation-health", summary="Salud de reconciliación CMDB")
def reconciliation_health(
    provider_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=get_reconciliation_health(db, provider_type=provider_type, org_id=_org(current_user)))


@router.get('/cmdb/discovery/reconciliation-candidates', summary='Preview deduplicación CMDB con confidence score')
def reconciliation_candidates(
    provider_type: Optional[str] = Query(None),
    min_confidence: float = Query(0.85, ge=0.5, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    items = deduplicate_candidates(db, provider_type=provider_type, min_confidence=min_confidence,
                                   org_id=_org(current_user))
    return APIResponse.ok(data={"items": items, "count": len(items), "min_confidence": min_confidence})


@router.post('/cmdb/discovery/reconciliation-merge', summary='Aplicar auto-merge de CIs duplicados por confidence score')
def reconciliation_merge(
    provider_type: Optional[str] = Query(None),
    min_confidence: float = Query(0.9, ge=0.5, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = auto_merge_duplicates(
        db,
        provider_type=provider_type,
        min_confidence=min_confidence,
        limit=limit,
        org_id=_org(current_user),
    )
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, **result})


# ── Dependency mapping + Blast Radius ────────────────────────────────────────

@router.get("/cmdb/{ci_id}/dependency-graph", summary="Grafo de dependencias D3.js force-directed")
def get_dependency_graph(
    ci_id: str,
    depth: int = Query(3, ge=1, le=6),
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna un grafo compatible con D3.js forceSimulation.

    Nodos incluyen color por tipo de CI y estado operacional.
    Links incluyen tipo de relación y strength para la simulación.
    """
    return APIResponse.ok(data=get_dependency_graph_d3(db, current_user, ci_id, depth=depth, limit=limit))


@router.get("/cmdb/{ci_id}/blast-radius", summary="Resumen de blast radius (CIs afectados + usuarios estimados)")
def get_ci_blast_radius(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Análisis de radio de impacto con desglose por criticidad y estimación de usuarios afectados."""
    return APIResponse.ok(data=get_blast_radius_summary(db, current_user, ci_id))


@router.get("/cmdb/{ci_id}/deprecation-impact", summary="Impacto de deprecación de un CI (incluye activos vinculados)")
def get_ci_deprecation_impact(
    ci_id: str,
    max_depth: int = Query(5, ge=1, le=10),
    limit: int = Query(500, ge=1, le=2000),
    include_root_assets: bool = Query(True, description="Incluir activos vinculados al CI origen"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evalúa el impacto de retirar/deprecar un CI usando dependencia CMDB + assets enlazados por ci_id."""
    return APIResponse.ok(data=get_ci_deprecation_impact_payload(
        db,
        current_user,
        ci_id,
        max_depth=max_depth,
        limit=limit,
        include_root_assets=include_root_assets,
    ))


# ── ITSM-P04: Drift Detection endpoints ──────────────────────────────────────

@router.get(
    "/cmdb/discovery/drift-report",
    summary="Reporte de drift de configuración CMDB (ITSM-P04)",
)
def cmdb_drift_report(
    hours: int = Query(24, ge=1, le=720, description="Ventana de tiempo en horas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Lista los CIs donde se detectó drift de configuración en las últimas `hours` horas.

    Para cada CI drifted incluye los últimos cambios del changelog, la IP actual
    y el proveedor de discovery que lo detectó.
    """
    return APIResponse.ok(data=get_drift_report(db, hours=hours, org_id=_org(current_user)))


@router.post(
    "/cmdb/discovery/run-due",
    summary="Ejecutar discovery para proveedores con ventana vencida (ITSM-P04)",
)
def run_due_discovery(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Ejecuta discovery sólo para proveedores cuya cadencia ha vencido (next_run_at <= now).

    Respeta el `scan_interval_minutes` de cada proveedor para evitar scans
    innecesarios y reducir carga en entornos grandes.
    """
    _ = current_user
    return APIResponse.ok(data={"ok": True, "results": run_due_discoveries(db)})


@router.post(
    "/cmdb/discovery/providers/{provider_id}/approve-baseline",
    summary="Aprobar baseline de configuración de un CI o proveedor (ITSM-P04)",
)
def approve_baseline(
    provider_id: str,
    ci_id: Optional[str] = Query(None, description="CI específico; omitir para aprobar todos del proveedor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Congela el estado actual de `attributes` como baseline aprobado.

    Limpia `drift_detected_at` — el CI ya no aparecerá como drifted hasta el
    próximo scan que detecte diferencias respecto a este baseline.

    Auditoría 2026-08: la consulta de aquí comparaba el **id** del proveedor
    contra `CMDBItem.discovery_provider`, que guarda su **tipo**, así que no
    encontraba nunca ningún CI y este endpoint no aprobaba nada. El detalle está
    en el docstring de `aprobar_linea_base`.
    """
    datos = aprobar_linea_base(db, current_user, provider_id, ci_id)
    if datos.get("ok"):
        _commit_or_rollback(db)
    return APIResponse.ok(data=datos)


# ══════════════════════════════════════════════════════════════════════════════
# On-Premise Agent Management Endpoints  (ITSM discovery gap)
# ══════════════════════════════════════════════════════════════════════════════

from app.services.service_desk.cmdb_discovery_service import (
    generate_agent_token,
    process_agent_checkin,
    list_agent_registrations,
    revoke_agent_token,
    rotate_agent_token,
)


class AgentRegisterIn(BaseModel):
    name: str
    description: Optional[str] = None
    os_type: Optional[str] = None   # windows | linux


class AgentCheckinIn(BaseModel):
    """Payload sent by the lightweight on-premise agent at each check-in."""
    os_type: Optional[str] = None           # windows | linux
    hostname: Optional[str] = None
    fqdn: Optional[str] = None
    ip_address: Optional[str] = None
    os_version: Optional[str] = None
    kernel_version: Optional[str] = None    # Linux only
    cpu_count: Optional[int] = None
    memory_mb: Optional[int] = None
    disk_gb: Optional[int] = None
    uptime_seconds: Optional[int] = None
    interfaces: list[dict] = []
    services: list[str] = []
    tags: dict = {}


@router.post("/cmdb/agents/register", summary="Registrar agente on-premise y obtener token (admin)", status_code=201)
def register_agent(
    payload: AgentRegisterIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Register a new on-premise agent and receive a one-time bearer token.

    The raw token is returned **once only** and must be securely delivered to
    the target host.  It cannot be recovered — use POST rotate-token if lost.
    """
    result = generate_agent_token(
        db,
        name=payload.name,
        description=payload.description,
        os_type=payload.os_type,
        created_by=str(current_user.id),
        organization_id=current_user.organization_id,
    )
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.post("/cmdb/agents/checkin", summary="Check-in de agente on-premise (bearer token auth)")
def agent_checkin(
    payload: AgentCheckinIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive a system inventory report from an on-premise agent.

    Authentication: `Authorization: Bearer <agent-token>` header.
    The agent token is validated by SHA-256 hash against the DB — no JWT.
    Creates or updates the corresponding CMDB CI automatically.
    """
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    raw_token = auth_header.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    client_ip = request.client.host if request.client else None
    result = process_agent_checkin(db, raw_token, payload.model_dump(), client_ip=client_ip)
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


@router.get("/cmdb/agents", summary="Listar agentes on-premise registrados (admin)")
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Los agentes registrados de la organizacion, con su ultimo check-in."""
    return APIListResponse.ok(items=list_agent_registrations(db, _org(current_user)))


@router.delete("/cmdb/agents/{agent_id}", summary="Revocar token de agente on-premise (admin)")
def revoke_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Revoke an agent's token (soft-disable).  The agent will be rejected at next check-in."""
    enforce_abac(db, current_user, "sd_cmdb_agent", agent_id, action="delete")
    revoke_agent_token(db, agent_id, _org(current_user))
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "agent_id": agent_id, "revoked": True})


@router.post("/cmdb/agents/{agent_id}/rotate-token", summary="Rotar token de agente on-premise (admin)")
def rotate_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Invalidate the current token and generate a new one.  Returned once only."""
    result = rotate_agent_token(db, agent_id, _org(current_user))
    _commit_or_rollback(db)
    return APIResponse.ok(data=result)


# ── SNMP Network Scan endpoint ────────────────────────────────────────────────

class SNMPScanIn(BaseModel):
    hosts: list[str]
    community: str = "public"
    port: int = 161
    timeout: int = 2
    retries: int = 1
    version: str = "v2c"
    scan_interfaces: bool = True
    v3_user: Optional[str] = None
    v3_auth_key: Optional[str] = None
    v3_priv_key: Optional[str] = None


@router.post("/cmdb/snmp-scan", summary="Escaneo SNMP de red con descubrimiento de interfaces (admin)")
def snmp_network_scan(
    payload: SNMPScanIn,
    persist: bool = Query(True, description="Reconcile discovered devices into CMDB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Ad-hoc SNMP scan of a list of hosts or CIDR ranges.

    Walks sysDescr/sysName/sysLocation/sysContact (SNMPv2c/v3) and optionally
    the ifTable OID for per-interface details (name, MAC, speed, oper-status).

    When `persist=true` (default), discovered devices are upserted into CMDB
    via the same reconcile_cis() logic as the scheduled discovery jobs.
    """
    from app.services.service_desk.cmdb_discovery_service import (
        discover_snmp_network, reconcile_cis,
    )
    from fastapi import HTTPException

    if not payload.hosts:
        raise HTTPException(status_code=400, detail="hosts list is required")

    config = payload.model_dump(exclude_none=True)
    discovered = discover_snmp_network(config)

    stats: dict = {}
    if persist and discovered:
        # Un escaneo puntual no ve la red entera: no retira lo que no encuentra.
        stats = reconcile_cis(db, discovered, "snmp", organization_id=current_user.organization_id,
                              retirar_ausentes=False)
        _commit_or_rollback(db)

    return APIResponse.ok(data={
        "ok": True,
        "discovered": len(discovered),
        "devices": discovered,
        "persisted": persist,
        "stats": stats,
    })
