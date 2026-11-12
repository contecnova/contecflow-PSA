"""
cab_service — Business logic extracted from app/api/v1/endpoints/cab.py.

Provides:
  - trigger_out               — serialize WebhookTrigger to dict
  - execute_workflow_from_webhook — background task: enqueue workflow
  - SYSTEM_EMAIL_TEMPLATES    — built-in email templates
  - render_template           — {{variable}} substitution
  - send_email_smtp           — SMTP email dispatch
  - AVAILABLE_WIDGETS         — dashboard widget catalog
  - default_widget_layout     — default layout by role
  - compute_risk_score        — rule-based project risk engine
  - sync_git_commits          — GitHub: pull requests reales
  - sync_calendar             — Google Calendar: sprints como eventos
  - sync_accounting           — QuickBooks/Xero: envio de facturas
  - sync_jira                 — Jira → tareas: estado

Auditoria 2026-11 (#24): eran 1422 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `integraciones`: Integraciones externas (git, calendario, contabilidad, Jira): alta, sincronizacion y datos traidos.
- `webhooks_entrantes`: Disparadores por webhook entrante: alta, rotacion del slug, registro y ejecucion del flujo.
- `correo`: Plantillas de correo del sistema, render, envio y registro de envios.
- `widgets_y_onboarding`: Widgets del panel del usuario y pasos de bienvenida.
- `riesgo`: Puntuacion de riesgo de proyecto (plazo, presupuesto, alcance, recursos) y su cache.
- `cab`: Comite de cambios (CAB): cambios pendientes, votos y ventanas de mantenimiento.
- `gdpr`: Peticiones RGPD: alta, borrado y portabilidad.
- `busqueda`: Busqueda global en proyectos, tareas, tickets, usuarios, facturas y oportunidades.
- `_comun`: Constantes y estado compartidos por los submodulos.
"""

from app.services.cab_service.integraciones import (  # noqa: F401
    desactivar_integracion,
    _config_de,
    _espera,
    sync_git_commits,
    sync_calendar,
    sync_accounting,
    _ESTADO_DESDE_JIRA,
    sync_jira,
    list_integrations,
    create_integration,
    run_integration_sync,
    get_calendar_events,
    get_commit_links,
)

from app.services.cab_service.webhooks_entrantes import (  # noqa: F401
    trigger_out,
    execute_workflow_from_webhook,
    list_webhook_triggers,
    create_webhook_trigger,
    log_webhook_fire,
    get_active_webhook_trigger_by_slug,
    rotate_webhook_trigger_slug,
    get_webhook_logs,
    delete_webhook_trigger,
)

from app.services.cab_service.correo import (  # noqa: F401
    SYSTEM_EMAIL_TEMPLATES,
    render_template,
    send_email_smtp,
    list_email_templates,
    create_email_template,
    _resolve_email_template,
    send_email_action,
    get_email_logs,
)

from app.services.cab_service.widgets_y_onboarding import (  # noqa: F401
    AVAILABLE_WIDGETS,
    default_widget_layout,
    get_user_widgets,
    save_widget_layout,
    reset_widgets,
    ONBOARDING_STEPS,
    get_onboarding,
    complete_onboarding_step,
    dismiss_onboarding,
)

from app.services.cab_service.riesgo import (  # noqa: F401
    _CLAVES_DE_RIESGO,
    _ajustes_de_riesgo,
    _risk_schedule,
    _risk_budget,
    _risk_scope,
    _risk_resource,
    _risk_recommendation,
    compute_risk_score,
    _RISK_SCORE_FIELDS,
    _is_risk_cache_fresh,
    _serialize_cached_risk,
    _persist_risk_score,
    get_risk_scores,
    get_project_risk_score,
)

from app.services.cab_service.cab import (  # noqa: F401
    get_cab_pending_changes,
    cast_cab_vote,
    close_cab_vote,
    list_maintenance_windows,
    create_maintenance_window,
    schedule_cr_in_window,
)

from app.services.cab_service.gdpr import (  # noqa: F401
    list_gdpr_requests,
    create_gdpr_request,
    _gdpr_erase_user,
    _gdpr_portability_export,
    process_gdpr_request,
)

from app.services.cab_service.busqueda import (  # noqa: F401
    _search_projects,
    _search_tasks,
    _search_tickets,
    _search_users,
    _search_invoices,
    _search_opportunities,
    global_search,
)

from app.services.cab_service._comun import (  # noqa: F401
    logger,
)

from app.services.integrations import get_jira_issue  # noqa: F401
