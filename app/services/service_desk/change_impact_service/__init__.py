"""
Change Impact Service — Fase 2 ITSM Intelligence
=================================================
Sprint 13-14: Análisis de impacto automático y scoring de riesgo para Change Requests.

Capacidades:
  1. score_change_risk()       — score 0-100 automático basado en heurísticas + histórico
  2. analyze_affected_cis()   — expande CIs afectados via grafo de dependencias
  3. suggest_maintenance_window() — ventana de menor incidentalidad (últimas 4 semanas)
  4. generate_impact_report() — informe completo para el CAB
  5. score_and_persist()      — wrapper que actualiza el Change Request en BD

Todos los métodos son read-only excepto score_and_persist (que escribe en el CR).

Auditoria 2026-11 (#24): eran 1350 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `riesgo`: Puntuacion de riesgo de un cambio, informe de impacto, ventana de mantenimiento y matriz de riesgo.
- `cab`: Panel del CAB y puntuacion (persistida) de los cambios pendientes.
- `planes`: Analisis completo guardado, plan de marcha atras y plan de pruebas.
- `comunicacion`: Plan de comunicacion del cambio: audiencias, canales y avisos.
- `simulacion`: Simulacion «que pasaria si» de un cambio y de su ventana propuesta.
"""

from app.services.service_desk.change_impact_service.riesgo import (  # noqa: F401
    logger,
    _CHANGE_TYPE_RISK,
    _CURRENT_RISK_SCORE,
    _ci_count_risk,
    _downtime_risk,
    _expand_ci_dependencies,
    _get_ci_details,
    _open_tickets_on_cis,
    _incident_count_last_days,
    suggest_maintenance_window,
    score_change_risk,
    generate_impact_report,
    _CRITICALITY_RISK_SCORE,
    _RISK_LEVEL_THRESHOLDS,
    _risk_level_label,
    get_risk_matrix_for_change,
)

from app.services.service_desk.change_impact_service.cab import (  # noqa: F401
    ESTADOS_PENDIENTES_DE_CAB,
    TOPE_DE_CAMBIOS_POR_PASADA,
    _cambios_de_la_organizacion,
    panel_del_cab,
    puntuar_cambios_pendientes,
    score_and_persist,
)

from app.services.service_desk.change_impact_service.planes import (  # noqa: F401
    _get_json_setting,
    _set_json_setting,
    analyze_change_impact_full,
    get_cached_impact_analysis,
    generate_rollback_plan,
    _PASOS_DEL_PLAN,
    _FASES_DEL_PLAN,
    _contexto_del_plan,
    _pasos_aplicables,
    generate_testing_plan,
)

from app.services.service_desk.change_impact_service.comunicacion import (  # noqa: F401
    _COMMS_AUDIENCES,
    _CHANNEL_MAP,
    _AVISOS_DEL_PLAN,
    _avisos_aplicables,
    generate_comms_plan,
)

from app.services.service_desk.change_impact_service.simulacion import (  # noqa: F401
    _ORDEN_DE_RIESGO,
    _cis_directos,
    _cambio_simulado,
    _matriz_de_incidencias,
    _evaluar_ventana_propuesta,
    _lado_del_informe,
    simulate_change_whatif,
)
