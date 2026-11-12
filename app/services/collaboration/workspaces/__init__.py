"""Workspace + Team + Channel + Conversation services.

Auditoria 2026-11 (#24): eran 1321 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Ayudantes compartidos: usuarios por id y su nombre visible.
- `equipos_y_canales`: Espacio de trabajo, equipos, canales y sus miembros.
- `conversaciones`: Conversaciones directas y de grupo: alta, miembros, detalle y listado del usuario.
- `presencia_y_avisos`: Presencia de los usuarios, avisos de colaboracion y sus reglas.
- `busquedas_y_menciones`: Busquedas guardadas y sugerencias de mencion.
"""

from app.services.collaboration.workspaces._comun import (  # noqa: F401
    _usuarios_por_id,
    _nombre_de,
)

from app.services.collaboration.workspaces.equipos_y_canales import (  # noqa: F401
    _SLUG_RE,
    slugify,
    get_or_create_workspace,
    seed_default_bots,
    list_teams,
    create_team,
    add_team_members,
    remove_team_member,
    create_channel,
    list_channels,
    add_channel_members,
    EquipoConRecuentos,
    CanalConRecuento,
    update_workspace,
    list_teams_con_recuentos,
    update_team,
    list_team_members,
    list_channels_con_recuentos,
    update_channel,
    list_channel_members,
)

from app.services.collaboration.workspaces.conversaciones import (  # noqa: F401
    open_direct,
    create_group,
    list_conversations_for_user,
    _grupo_de_conversacion,
    list_conversation_members,
    add_conversation_members,
    remove_conversation_member,
    conversation_detail,
    conversaciones_accesibles,
)

from app.services.collaboration.workspaces.presencia_y_avisos import (  # noqa: F401
    list_presence,
    update_presence,
    MAX_NOTIFICACIONES,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    list_notification_rules,
    upsert_notification_rule,
)

from app.services.collaboration.workspaces.busquedas_y_menciones import (  # noqa: F401
    list_saved_searches,
    save_search,
    delete_saved_search,
    registrar_uso_de_busqueda,
    _CANDIDATOS_A_MENCIONAR,
    GRUPOS_DE_MENCION,
    mention_suggestions,
    MAX_RESULTADOS_DE_BUSQUEDA,
)
