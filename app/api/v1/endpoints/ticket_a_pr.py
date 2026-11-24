"""«Del ticket al PR»: API (docs/integraciones/TICKET_A_PR.md). Prefijo `/api/v1/ticket-pr`.

Capacidades literales:

- `ticket_pr.ver`: estado del módulo, panel del ticket o tarea, ejecución y su log
  (solo de orígenes que la persona ya ve);
- `ticket_pr.lanzar`: proponer la instrucción, lanzar, cancelar, reintentar el
  vínculo con el cambio y sincronizar con el CAB;
- `ticket_pr.aprobar_plan`: aprobar o rechazar el plan;
- `ticket_pr.config`: configuración (encendido, motor, modelo, límites,
  ficheros protegidos, tests, plantillas), repositorios por proyecto, prueba de
  conexión y coste por proyecto. Las credenciales Git van por el almacén de
  integraciones (`PUT /settings/integrations/ticket_pr/{campo}`, cifradas).

Una credencial delegada (clave de API, token OAuth) no abre nada de esto
(`credenciales_delegadas.RUTAS_VEDADAS`): lanzar un agente que gasta y abre PR
exige una sesión de una persona.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.async_db import run_db
from app.core.codigos_de_error import error
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.transaccion import confirmar
from app.services.ticket_a_pr import config as _config
from app.services.ticket_a_pr import servicio as _svc

router = APIRouter()


def _ip_ua(request: Request) -> tuple[Optional[str], Optional[str]]:
    from app.core.network import extract_client_ip
    return extract_client_ip(request), (request.headers.get("user-agent") or "")[:300] or None


def _origen(tipo: str) -> str:
    if tipo not in _svc.ORIGENES:
        raise error(422, "ticket_pr_origen_no_valido", tipo=tipo[:20])
    return tipo


# ── Estado y panel del ticket o tarea ───────────────────────────────────────

@router.get("/estado", summary="Estado del módulo para la empresa y lo que puede hacer quien mira")
def estado(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ticket_pr.ver"))):
    return APIResponse.ok(data=_svc.estado_de_la_empresa(db, current_user))


@router.get("/origen/{tipo}/{origen_id}", summary="Panel del ticket o tarea: si se puede lanzar, repositorios y ejecuciones")
def panel(tipo: str, origen_id: str, db: Session = Depends(get_db),
          current_user: User = Depends(requiere_capacidad("ticket_pr.ver"))):
    return APIResponse.ok(data=_svc.disponibilidad(db, current_user, _origen(tipo), origen_id))


class PropuestaIn(BaseModel):
    repo_id: str = Field(..., max_length=36)
    base_branch: Optional[str] = Field(None, max_length=200)


@router.post("/origen/{tipo}/{origen_id}/instruccion",
             summary="Instrucción propuesta a partir del ticket o tarea (datos personales ocultos)")
def proponer(tipo: str, origen_id: str, payload: PropuestaIn, db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("ticket_pr.lanzar"))):
    return APIResponse.ok(data=_svc.proponer_instruccion(db, current_user, _origen(tipo), origen_id,
                                                         payload.repo_id, payload.base_branch))


class LanzarIn(PropuestaIn):
    instruction: Optional[str] = Field(None, max_length=12000,
                                       description="Instrucción revisada o editada (se vuelve a ocultar al lanzar)")


@router.post("/origen/{tipo}/{origen_id}/ejecuciones",
             summary="Lanzar el agente (fase PLAN de solo lectura en un contenedor aislado; auditado)")
async def lanzar(tipo: str, origen_id: str, payload: LanzarIn, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("ticket_pr.lanzar"))):
    ip, ua = _ip_ua(request)

    def _hacer():
        run = _svc.lanzar(db, current_user, _origen(tipo), origen_id, payload.repo_id, payload.base_branch,
                          payload.instruction, ip=ip, ua=ua)
        return _svc.serializar(db, current_user, run)
    return APIResponse.ok(data=await run_db(_hacer))


# ── Ejecuciones ──────────────────────────────────────────────────────────────

@router.get("/ejecuciones/{run_id}", summary="Una ejecución (si su ticket o tarea es visible)")
def ejecucion(run_id: str, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("ticket_pr.ver"))):
    run = _svc.obtener_ejecucion(db, current_user, run_id)
    return APIResponse.ok(data=_svc.serializar(db, current_user, run))


@router.get("/ejecuciones/{run_id}/log", summary="Log del contenedor (datos personales ocultos, recortado)")
def log(run_id: str, db: Session = Depends(get_db),
        current_user: User = Depends(requiere_capacidad("ticket_pr.ver"))):
    run = _svc.obtener_ejecucion(db, current_user, run_id)
    return APIResponse.ok(data={"id": run.id, "log": run.log_redacted or ""})


class DecisionIn(BaseModel):
    approve: bool
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/ejecuciones/{run_id}/plan", summary="Aprobar (pasa a BUILD) o rechazar el plan (auditado)")
async def decidir(run_id: str, payload: DecisionIn, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("ticket_pr.aprobar_plan"))):
    ip, ua = _ip_ua(request)

    def _hacer():
        run = _svc.decidir_plan(db, current_user, run_id, payload.approve, payload.note, ip=ip, ua=ua)
        return _svc.serializar(db, current_user, run)
    return APIResponse.ok(data=await run_db(_hacer))


@router.post("/ejecuciones/{run_id}/cancelar", summary="Cancelar la ejecución (auditado; con PR: cambio cancelado)")
def cancelar(run_id: str, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("ticket_pr.lanzar"))):
    ip, ua = _ip_ua(request)
    run = _svc.cancelar(db, current_user, run_id, ip=ip, ua=ua)
    return APIResponse.ok(data=_svc.serializar(db, current_user, run))


@router.post("/ejecuciones/{run_id}/sincronizar",
             summary="Reintentar el vínculo con el cambio y llevar su estado al PR (nunca fusiona)")
async def sincronizar(run_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("ticket_pr.lanzar"))):
    def _hacer():
        run = _svc.obtener_ejecucion(db, current_user, run_id)
        if not run.change_id:
            _svc.vincular_cambio(db, run)
        _svc.sincronizar(db, run)
        return _svc.serializar(db, current_user, run)
    return APIResponse.ok(data=await run_db(_hacer))


# ── Configuración (Configuración › Del ticket al PR) ─────────────────────────

def _vista_de_config(db: Session, user: User) -> dict:
    org = user.organization_id
    return {"enabled": _config.encendido(db, org), "config": _config.leer(db, org),
            "credentials": _config.resumen_de_credenciales(db, org),
            "protected_defaults": list(_config.PROTEGIDOS_DE_FABRICA),
            "usage_today": _svc.uso_de_hoy(db, org)}


@router.get("/config", summary="Configuración del módulo (sin secretos)")
def ver_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    return APIResponse.ok(data=_vista_de_config(db, current_user))


class ConfigIn(BaseModel):
    enabled: Optional[bool] = None
    engine: Optional[str] = None
    engine_image: Optional[str] = None
    engine_version: Optional[str] = None
    proxy_image: Optional[str] = None
    ai_provider_id: Optional[str] = None
    model: Optional[str] = None
    protected_paths: Optional[list[str]] = None
    run_tests: Optional[bool] = None
    block_on_test_failure: Optional[bool] = None
    extra_egress_hosts: Optional[list[str]] = None
    bash_allow: Optional[list[str]] = None
    plan_requires_other_person: Optional[bool] = None
    change_type: Optional[str] = None
    standard_model_id: Optional[str] = None
    templates: Optional[dict] = None
    limits: Optional[dict] = None


@router.patch("/config", summary="Cambiar la configuración o encender/apagar el módulo (auditado)")
def cambiar_config(payload: ConfigIn, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    from app.services.audit import audit_log
    org = current_user.organization_id
    datos = payload.model_dump(exclude_unset=True)
    encendido = datos.pop("enabled", None)
    if datos:
        _config.guardar(db, org, current_user, datos)
    if encendido is not None:
        antes = _config.encendido(db, org)
        ip, ua = _ip_ua(request)
        audit_log(db, current_user, "UPDATE", "ticket_pr_module", org, _config.MODULO,
                  old_values={"enabled": antes}, new_values={"enabled": bool(encendido)},
                  metadata={"canal": "settings"}, ip_address=ip, user_agent=ua)
        _config.encender(db, org, current_user, bool(encendido))   # confirma
    confirmar(db)
    return APIResponse.ok(data=_vista_de_config(db, current_user))


@router.get("/repos", response_model=APIListResponse[dict], summary="Repositorios permitidos por proyecto")
def repos(project_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
          current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    items = _svc.listar_repos(db, current_user, project_id)
    return APIListResponse.ok(items=items, total=len(items), page=1, page_size=max(1, len(items)))


class RepoIn(BaseModel):
    project_id: str = Field(..., max_length=36)
    provider: str = Field(..., pattern=r"^(github|gitlab)$")
    repo_full_name: str = Field(..., max_length=256)
    default_branch: str = Field("main", max_length=200)
    test_command: Optional[str] = Field(None, max_length=500)


@router.post("/repos", summary="Permitir un repositorio para un proyecto (auditado)")
def crear_repo(payload: RepoIn, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    repo = _svc.crear_repo(db, current_user, payload.model_dump())
    confirmar(db)
    return APIResponse.ok(data=_svc.serializar_repo(repo))


class RepoPatch(BaseModel):
    repo_full_name: Optional[str] = Field(None, max_length=256)
    default_branch: Optional[str] = Field(None, max_length=200)
    test_command: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


@router.patch("/repos/{repo_id}", summary="Cambiar un repositorio permitido (auditado)")
def editar_repo(repo_id: str, payload: RepoPatch, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    repo = _svc.editar_repo(db, current_user, repo_id, payload.model_dump(exclude_unset=True))
    confirmar(db)
    return APIResponse.ok(data=_svc.serializar_repo(repo))


@router.delete("/repos/{repo_id}", summary="Quitar un repositorio permitido (se desactiva; auditado)")
def borrar_repo(repo_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    _svc.borrar_repo(db, current_user, repo_id)
    confirmar(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/prueba", summary="Prueba de conexión real: Docker, imágenes, credencial Git y modelo (`verificado`)")
async def prueba(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    from app.services.ticket_a_pr.prueba import probar
    return APIResponse.ok(data=await run_db(probar, db, current_user.organization_id))


@router.get("/costes", response_model=APIListResponse[dict], summary="Coste de IA y horas del agente por proyecto")
def costes(dias: int = Query(30, ge=1, le=3660), db: Session = Depends(get_db),
           current_user: User = Depends(requiere_capacidad("ticket_pr.config"))):
    items = _svc.coste_por_proyecto(db, current_user, dias)
    return APIListResponse.ok(items=items, total=len(items), page=1, page_size=max(1, len(items)))
