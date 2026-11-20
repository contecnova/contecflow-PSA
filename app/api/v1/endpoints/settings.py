"""
settings — thin router delegating to app.services.settings_service
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, requiere_capacidad
from app.core.abac_enforce import enforce_abac
from app.core.config import settings as app_settings
from app.models.user import User, UserRole
import app.services.settings_service as _svc
from app.services.politica_de_visibilidad import audiencia_de
from app.core.responses import APIListResponse, APIResponse
from app.schemas.settings import (
    SettingOut,
    SettingUpdate,
    ProjectTypeIn,
    ProjectTypeOut,
    ProjectStatusIn,
    ProjectStatusOut,
    TaskStatusIn,
    TaskStatusOut,
    DepartmentIn,
    DepartmentOut,
    AreaIn,
    AreaOut,
    HolidayIn,
    HolidayOut,
    LogLevelPayload,
)
from app.core.codigos_de_error import error_http, desde_valor

router = APIRouter()


def require_admin_or_pm(current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise error_http(403, "sin_permiso", detail="Acceso denegado")
    return current_user

# ── Puesta en marcha de la empresa (revisión 2026-11) ─────────────────────────
@router.get("/setup-checklist", summary="Qué falta por configurar en la empresa (medido) (admin)")
def setup_checklist(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    from app.services.puesta_en_marcha import lista
    return APIResponse.ok(data=lista(db, current_user.organization_id))


# ── Aislamiento en la base (revisión 2026-11) ─────────────────────────────────
@router.get("/db-isolation", summary="¿Está armado el aislamiento entre empresas en la base (RLS)? (admin)")
def db_isolation(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    from app.db import rls
    return APIResponse.ok(data=rls.estado(db.connection()))


# ── Traducciones del back-office (revisión 2026-11) ───────────────────────────
@router.get("/app-translations", summary="Traducciones del back-office personalizadas por la empresa")
def get_app_translations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.branding_service import traducciones_del_back_office
    return APIResponse.ok(data=traducciones_del_back_office(db, str(current_user.organization_id)))


@router.put("/app-translations", summary="Guardar traducciones del back-office (admin)")
def put_app_translations(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    from app.services.branding_service import guardar_traducciones_del_back_office
    return APIResponse.ok(data=guardar_traducciones_del_back_office(
        db, str(current_user.organization_id), payload.get("translations") or {}))


# ── General settings ──────────────────────────────────────────────────────────

@router.get("/org-defaults", summary="Defaults de organización (moneda, zona horaria, idioma, jornada)")
def get_org_defaults(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Valores efectivos (pantalla → entorno), solo los de la audiencia de quien pregunta."""
    return APIResponse.ok(data=_svc.defaults_de_organizacion(
        db, getattr(current_user, "organization_id", None), audiencia_de(current_user)))


@router.get("/general", response_model=APIListResponse[SettingOut])
def get_general_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Sin secretos y por audiencia: ver `ajustes_generales_para`.
    items = _svc.ajustes_generales_para(db, audiencia_de(current_user), bool(current_user.is_superadmin),
                                        getattr(current_user, "organization_id", None))
    return APIListResponse.ok(items=items, total=len(items))

@router.patch("/general/{key}", response_model=APIResponse[SettingOut])
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    # Por aqui solo los ajustes generales; el estado interno de los servicios
    # (claves con punto, secretos) lo escribe cada servicio, no esta pantalla.
    if not current_user.is_superadmin and not _svc.es_ajuste_general(key):
        raise error_http(403, "ajustes_solo_generales")
    try:
        return APIResponse.ok(data=_svc.update_setting(key, payload.value, current_user.organization_id, db))
    except ValueError as e:
        # 18-11-2026: moneda, zona, idioma y jornada se validan como su clave de ejecución.
        raise desde_valor(422, e)


# ── Runtime-flag groups (Phase 1 of env → UI migration) ──────────────────────
# These are typed, validated knobs grouped by domain (SLA, semantic, health,
# etc.). Values resolve org-then-global, fall back to env. See
# docs/CONFIG_MIGRATION_INVENTORY.md.

@router.get("/runtime/{group}", summary="Effective values of a runtime-flag group (SLA, etc.)")
def get_runtime_group(group: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    try:
        return APIResponse.ok(data={"group": group, "items": _svc.get_runtime_group(db, group, current_user.organization_id)})
    except ValueError as e:
        raise desde_valor(404, e)


@router.put("/runtime/{group}/{key}", summary="Update a runtime-flag value (admin)")
def update_runtime_setting(group: str, key: str, payload: SettingUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    # Revisión 2026-11: los de plataforma, sólo el superadmin y en la fila global.
    plataforma = key in _svc.AJUSTES_DE_PLATAFORMA
    if plataforma and not current_user.is_superadmin:
        raise error_http(403, "ajuste_solo_superadmin", detail="Es un ajuste de la plataforma: sólo lo cambia el superadmin")
    try:
        from app.core.network import extract_client_ip
        return APIResponse.ok(data=_svc.set_runtime_value(
            db, group, key, payload.value, None if plataforma else current_user.organization_id,
            actor_id=str(current_user.id),
            actor_ip=extract_client_ip(request),
            actor_ua=request.headers.get("user-agent"),
        ))
    except ValueError as e:
        raise desde_valor(400, e)


# ── Integration credentials (Phase 2 of env → UI migration) ──────────────────
# Encrypted per-org provider credentials. Secret values are never echoed back —
# only a "configured: true" flag. Setting an empty value resets to env.

from app.services import integration_credentials_service as _creds


@router.get("/integrations", summary="List integration providers with their fields")
def list_integration_providers(_: User = Depends(requiere_capacidad("org.administrar"))):
    return APIResponse.ok(data={"providers": _creds.list_providers()})


@router.get("/integrations/{provider}", summary="Describe a provider's configuration (no secrets echoed)")
def describe_integration(provider: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    try:
        return APIResponse.ok(data=_creds.describe_provider(db, provider, current_user.organization_id))
    except ValueError as e:
        raise desde_valor(404, e)


@router.get("/audit-log", summary="Read settings + integration credential audit trail (admin)")
def read_audit_log(
    scope: Optional[str] = None,
    key: Optional[str] = None,
    provider: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("org.administrar")),
):
    from app.services.settings_audit_service import query_audit_log, serialize
    rows, total = query_audit_log(
        db,
        scope=scope, key=key, provider=provider, actor_id=actor_id,
        organization_id=current_user.organization_id,
        limit=limit, offset=offset,
    )
    return APIListResponse.ok(items=[serialize(r) for r in rows], total=total, page_size=limit)


@router.post("/integrations/{provider}/test", summary="Probe an integration provider with its current credentials (admin)")
def test_integration(provider: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    from app.services.integration_test_service import test_provider_connection
    return APIResponse.ok(data=test_provider_connection(db, provider, org_id=current_user.organization_id))


@router.put("/integrations/{provider}/{key}", summary="Set or clear a provider's field (admin)")
def update_integration(provider: str, key: str, payload: SettingUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("org.administrar"))):
    try:
        from app.core.network import extract_client_ip
        resultado = _creds.set_credential(
            db, provider, key, payload.value if payload.value != "" else None,
            current_user.organization_id, updated_by=str(current_user.id),
            actor_ip=extract_client_ip(request),
            actor_ua=request.headers.get("user-agent"),
        )
        # Revisión 2026-11: los tokens guardados de un conector son de la credencial anterior.
        from app.services.conectores.anfitrion import PRODUCTOS, olvidar_tokens
        if provider in PRODUCTOS:
            olvidar_tokens(PRODUCTOS[provider])
        return APIResponse.ok(data=resultado)
    except ValueError as e:
        raise desde_valor(400, e)


# ── Project types ─────────────────────────────────────────────────────────────

@router.get("/project-types", response_model=APIListResponse[ProjectTypeOut])
def get_project_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_project_types(db)
    return APIListResponse.ok(items=items, total=len(items))

@router.post("/project-types", response_model=APIResponse[ProjectTypeOut])
def create_project_type(payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.create_project_type(payload.model_dump(), db))
    except ValueError as e:
        raise desde_valor(400, e)

@router.patch("/project-types/{item_id}", response_model=APIResponse[ProjectTypeOut])
def update_project_type(item_id: str, payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.update_project_type(item_id, payload.model_dump(), db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

@router.delete("/project-types/{item_id}")
def delete_project_type(item_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        enforce_abac(db, _, "custom_project_type", item_id, action="delete")
        return APIResponse.ok(data=_svc.delete_project_type(item_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")


# ── Sectores de cliente y categorías de gasto (19-11-2026) ────────────────────
# Catálogos de clave editables por empresa (`settings_service.catalogos_de_clave`);
# mismo contrato que /project-types (value, label, color, sort_order).

def _rutas_de_catalogo(ruta: str, nombre: str) -> None:
    @router.get(f"/{ruta}", response_model=APIListResponse[ProjectTypeOut], name=f"listar_{nombre}")
    def _listar(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
        items = _svc.catalogos_de_clave.listar(db, nombre)
        return APIListResponse.ok(items=items, total=len(items))

    @router.post(f"/{ruta}", response_model=APIResponse[ProjectTypeOut], name=f"crear_{nombre}")
    def _crear(payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
        try:
            return APIResponse.ok(data=_svc.catalogos_de_clave.crear(db, nombre, payload.model_dump()))
        except ValueError as e:
            raise desde_valor(400, e)

    @router.patch(f"/{ruta}/{{item_id}}", response_model=APIResponse[ProjectTypeOut], name=f"actualizar_{nombre}")
    def _actualizar(item_id: str, payload: ProjectTypeIn, db: Session = Depends(get_db),
                    _: User = Depends(require_admin_or_pm)):
        try:
            return APIResponse.ok(data=_svc.catalogos_de_clave.actualizar(db, nombre, item_id, payload.model_dump()))
        except ValueError:
            raise error_http(404, "no_encontrado_generico")

    @router.delete(f"/{ruta}/{{item_id}}", name=f"borrar_{nombre}")
    def _borrar(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
        try:
            return APIResponse.ok(data=_svc.catalogos_de_clave.borrar(db, nombre, item_id))
        except ValueError:
            raise error_http(404, "no_encontrado_generico")


_rutas_de_catalogo("client-industries", "client_industries")
_rutas_de_catalogo("expense-categories", "expense_categories")
_rutas_de_catalogo("supplier-service-types", "supplier_service_types")  # proveedores (rev. 189)
_rutas_de_catalogo("supplier-billing-units", "supplier_billing_units")

# ── Project statuses ──────────────────────────────────────────────────────────

@router.get("/project-statuses", response_model=APIListResponse[ProjectStatusOut])
def get_project_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_project_statuses(db)
    return APIListResponse.ok(items=items, total=len(items))

@router.post("/project-statuses", response_model=APIResponse[ProjectStatusOut])
def create_project_status(payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.create_project_status(payload.model_dump(), db))
    except ValueError as e:
        raise desde_valor(400, e)

@router.patch("/project-statuses/{item_id}", response_model=APIResponse[ProjectStatusOut])
def update_project_status(item_id: str, payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.update_project_status(item_id, payload.model_dump(), db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

@router.delete("/project-statuses/{item_id}")
def delete_project_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        enforce_abac(db, _, "custom_project_status", item_id, action="delete")
        return APIResponse.ok(data=_svc.delete_project_status(item_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

# ── Task statuses ─────────────────────────────────────────────────────────────

@router.get("/task-statuses", response_model=APIListResponse[TaskStatusOut])
def get_task_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_task_statuses(db)
    return APIListResponse.ok(items=items, total=len(items))

@router.post("/task-statuses", response_model=APIResponse[TaskStatusOut])
def create_task_status(payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.create_task_status(payload.model_dump(), db))
    except ValueError as e:
        raise desde_valor(400, e)

@router.patch("/task-statuses/{item_id}", response_model=APIResponse[TaskStatusOut])
def update_task_status(item_id: str, payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        return APIResponse.ok(data=_svc.update_task_status(item_id, payload.model_dump(), db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

@router.delete("/task-statuses/{item_id}")
def delete_task_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("proyectos.config"))):
    try:
        enforce_abac(db, _, "custom_task_status", item_id, action="delete")
        return APIResponse.ok(data=_svc.delete_task_status(item_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

# ── Departments ───────────────────────────────────────────────────────────────

@router.get("/departments", response_model=APIListResponse[DepartmentOut])
def get_departments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_departments(db)
    return APIListResponse.ok(items=items, total=len(items))

@router.post("/departments", response_model=APIResponse[DepartmentOut])
def create_department(payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        return APIResponse.ok(data=_svc.create_department(payload.model_dump(), db))
    except ValueError as e:
        raise desde_valor(400, e)

@router.patch("/departments/{item_id}", response_model=APIResponse[DepartmentOut])
def update_department(item_id: str, payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        # Sólo lo que llega: si no, un PATCH sin área la quitaba.
        return APIResponse.ok(data=_svc.update_department(item_id, payload.model_dump(exclude_unset=True), db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

@router.delete("/departments/{item_id}")
def delete_department(item_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        enforce_abac(db, _, "department", item_id, action="delete")
        return APIResponse.ok(data=_svc.delete_department(item_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

# ── Áreas (revisión 2026-11): agrupan departamentos; base de su presupuesto ─────

@router.get("/areas", response_model=APIListResponse[AreaOut])
def get_areas(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_areas(db)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/areas", response_model=APIResponse[AreaOut])
def create_area(payload: AreaIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("personas.config"))):
    return APIResponse.ok(data=_svc.guardar_area(db, payload.model_dump(), current_user.organization_id))


@router.patch("/areas/{area_id}", response_model=APIResponse[AreaOut])
def update_area(area_id: str, payload: AreaIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("personas.config"))):
    try:
        return APIResponse.ok(data=_svc.guardar_area(db, payload.model_dump(exclude_unset=True), current_user.organization_id, area_id))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")


@router.delete("/areas/{area_id}")
def delete_area(area_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        return APIResponse.ok(data=_svc.borrar_area(db, area_id))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")


# ── Holidays ──────────────────────────────────────────────────────────────────

@router.get("/holidays", response_model=APIListResponse[HolidayOut])
def get_holidays(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = _svc.get_holidays(db)
    return APIListResponse.ok(items=items, total=len(items))

@router.post("/holidays", response_model=APIResponse[HolidayOut])
def create_holiday(payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    return APIResponse.ok(data=_svc.create_holiday(payload.model_dump(), db))

@router.patch("/holidays/{item_id}", response_model=APIResponse[HolidayOut])
def update_holiday(item_id: str, payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        return APIResponse.ok(data=_svc.update_holiday(item_id, payload.model_dump(), db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")

@router.delete("/holidays/{item_id}")
def delete_holiday(item_id: str, db: Session = Depends(get_db), _: User = Depends(requiere_capacidad("personas.config"))):
    try:
        enforce_abac(db, _, "holiday", item_id, action="delete")
        return APIResponse.ok(data=_svc.delete_holiday(item_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado_generico")


# ── Log Level (runtime configurable) ─────────────────────────────────────────

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

@router.get("/log-level", summary="Obtener nivel de log actual")
def get_log_level(_: User = Depends(requiere_capacidad("org.administrar"))):
    root_level = logging.getLevelName(logging.getLogger().level)
    contecflow_level = logging.getLevelName(logging.getLogger("contecflow").level)
    uvicorn_level = logging.getLevelName(logging.getLogger("uvicorn").level)
    uvicorn_error_level = logging.getLevelName(logging.getLogger("uvicorn.error").level)
    uvicorn_access_level = logging.getLevelName(logging.getLogger("uvicorn.access").level)
    return APIResponse.ok(data={
        "root": root_level,
        "contecflow": contecflow_level if contecflow_level != "NOTSET" else root_level,
        "uvicorn": uvicorn_level if uvicorn_level != "NOTSET" else root_level,
        "uvicorn_error": uvicorn_error_level if uvicorn_error_level != "NOTSET" else root_level,
        "uvicorn_access": uvicorn_access_level if uvicorn_access_level != "NOTSET" else root_level,
        "valid_levels": sorted(VALID_LOG_LEVELS),
    })


@router.post("/log-level", summary="Cambiar nivel de log en tiempo real (requiere admin)")
def set_log_level(payload: LogLevelPayload, _: User = Depends(requiere_capacidad("org.administrar"))):
    level_name = payload.level.upper()
    if level_name not in VALID_LOG_LEVELS:
        raise error_http(400, "campo_no_valido_opciones", detail=f"Nivel inválido. Use uno de: {', '.join(sorted(VALID_LOG_LEVELS))}", campo="level", opciones=', '.join(sorted(VALID_LOG_LEVELS)))
    numeric = getattr(logging, level_name)
    if payload.logger:
        target_logger = logging.getLogger(payload.logger)
        target_logger.setLevel(numeric)
        affected = [payload.logger]
    else:
        affected = ["root", "contecflow", "uvicorn", "uvicorn.error", "uvicorn.access"]
        logging.getLogger().setLevel(numeric)
        logging.getLogger("contecflow").setLevel(numeric)
        logging.getLogger("uvicorn").setLevel(numeric)
        logging.getLogger("uvicorn.error").setLevel(numeric)
        logging.getLogger("uvicorn.access").setLevel(numeric)
    app_settings.LOG_LEVEL = level_name
    logging.getLogger("contecflow").info(
        f"Log level changed to {level_name} for logger '{payload.logger or 'root'}'"
    )
    return APIResponse.ok(data={
        "ok": True,
        "logger": payload.logger or "global",
        "level": level_name,
        "affected": affected,
    })
