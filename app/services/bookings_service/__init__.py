"""
Bookings service — business logic extracted from bookings.py endpoint.
Covers: task dependencies, resource bookings, exchange rates, SLA schedules,
        API keys, recurring invoices, pipeline ops, ITSM aging, SSO, workflows.

Auditoria 2026-11 (#24): eran 1565 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `reservas`: Reservas de recursos: listado, mapa de calor y control de capacidad.
- `divisas`: Tipos de cambio de reservas y conversion de importes.
- `sla`: Calendarios de SLA, festivos y calculo de vencimientos.
- `api_keys`: Claves de API: alta, revocacion y verificacion.
- `facturacion_recurrente`: Facturas recurrentes: plantillas y generacion periodica.
- `pipeline_e_informes`: Pipeline comercial (oportunidad a proyecto, prevision) e informes operativos (antiguedad de tickets, wallboard).
- `aprovisionamiento`: Acciones de aprovisionamiento de los flujos: identidad, Terraform y Ansible.
- `cola_de_flujos`: Flujos de automatizacion: pasos, reintentos, condiciones y la cola que los ejecuta.
- `_comun`: Constantes y estado compartidos por los submodulos.
"""

from app.services.bookings_service.reservas import (  # noqa: F401
    serialize_booking,
    list_bookings_records,
    get_bookings_heatmap,
    _horas_en_semana,
    comprobar_capacidad,
    create_booking_record,
    update_booking_record,
    delete_booking_record,
)

from app.services.bookings_service.divisas import (  # noqa: F401
    get_exchange_rates_data,
    upsert_exchange_rate_record,
    convert_currency_amount,
)

from app.services.bookings_service.sla import (  # noqa: F401
    serialize_schedule,
    list_sla_schedules_records,
    create_sla_schedule_record,
    calculate_sla_deadline_record,
    add_holidays_record,
    delete_holiday_record,
)

from app.services.bookings_service.api_keys import (  # noqa: F401
    _hash_api_key,
    _verify_api_key,
    list_api_keys_records,
    create_api_key_record,
    revoke_api_key_record,
)

from app.services.bookings_service.facturacion_recurrente import (  # noqa: F401
    serialize_recurring,
    list_recurring_records,
    create_recurring_record,
    update_recurring_record,
    process_due_recurring_records,
    generate_recurring_now_record,
)

from app.services.bookings_service.pipeline_e_informes import (  # noqa: F401
    convert_opportunity_to_project_record,
    get_pipeline_revenue_forecast,
    get_ticket_aging_report,
    get_wallboard_data,
)

from app.services.bookings_service.aprovisionamiento import (  # noqa: F401
    ALLOWED_TERRAFORM_COMMANDS,
    _render_step_value,
    _provisioning_root,
    _safe_provision_path,
    _run_cli,
    _validate_provision_url,
    _execute_provision_action,
    _execute_terraform_action,
    _execute_ansible_action,
    _execute_step_action,
)

from app.services.bookings_service.cola_de_flujos import (  # noqa: F401
    paso_de_workflow_propio,
    configurar_reintentos_de_paso,
    _coerce_retry_policy,
    _retry_sleep_seconds,
    enqueue_workflow_record,
    _OPERADORES_DE_CONDICION,
    _MINUTOS_POR_UNIDAD,
    _MAX_INTENTOS,
    _ELEMENTOS_POR_PASADA,
    _ESPERAR,
    _ejecutar_accion_con_reintentos,
    _encolar_continuacion,
    _evaluar_condicion,
    _ejecutar_webhook,
    _ejecutar_paso,
    _anotar_metricas_del_flujo,
    _procesar_un_elemento,
    process_workflow_queue_record,
    execute_workflow_now_record,
)

from app.services.bookings_service._comun import (  # noqa: F401
    logger,
)
