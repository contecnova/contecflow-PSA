"""
billing_reports_service — business logic extracted from billing_reports.py router.
Covers: report runners, invoice helpers, SLA helpers, workflow/scheduled-report
serializers, SmartMatch, template instantiation, bulk import helpers.

Auditoria 2026-11 (#24): eran 1959 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Ayudantes compartidos: organizacion de la sesion, alcance de facturas y bloqueo de proyecto.
- `facturas`: Facturas: alta, edicion, estados, resumen y enlace de cobro.
- `informes`: Informes del sistema, informes programados y definiciones de informe.
- `sla`: Panel de SLA, rendimiento de agentes y pausa del reloj de SLA.
- `workflows`: Flujos de automatizacion: alta, edicion, listado y serializacion.
- `plantillas`: Plantillas de proyecto: alta, listado e instanciacion.
- `smartmatch`: SmartMatch: puntuacion de candidatos por habilidades y disponibilidad.
- `importacion`: Importacion de datos por CSV: plantillas, validacion y ejecucion.
"""

from app.services.billing_reports_service._comun import (  # noqa: F401
    _logger,
    _tenant_org_id,
    _is_superadmin,
    _query_project_for_org,
    _lock_project_for_update,
    _set_serializable_if_postgres,
    _is_serialization_failure,
    _scope_invoice_query,
)

from app.services.billing_reports_service.facturas import (  # noqa: F401
    get_invoice_by_id,
    crear_enlace_de_pago,
    query_invoices,
    next_invoice_number,
    invoice_out,
    create_invoice,
    importe_de_linea,
    _CABECERA_EDITABLE,
    _factura,
    _exigir_borrador,
    _imputaciones_de,
    obtener_factura,
    editar_factura,
    liberar_lo_facturado,
    borrar_factura,
    _aprobacion_antes_de_enviar,
    update_invoice_status,
    _a_moneda_base,
    get_invoice_summary,
    list_invoices,
    get_invoice_for_pdf,
)

from app.services.billing_reports_service.informes import (  # noqa: F401
    run_projects_report,
    run_imputations_report,
    run_tickets_report,
    run_expenses_report,
    run_capacity_report,
    _INFORMES_DEL_SISTEMA,
    run_system_report,
    create_scheduled_report,
    CAMPOS_EDITABLES_INFORME,
    update_scheduled_report,
    delete_scheduled_report,
    list_scheduled_reports,
    save_report_definition,
    delete_report_definition,
    get_scheduled_report_by_id,
    serialize_scheduled_report,
)

from app.services.billing_reports_service.sla import (  # noqa: F401
    business_minutes_between,
    get_sla_dashboard,
    get_agent_performance,
    pause_resume_sla,
)

from app.services.billing_reports_service.workflows import (  # noqa: F401
    create_workflow,
    update_workflow,
    list_workflows_all,
    delete_workflow,
    serialize_workflow,
)

from app.services.billing_reports_service.plantillas import (  # noqa: F401
    create_template,
    list_templates_all,
    instantiate_template,
)

from app.services.billing_reports_service.smartmatch import (  # noqa: F401
    _NIVEL_A_NUMERO,
    _PESOS_DE_SMARTMATCH,
    _RECOMENDACIONES_SMARTMATCH,
    _nivel_numerico,
    _semanas_del_periodo,
    _mapas_de_habilidades,
    _puntuar_candidato,
    smartmatch,
)

from app.services.billing_reports_service.importacion import (  # noqa: F401
    IMPORT_TEMPLATES,
    MAX_IMPORT_BYTES,
    _CAMPOS_OBLIGATORIOS,
    _CAMPOS_NUMERICOS,
    _FILAS_QUE_SE_VALIDAN,
    _errores_de_fila,
    _leer_csv,
    validate_import_csv,
    _FilaRechazada,
    _defectos_de_proyecto,
    _crear_proyecto,
    _crear_usuario,
    _crear_imputacion,
    _CONSTRUCTORES,
    _PREPARACION,
    _importar_filas,
    _estado_del_trabajo,
    execute_import_csv,
)

from app.services.audit import audit_log  # noqa: F401

from app.services.numbering import next_numbered_code  # noqa: F401

from app.services.billing_reports.data_source_service import run_skills_report  # noqa: F401

from app.db.session import is_postgres  # noqa: F401
