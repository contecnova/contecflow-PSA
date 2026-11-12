"""Service layer for Performance Reviews.

Auditoria 2026-11 (#24): eran 1017 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `guardas`: Busquedas acotadas a la organizacion de quien llama (pregunta, objetivo, plan, usuario); 404 si no es suya.
- `ciclos_y_preguntas`: Ciclos de evaluacion y sus preguntas: alta, siembra, clonado, edicion y estado del ciclo.
- `evaluaciones`: Evaluaciones individuales: evaluadores elegibles, alta, guardado, envio e historial.
- `campanas_360`: Campanas 360: validacion, alta, avisos a evaluadores, cierre, agregado e historial.
"""

from app.services.performance_service.guardas import (  # noqa: F401
    _org_de,
    pregunta_propia,
    objetivo_propio,
    plan_propio,
    usuario_propio,
    usuario_de_la_organizacion,
)

from app.services.performance_service.ciclos_y_preguntas import (  # noqa: F401
    DEFAULT_QUESTIONS,
    list_cycles,
    create_cycle,
    list_questions,
    seed_default_questions_for_cycle,
    clone_questions,
    add_question,
    update_question,
    delete_question,
    anadir_pregunta,
    actualizar_pregunta,
    borrar_pregunta,
    sembrar_preguntas_por_defecto,
    clonar_preguntas,
    get_cycle,
    activate_cycle,
    close_cycle,
    serialize_question,
)

from app.services.performance_service.evaluaciones import (  # noqa: F401
    eligible_reviewers,
    list_cycle_reviews,
    list_my_pending_reviews,
    _organizacion_del_ciclo,
    create_review,
    get_review,
    save_review,
    submit_review,
    get_user_review_history,
    avg_score,
    serialize_review,
)

from app.services.performance_service.campanas_360 import (  # noqa: F401
    logger,
    get_campaign,
    list_cycle_campaigns,
    _MENSAJES_DE_ELEGIBILIDAD,
    _elegibles,
    _validar_lista_de_evaluadores,
    _sin_duplicados,
    _validar_campana,
    _evaluaciones_de_la_campana,
    create_campaign,
    _notify_reviewers,
    close_campaign,
    serialize_campaign,
    _is_rating_kind,
    _coerce_number,
    aggregate_campaign,
    history_360_for_subject,
    can_launch_campaign_for,
)
