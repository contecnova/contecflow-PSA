"""app.services.portal_conversation_service.

Auditoria 2026-11 (#24): eran 1179 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Ayudantes compartidos: reloj, ids de hilos antiguos, consultas base, participantes, auditoria y avisos.
- `politicas`: Politicas de conversacion: asignacion, clasificacion, redaccion de datos sensibles y aprobacion de mensajes.
- `serializacion`: Como se presentan conversaciones, participantes y mensajes (tambien los hilos antiguos).
- `hilos_antiguos`: Hilos de mensajes anteriores al modelo de conversaciones: busqueda y listado.
- `conversaciones`: Conversaciones de equipo y de cliente: listado, detalle, alta, participantes y escalado por SLA.
- `mensajes`: Mensajes: listado, envio, respuesta del bot L1 y revision.
"""

from app.services.portal_conversation_service._comun import (  # noqa: F401
    logger,
    _now,
    _is_past,
    _enum_value,
    _legacy_conversation_id,
    _is_legacy_conversation_id,
    _legacy_thread_key,
    _audit,
    _base_conversation_query,
    _legacy_roots_query,
    _get_project_for_team,
    _get_team_conversation,
    _get_client_conversation,
    _ensure_participant,
    _resolve_group_members,
    _notify_users,
)

from app.services.portal_conversation_service.politicas import (  # noqa: F401
    SENSITIVE_EMAIL_RE,
    SENSITIVE_TOKEN_RE,
    SENSITIVE_DIGITS_RE,
    DEFAULT_POLICY_MAP,
    _policy_defaults,
    _get_or_create_policy,
    _policy_out,
    list_policies,
    update_policy,
    _apply_assignment_policy,
    _redact_sensitive,
    _resolve_classification,
    _approver_candidates,
    _create_message_approval_request,
    _apply_message_policy,
)

from app.services.portal_conversation_service.serializacion import (  # noqa: F401
    _participant_out,
    _message_out,
    _legacy_message_out,
    _conversation_out,
    _legacy_conversation_out,
)

from app.services.portal_conversation_service.hilos_antiguos import (  # noqa: F401
    _get_legacy_thread_for_team,
    _get_legacy_thread_for_client,
    _list_legacy_threads_for_team,
    _list_legacy_threads_for_client,
)

from app.services.portal_conversation_service.conversaciones import (  # noqa: F401
    list_team_conversations,
    list_client_conversations,
    get_team_conversation_detail,
    get_client_conversation_detail,
    create_team_conversation,
    create_client_conversation,
    assign_participants,
    run_sla_escalations,
)

from app.services.portal_conversation_service.mensajes import (  # noqa: F401
    _refresh_conversation_status,
    _mark_first_response_if_needed,
    list_team_messages,
    list_client_messages,
    send_team_message,
    send_client_message,
    send_l1_bot_reply,
    review_message,
)
