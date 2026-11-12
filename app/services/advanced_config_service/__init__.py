"""
Advanced Config Service — business logic extracted from advanced_config.py router.
Covers: seeders, vacation balance computation, project template application.

Auditoria 2026-11 (#24): eran 1179 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Logger y la excepcion `NotFoundError`, compartidos.
- `semillas`: Valores por defecto y su siembra: alertas, tipos de tarea, numeracion y roles del sistema.
- `roles_y_tipos`: Roles personalizados, tipos de tarea y configuracion de alertas.
- `tarifas_y_vacaciones`: Tablas de tarifas, politicas y saldos de vacaciones, y oficinas.
- `numeracion_y_campos`: Secuencias de numeracion y campos personalizados con sus valores.
- `plantillas`: Plantillas de proyecto: listado, alta, documentos y roles, aplicacion y exportacion desde un proyecto.
"""

from app.services.advanced_config_service._comun import (  # noqa: F401
    logger,
    NotFoundError,
)

from app.services.advanced_config_service.semillas import (  # noqa: F401
    DEFAULT_ALERT_CONFIGS,
    DEFAULT_TASK_TYPES,
    DEFAULT_NUMBERING,
    DEFAULT_MODULES,
    DEFAULT_SYSTEM_ROLES,
    seed_alert_configs,
    seed_task_types,
    seed_numbering,
    seed_system_roles,
)

from app.services.advanced_config_service.roles_y_tipos import (  # noqa: F401
    list_roles,
    _ROLES_BASE,
    create_role,
    update_role,
    delete_role,
    list_task_types,
    create_task_type,
    update_task_type,
    delete_task_type,
    list_alert_configs,
    update_alert_config,
)

from app.services.advanced_config_service.tarifas_y_vacaciones import (  # noqa: F401
    get_vacation_balances,
    update_vacation_balance,
    list_rate_tables,
    create_rate_table,
    add_rate_entry,
    update_rate_entry,
    delete_rate_entry,
    delete_rate_table,
    list_vacation_policies,
    create_vacation_policy,
    update_vacation_policy,
    delete_vacation_policy,
    list_offices,
    create_office,
    update_office,
    delete_office,
)

from app.services.advanced_config_service.numeracion_y_campos import (  # noqa: F401
    list_numbering,
    update_numbering_seq,
    reset_numbering_seq,
    list_custom_fields,
    create_custom_field,
    update_custom_field,
    delete_custom_field,
    get_custom_field_values,
    save_custom_field_values,
)

from app.services.advanced_config_service.plantillas import (  # noqa: F401
    apply_template_to_project,
    list_templates,
    create_template,
    delete_template,
    PROBABILIDAD_POR_DEFECTO,
    IMPACTO_POR_DEFECTO,
    _valor_de_enum,
    plantilla_propia,
    agregar_documento_a_plantilla,
    agregar_rol_a_plantilla,
    anadir_documento_a_plantilla,
    anadir_rol_a_plantilla,
    get_full_template,
    export_project_as_template,
)
