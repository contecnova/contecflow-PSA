"""Series temporales de metricas para el motor de alertas inteligentes.

Devuelve la serie mensual de cada metrica soportada —y de las compuestas que
define el cliente— a partir de datos reales de la base.

── Como esta organizado y por que ───────────────────────────────────────────
Auditoria 2026-08 (hallazgo 18). `_fetch_metric_series` era la funcion mas
compleja de la solucion con enorme diferencia: complejidad ciclomatica **247** en
945 lineas, cuando la siguiente del proyecto esta en 67. Eran 55 `if metric_key
== ...` secuenciales al mismo nivel, cada uno con su consulta y su `return`: una
tabla de despacho escrita como una unica funcion.

Eso tenia tres costes concretos, no esteticos:

  · una clave del catalogo sin rama caia al `return _empty_like()` del final, asi
    que la metrica presentaba una linea plana en vez de fallar — el mismo patron
    que dejo muerto el endpoint `/analytics/adhoc` y el reconocimiento ASC 606;
  · las 945 lineas compartian un unico ambito, asi que cualquier variable de una
    rama era visible para las 54 siguientes;
  · ninguna rama se podia probar por separado.

Ahora cada grupo de metricas es una funcion con nombre, registrada en
`_RESOLUTORES`. La logica de cada una se movio VERBATIM —misma condicion, mismo
cuerpo, mismos comentarios— y la equivalencia se verifico comparando las 133
series del catalogo antes y despues, valor a valor. Lo unico que se anadio a cada
funcion es el preambulo que reenlaza los nombres que tomaba del entorno.

El contexto compartido (`_Ctx`) lleva la serie de meses de referencia y los cuatro
ayudantes de agregacion que antes eran cierres. Se llama `ctx` y no `c` porque el
codigo original usa `c` como variable propia en cinco sitios.

Ver tests/test_bi_metrics_catalog.py: comprueba que las 133 claves del catalogo se
resuelven, que todas devuelven series de la misma longitud y que catalogo y
codigo no se pueden separar.

Auditoria 2026-11 (#24): eran 1861 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_contexto`: Contexto de calculo de una serie (organizacion, periodo, sesion) y el logger comun.
- `finanzas`: Series financieras: ingresos, coste, margen, facturas, gastos y perfil de coste.
- `recursos`: Series de personas: horas, carga, hojas de horas, ausencias, certificaciones y alertas de recursos.
- `proyectos`: Series de proyectos: estado, hitos, entregables, peticiones de cambio y tareas.
- `itsm`: Series de service desk: tickets, SLA, base de conocimiento, problemas, cambios, activos e incidentes.
- `gobierno`: Series de gobierno y automatizacion: playbooks, aprobaciones, flujos, SoD, GRC e importaciones.
- `_registro`: El registro de resolutores (clave -> serie), la entrada `serie_con_meses` y las series que se derivan de otras metricas.
"""

from app.services.bi_smart_alerts.metrics._contexto import (  # noqa: F401
    logger,
    _Ctx,
    _construir_contexto,
)

from app.services.bi_smart_alerts.metrics.finanzas import (  # noqa: F401
    COST_PROFILE_KEYS,
    _serie_revenue,
    _serie_cost,
    _serie_margin,
    _serie_margin_pct,
    _serie_budget_used_pct,
    _fecha_de_vencimiento,
    _fecha_de_emision,
    _fecha_de_cobro,
    _MetricaDeFactura,
    _METRICAS_DE_FACTURA,
    _METRICA_DIAS_DE_COBRO,
    CLAVES_DE_FACTURA,
    _estado_de,
    _acumular,
    _dias_medios_de_cobro,
    _serie_invoice,
    _serie_expense,
    _fin_de_mes,
    _percentil,
    _maximo_de_las_medias,
    _MesDeCoste,
    _cp_avg_per_hour,
    _cp_max_per_hour,
    _cp_p95_per_hour,
    _cp_dept_max_per_hour,
    _cp_country_max_per_hour,
    _cp_total_annual,
    _cp_top_person_annual,
    _cp_top_country_annual,
    _cp_users_with,
    _cp_users_legacy,
    _cp_users_missing,
    _cp_employer_pct_avg,
    _cp_employer_pct_max,
    _CALCULOS_DE_COSTE,
    _serie_cost_profile,
)

from app.services.bi_smart_alerts.metrics.recursos import (  # noqa: F401
    _serie_imputations_approved_hours,
    _serie_hours_logged,
    _serie_hours_billable,
    _serie_utilization,
    _serie_overloaded_users,
    _serie_avg_user_load_pct,
    _serie_users_at_capacity,
    _serie_users_underutilized,
    _serie_snapshot_billable_pct,
    _ESTADO_DE_HOJA,
    CLAVES_DE_HOJA_DE_HORAS,
    _hojas_pendientes_ahora,
    _contar_hojas_por_mes,
    _coste_de_hojas_por_mes,
    _horas_medias_por_hoja,
    _serie_pending_timesheets,
    _serie_absence,
    _serie_certified_users_count,
    _serie_resource_alerts,
)

from app.services.bi_smart_alerts.metrics.proyectos import (  # noqa: F401
    _serie_active_projects,
    _serie_projects_at_risk,
    _serie_projects_over_budget,
    _serie_projects_overdue,
    _serie_projects_on_hold,
    _serie_projects_cancelled,
    _serie_projects_completed_count,
    _serie_milestones,
    _serie_deliverables,
    _serie_change_requests,
    _serie_tasks_overdue,
    _serie_tasks_blocked,
    _serie_tasks_created,
    _serie_tasks_completed,
)

from app.services.bi_smart_alerts.metrics.itsm import (  # noqa: F401
    _ESTADOS_NO_ABIERTOS,
    _ESTADOS_RESUELTOS,
    _FilaDeTicket,
    _MetricaDeTicket,
    _todas,
    _METRICAS_DE_TICKET,
    CLAVES_DE_TICKET,
    _serie_tickets_open,
    _serie_ticket_time_log_total,
    _serie_sla_breach_count,
    _serie_sla_compliance_pct,
    _serie_kb,
    _serie_problems_open,
    _serie_known_errors_active,
    _serie_itsm_changes,
    _serie_assets_total,
    _serie_major_incidents_active,
    _serie_escalations_total,
)

from app.services.bi_smart_alerts.metrics.gobierno import (  # noqa: F401
    _serie_playbook,
    _serie_pending_approvals,
    _serie_workflow,
    _serie_sod_violations,
    _serie_grc,
    _serie_imports,
)

from app.services.bi_smart_alerts.metrics._registro import (  # noqa: F401
    _serie_custom,
    _serie_billable_pct,
    _serie_task_completion_rate,
    _Resolutor,
    _RESOLUTORES,
    _POR_PREFIJO,
    claves_atendidas,
    _resolutor_para,
    _fetch_metric_series,
    serie_con_meses,
)
