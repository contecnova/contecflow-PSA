"""
Automations service — reglas SI disparador [condicion] ENTONCES acciones.

Auditoria 2026-11. Hasta ahora ninguna regla saltaba sola (nada llamaba a
`fire_trigger`), la pantalla ofrecia 64 disparadores y 23 acciones de los que
el motor conocia 14 y 11, «Probar» ejecutaba las acciones de verdad, y varias
acciones cruzaban organizaciones. Ahora:

- **Catalogo unico** (`CATALOGO_DISPARADORES`, `CATALOGO_ACCIONES`): la
  pantalla lo pide a la API, y guardar algo fuera de el da 422.
- **Disparo**: los cambios de registro los anota `automation_events` al
  guardar y los procesa el worker (`disparar`); los de fecha y umbral salen de
  `escanear`, que corre cada `AUTOMATIONS_SCAN_MINUTES`.
- **Una organizacion**: una regla solo ve eventos de la suya, y sus acciones
  (avisar a un rol, la integracion de Slack/Teams) se quedan dentro.
- **«Probar» simula**: dice que haria cada accion sin hacerla.

Auditoria 2026-11 (#24): eran 1340 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Logger y `_v` (valor de un enum o el propio valor), compartidos.
- `catalogo`: Catalogo de disparadores y acciones, validacion de reglas y evaluacion de condiciones.
- `acciones`: Ejecucion de las acciones de una regla: avisos, correo, webhooks, mensajeria, tareas, tickets, asignacion y aprobaciones.
- `disparo`: Disparo de reglas por evento, barridos periodicos y reglas programadas.
- `reglas`: Reglas de la organizacion: alta, edicion, borrado, ejecuciones, plantillas y simulacion.
"""

from app.services.automations_service._comun import (  # noqa: F401
    logger,
    _v,
)

from app.services.automations_service.catalogo import (  # noqa: F401
    _CAMPOS_TAREA,
    _CAMPOS_TICKET,
    _CAMPOS_FACTURA,
    _CAMPOS_APROBACION,
    CATALOGO_DISPARADORES,
    _SEVERIDADES,
    _ROLES,
    _ESTADOS_TAREA,
    _PRIORIDADES_TAREA,
    _ESTADOS_PROYECTO,
    _ESTADOS_TICKET,
    _p,
    CATALOGO_ACCIONES,
    _ALIAS,
    _OPERADORES,
    _GRUPOS,
    CAMPOS_ACTUALIZABLES,
    catalogo,
    _faltan,
    _validar_condicion,
    validar_cron,
    validar_regla,
    serialize_rule,
    check_conditions,
)

from app.services.automations_service.acciones import (  # noqa: F401
    _org,
    _usuarios_del_rol,
    _accion_create_alert,
    _avisar,
    _recurso,
    _accion_notify_role,
    _accion_notify_user,
    _destinatarios_de_correo,
    _accion_send_email,
    _motivo_de_rechazo_ssrf,
    _cuerpo_del_webhook,
    _contexto_publico,
    _timeout,
    _accion_call_webhook,
    _webhook_de_la_integracion,
    _accion_send_slack_message,
    _accion_send_teams_message,
    _tarea_del_evento,
    _accion_change_task_status,
    _accion_change_task_priority,
    _codigo_de_tarea,
    _accion_create_task,
    _accion_change_project_status,
    _ticket_del_evento,
    _accion_escalate_ticket,
    _accion_change_ticket_status,
    _accion_conditional_branch,
    _TICKET_CERRADO,
    _menos_cargado,
    _accion_assign,
    _valor_de_campo,
    _accion_update_field,
    _ENTIDAD_DEL_EVENTO,
    _accion_create_approval,
    _ACCIONES,
    execute_actions,
    _TAREA_ABIERTA,
)

from app.services.automations_service.disparo import (  # noqa: F401
    _encendidas,
    _reglas,
    disparar,
    _ejecutar_regla,
    _orgs_con_reglas,
    _contexto_de_tarea,
    _barrer_tareas_vencidas,
    _barrer_tareas_que_vencen,
    _barrer_presupuesto,
    _barrer_partes,
    _barrer_facturas_vencidas,
    contexto_de_factura,
    _BARRIDOS,
    escanear,
    _zona_de,
    proxima_ejecucion,
    _correr_programadas,
    run_scheduled_automations,
)

from app.services.automations_service.reglas import (  # noqa: F401
    _EFECTO,
    simular,
    get_automation_templates,
    _de_mi_organizacion,
    list_rules_for_user,
    regla_de,
    _proyecto_de_mi_organizacion,
    create_rule_db,
    update_rule_db,
    delete_rule_db,
    get_executions_db,
    test_rule_by_id,
)
