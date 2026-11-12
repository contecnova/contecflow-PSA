"""
activity_service.py — Business logic for activity feeds, mentions, project health,
recurring tasks, CPM critical path, resource demand, vendor scorecard, and what-if
simulation.

Auditoria 2026-11 (#24): eran 1069 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `actividad`: Actividad y menciones: eventos, avisos de mencion y feeds.
- `salud`: Salud de proyecto: calculo, instantaneas y vista de cartera.
- `tareas_recurrentes`: Tareas recurrentes: definicion y materializacion de ocurrencias.
- `planificacion`: Planificacion: camino critico, demanda de recursos y simulacion de proyecto.
- `proveedores`: Cuadro de mando de proveedores: puntuaciones y ranking.
"""

from app.services.activity_service.actividad import (  # noqa: F401
    emit_activity,
    create_notification,
    parse_and_store_mentions,
    get_new_notifications,
    get_new_activity_events,
    activity_feed_payload,
    project_activity_payload,
    my_mentions_payload,
    mark_mention_read_record,
)

from app.services.activity_service.salud import (  # noqa: F401
    _PROJECT_HEALTH_KEYS,
    compute_health,
    project_health_payload,
    save_health_snapshot_record,
    portfolio_health_payload,
)

from app.services.activity_service.tareas_recurrentes import (  # noqa: F401
    TaskModel,
    list_recurring_tasks_payload,
    create_recurring_task_record,
    update_recurring_task_record,
    delete_recurring_task_record,
    _DISPARA_EN,
    _pasa_la_mascara_de_dias,
    _ocurrencias_pendientes,
    _siguiente_codigo_de_tarea,
    _tarea_de_la_recurrencia,
    materialize_recurring_tasks_cmd,
)

from app.services.activity_service.planificacion import (  # noqa: F401
    _duracion_en_dias,
    _grafo_de_dependencias,
    _orden_topologico,
    _pasada_adelante,
    _pasada_atras,
    critical_path_payload,
    resource_demand_payload,
    create_demand_line_record,
    delete_demand_line_record,
    _resolve_simulation_rate,
    simulate_project_payload,
)

from app.services.activity_service.proveedores import (  # noqa: F401
    score_composite,
    vendor_scorecard_payload,
    add_vendor_score_record,
    vendor_scorecard_ranking_payload,
)
