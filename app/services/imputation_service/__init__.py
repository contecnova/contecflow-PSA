"""
imputation_service.py — Lógica de negocio para imputaciones y cronómetros.

Funciones exportadas:
  compute_cost(user, hours, db=None, on_date=None)
  resolve_user_rate(db, user, on_date=None)
  validate_and_create_imputation(payload, current_user, db)
  validate_imputation_edit_allowed(imp, current_user, db)
  start_timer_session(payload, current_user, db)
  pause_timer_session(current_user, db)
  resume_timer_session(current_user, db)
  stop_timer_session(payload, current_user, db)
  compute_timer_elapsed(timer) -> int (seconds)
  get_week_summary(week_start, current_user, db)
  get_lockout_cutoff(current_user, db)

Auditoria 2026-11 (#24): eran 1052 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Tarifa y coste, sincronizacion con la hoja semanal, fecha de cierre, pertenencia al proyecto y aviso de duplicados.
- `alta`: Alta de imputaciones con todas sus validaciones, y si una imputacion se puede editar.
- `cronometro`: Cronometro de imputacion: arrancar, pausar, reanudar, cancelar y parar.
- `consultas_y_edicion`: Consulta, edicion y borrado de imputaciones; resumen semanal, alertas y estado de cierre.
"""

from app.services.imputation_service._comun import (  # noqa: F401
    resolve_user_rate,
    compute_cost,
    sync_imputation_week_timesheet,
    _dias_de_bloqueo,
    get_lockout_cutoff,
    _assert_project_membership,
    _notify_duplicate_imputation_manager,
)

from app.services.imputation_service.alta import (  # noqa: F401
    _validar_fecha_imputable,
    _buscar_proyecto_del_usuario,
    _buscar_tarea_del_proyecto,
    _validar_estado_del_proyecto,
    _validar_tarifa_horaria,
    _validar_tope_diario,
    _validar_estado_de_la_tarea,
    _id_de_imputacion_duplicada,
    _validar_tope_semanal,
    _crear_imputacion,
    validate_and_create_imputation,
    validate_imputation_edit_allowed,
)

from app.services.imputation_service.cronometro import (  # noqa: F401
    _resolve_timer_stop_task,
    compute_timer_elapsed,
    start_timer_session,
    pause_timer_session,
    resume_timer_session,
    cancel_timer_session,
    _proyecto_valido_para_parar,
    _horas_del_cronometro,
    _comprobar_cierre_y_tope_diario,
    stop_timer_session,
    timer_out,
    get_current_timer_record,
)

from app.services.imputation_service.consultas_y_edicion import (  # noqa: F401
    update_imputation_fields,
    lockout_status_payload,
    list_alerts_payload,
    dismiss_alert_record,
    get_week_summary,
    list_imputations_query,
    get_imputation_by_id,
    delete_imputation_record,
)
