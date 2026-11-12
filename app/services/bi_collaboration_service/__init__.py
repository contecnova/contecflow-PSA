"""BI Collaboration service orchestration.

Collaboration state (comments, versions, shares, notifications) is persisted
in relational tables. Governance and cache policy keep using AppSetting JSON
for now to preserve backward compatibility with existing runtime configs.

Auditoria 2026-11 (#24): eran 1024 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Claves de ajuste, JSON en ajustes, reloj y aviso de cambios en un panel.
- `comentarios`: Comentarios de panel: listado, alta y resolucion (con su formato heredado en JSON).
- `gobierno`: Reglas de gobierno de paneles, comprobaciones y politica de cache.
- `vistas_y_versiones`: Vistas compartidas y versiones de panel.
- `compartir`: Comparticion de paneles con usuarios y sus permisos.
- `avisos`: Avisos de colaboracion en paneles e instantanea de cambios.
"""

from app.services.bi_collaboration_service._comun import (  # noqa: F401
    logger,
    COMMENTS_KEY,
    RULES_KEY,
    LAST_RUN_KEY,
    SHARED_VIEWS_KEY,
    VERSIONS_KEY_PREFIX,
    SHARES_KEY_PREFIX,
    CACHE_POLICY_KEY,
    _iso_now,
    _to_json_value,
    _from_json_value,
    _is_missing_table_error,
    _table_exists,
    _emit_dashboard_notification,
    _setting_row,
    _get_json,
    _set_json,
)

from app.services.bi_collaboration_service.comentarios import (  # noqa: F401
    _legacy_list_comments,
    list_comments,
    create_comment,
    _resolver_en_json_heredado,
    _comentario_como_dict,
    resolve_comment,
)

from app.services.bi_collaboration_service.gobierno import (  # noqa: F401
    default_governance_rules,
    get_governance_rules,
    update_governance_rules,
    governance_overview,
    run_governance_checks,
    get_last_governance_run,
    get_cache_policy,
    update_cache_policy,
)

from app.services.bi_collaboration_service.vistas_y_versiones import (  # noqa: F401
    list_shared_views,
    create_shared_view,
    patch_shared_view,
    _versions_key,
    list_dashboard_versions,
    create_dashboard_version,
    restore_dashboard_version,
)

from app.services.bi_collaboration_service.compartir import (  # noqa: F401
    SHARE_PERMISSIONS,
    _shares_key,
    list_dashboard_shares,
    share_dashboard,
    revoke_dashboard_share,
)

from app.services.bi_collaboration_service.avisos import (  # noqa: F401
    dashboard_update_snapshot,
    list_notifications,
    mark_notification_read,
)
