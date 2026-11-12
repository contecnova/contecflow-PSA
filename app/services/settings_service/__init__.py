"""
settings_service — business logic extracted from app/api/v1/endpoints/settings.py
Covers: general settings, project types/statuses, task statuses,
        departments, holidays.

Auditoria 2026-11 (#24): eran 1020 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_catalogo`: Catalogo de ajustes de ejecucion por grupo (los flags que expone la pantalla de configuracion).
- `runtime`: Ajustes de ejecucion: lectura con cache y respaldo de entorno, escritura por ambito, timeouts y monedas.
- `generales`: Ajustes generales de la empresa: valores por defecto, enmascarado de los sensibles y actualizacion.
- `catalogos`: Catalogos editables: tipos y estados de proyecto, estados de tarea, areas, departamentos y festivos.
"""

from app.services.settings_service._catalogo import (  # noqa: F401
    RUNTIME_FLAG_GROUPS,
)

from app.services.settings_service.runtime import (  # noqa: F401
    logger,
    _CACHE_TTL_SECONDS,
    _cache,
    _cache_lock,
    _MISSING,
    _read_raw,
    _env_fallback,
    _invalidate_cache_local,
    invalidate_cache,
    get_runtime_str,
    get_runtime_int,
    get_runtime_float,
    get_runtime_bool,
    get_runtime_namespace,
    outbound_http_timeout,
    outbound_ai_timeout,
    AJUSTES_DE_PLATAFORMA,
    get_runtime_group,
    _upsert_setting_at_scope,
    set_runtime_value,
    monedas,
    simbolos_de_moneda,
)

from app.services.settings_service.generales import (  # noqa: F401
    DEFAULT_SETTINGS,
    get_general_settings,
    CLAVE_SENSIBLE,
    MASCARA,
    es_sensible,
    es_ajuste_general,
    ajustes_generales_para,
    update_setting,
)

from app.services.settings_service.catalogos import (  # noqa: F401
    DEFAULT_PROJECT_TYPES,
    DEFAULT_PROJECT_STATUSES,
    DEFAULT_TASK_STATUSES,
    get_project_types,
    create_project_type,
    update_project_type,
    delete_project_type,
    get_project_statuses,
    create_project_status,
    update_project_status,
    delete_project_status,
    get_task_statuses,
    create_task_status,
    update_task_status,
    delete_task_status,
    get_areas,
    guardar_area,
    borrar_area,
    get_departments,
    create_department,
    update_department,
    delete_department,
    get_holidays,
    create_holiday,
    update_holiday,
    delete_holiday,
    _check_department_dependencies,
)
