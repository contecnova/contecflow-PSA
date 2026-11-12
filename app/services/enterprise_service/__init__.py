"""
Enterprise service — business logic extracted from enterprise.py router.
Covers: serializers, subcontractor worker creation, revenue forecast aggregation,
        audit stats computation, webhook test, SSO config validation.

Auditoria 2026-11 (#24): eran 1257 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `webhooks`: Webhooks salientes: validacion de destino (sin redes internas), alta, edicion, entregas y prueba.
- `sso`: Configuraciones de SSO: validacion, alta, edicion y borrado.
- `auditoria_y_permisos`: Registro de auditoria (consulta, estadisticas, exportacion firmada) y permisos por proyecto.
- `avisos`: Avisos del usuario: listado, lectura y limpieza.
- `subcontratas`: Subcontratas: empresas, tarifas, asignaciones, trabajadores, habilidades, horas y facturas.
- `prevision`: Prevision de ingresos por proyecto y de cartera.
"""

from app.services.enterprise_service.webhooks import (  # noqa: F401
    logger,
    _BLOCKED_NETWORKS,
    _BLOCKED_HOSTNAMES,
    _rechazar_si_es_interna,
    _validate_webhook_url,
    serialize_webhook,
    test_webhook_delivery,
    list_webhooks,
    create_webhook,
    update_webhook,
    delete_webhook,
    get_webhook_deliveries,
    get_webhook_for_test,
)

from app.services.enterprise_service.sso import (  # noqa: F401
    serialize_sso,
    validate_sso_config,
    list_sso_configs,
    create_sso_config,
    update_sso_config,
    delete_sso_config,
    get_sso_config_for_test,
)

from app.services.enterprise_service.auditoria_y_permisos import (  # noqa: F401
    compute_audit_stats,
    get_audit_log,
    get_project_permissions,
    grant_project_permission,
    update_project_permission,
    revoke_project_permission,
    exportar_cadena_de_auditoria,
)

from app.services.enterprise_service.avisos import (  # noqa: F401
    get_my_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    clear_old_notifications,
)

from app.services.enterprise_service.subcontratas import (  # noqa: F401
    serialize_subcontractor,
    serialize_worker,
    next_sub_code,
    get_subcontractor,
    create_worker_with_user,
    list_subcontractors,
    create_subcontractor,
    update_subcontractor,
    delete_subcontractor,
    add_subcontractor_rate,
    delete_subcontractor_rate,
    get_subcontractor_assignments,
    create_subcontractor_assignment,
    list_all_workers,
    get_workers_for_subcontractor,
    _ESPEJO_TRABAJADOR_USUARIO,
    _sincronizar_usuario_enlazado,
    update_worker,
    delete_worker,
    add_worker_skill,
    remove_worker_skill,
    get_timelogs,
    create_timelog,
    delete_timelog,
    get_sub_invoices,
    create_sub_invoice,
    update_sub_invoice,
    get_subcontractors_dashboard,
)

from app.services.enterprise_service.prevision import (  # noqa: F401
    serialize_forecast,
    get_portfolio_forecast,
    get_project_forecast,
    upsert_forecast,
)
