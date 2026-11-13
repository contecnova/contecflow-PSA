"""
client_portal_service.py — Business logic extracted from client_portal router.

Auditoria 2026-11 (#24): eran 1851 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `autenticacion`: Credenciales del portal: contrasenas, tokens de cliente, enlaces publicos y configuracion de sesion.
- `serializacion`: Como se presentan al portal peticiones, UAT, mensajes, documentos y encuestas.
- `clientes`: Clientes del portal: alta, edicion, acceso, perfil propio y marca.
- `facturas`: Facturas del cliente y enlaces publicos de estado del proyecto.
- `panel`: Panel del cliente, actividad reciente, ficha del proyecto y estadisticas del portal.
- `peticiones`: Peticiones de funcionalidad del cliente y las peticiones de cambio que generan.
- `uat`: Pruebas de aceptacion (UAT): campanas, casos, resultados e incidencias.
- `mensajes`: Mensajeria entre cliente y equipo.
- `documentos`: Documentos del portal y su firma.
- `wiki_y_encuestas`: Paginas de wiki visibles en el portal y encuestas de satisfaccion.
"""

from app.services.client_portal_service.autenticacion import (  # noqa: F401
    logger,
    CLIENT_TOKEN_EXPIRE_HOURS,
    CLIENT_TOKEN_SECRET,
    PORTAL_SHARE_LINK_EXPIRE_HOURS,
    ALGORITHM,
    hash_password,
    verify_password,
    create_client_token,
    revocar_token_de_cliente,
    token_de_cliente_revocado,
    get_portal_session_config,
    create_portal_share_token,
    decode_portal_share_token,
)

from app.services.client_portal_service.serializacion import (  # noqa: F401
    _FR_STATUS_LABELS,
    _FR_PRIORITY_LABELS,
    _FR_PRIORITY_COLORS,
    _FR_STATUS_COLORS,
    _CR_STATUS_LABELS,
    _CR_STATUS_COLORS,
    _resolve_fr_cr_status,
    fr_out,
    _UAT_STATUS_LABELS,
    _UAT_STATUS_COLORS,
    _uat_stats,
    _uat_test_cases_out,
    _uat_issues_out,
    uat_out,
    msg_out,
    doc_out,
    survey_out,
)

from app.services.client_portal_service.clientes import (  # noqa: F401
    list_clients,
    create_client,
    update_client,
    delete_client,
    get_active_client_by_id,
    client_login,
    get_me,
    get_portal_branding,
    _traducciones_del_portal_de,
    update_my_profile,
)

from app.services.client_portal_service.facturas import (  # noqa: F401
    _FACTURAS_DEL_CLIENTE,
    list_client_invoices,
    approve_client_invoice,
    create_public_share_link,
    view_public_project_status,
)

from app.services.client_portal_service.panel import (  # noqa: F401
    get_recent_activity,
    _OPEN_TICKET_STATUSES,
    _resolve_dashboard_project,
    _dashboard_budget_and_milestones,
    _dashboard_deliverables_and_uat,
    _dashboard_fr_and_unread,
    _dashboard_ticket_counts,
    _dashboard_sla_stats,
    _dashboard_progress_pct,
    _dashboard_next_milestone,
    get_client_dashboard,
    get_project_info,
    _portal_stats_client_count,
    _portal_stats_survey_aggregates,
    get_portal_stats,
)

from app.services.client_portal_service.peticiones import (  # noqa: F401
    list_feature_requests,
    list_all_feature_requests,
    create_feature_request,
    update_feature_request,
    withdraw_feature_request,
    _ESTADO_DE_CR_SEGUN_FR,
    _acotar_fr_a_la_organizacion,
    _avisar_del_cambio_de_estado,
    respond_to_fr,
    _next_cr_code,
    _create_cr_from_fr,
    _apply_client_fr_approval,
    _apply_client_fr_rejection,
    client_decide_fr,
)

from app.services.client_portal_service.uat import (  # noqa: F401
    list_uat_client,
    list_uat_team,
    create_uat_for_project,
    add_test_case,
    submit_uat_result,
    report_uat_issue,
    update_uat_issue,
)

from app.services.client_portal_service.mensajes import (  # noqa: F401
    get_client_messages,
    get_team_messages,
    send_client_message,
    send_team_message,
)

from app.services.client_portal_service.documentos import (  # noqa: F401
    get_client_documents,
    get_all_documents,
    upload_document,
    _load_signable_document,
    _apply_signature_metadata,
    _resolve_doc_project_name,
    _generate_and_store_signature_pdf,
    sign_document,
    download_signed_pdf,
)

from app.services.client_portal_service.wiki_y_encuestas import (  # noqa: F401
    _portal_visible_wiki_filter,
    portal_wiki_pages,
    portal_wiki_page_detail,
    get_surveys,
    create_survey,
    respond_survey,
)
