"""
auth_service.py — Business logic helpers extracted from auth router.
Covers: SSO state management, login rate-limiting, MFA challenge helpers,
password-reset token flow, cookie utilities, ephemeral tokens.

Auditoria 2026-11 (#24): eran 1093 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `estado_efimero`: Estado efimero en Redis (con respaldo en memoria): estados SSO, intentos de login, peticiones y jti de restablecimiento.
- `mfa`: MFA: exigencia por organizacion, secreto y reto de segundo factor.
- `sso`: SSO: rol y organizacion del usuario, URL de descubrimiento, proveedores, salud SAML y alta del usuario federado.
- `tokens_y_cookies`: Tokens efimeros, cookies de autenticacion y el flujo de restablecimiento de contrasena.
- `sesiones_y_usuarios`: Busqueda de usuarios, sesiones activas y su revocacion, e IP y eventos de seguridad.
- `webauthn`: Credenciales WebAuthn (passkeys): consulta y alta.
- `_comun`: Constantes y estado compartidos por los submodulos.
"""

from app.services.auth_service.estado_efimero import (  # noqa: F401
    SSO_STATE_TTL,
    SSO_KEY_PREFIX,
    LOGIN_FAIL_PREFIX,
    LOGIN_LOCK_PREFIX,
    PASSWORD_RESET_TTL_SECONDS,
    PASSWORD_RESET_REQUEST_WINDOW_SECONDS,
    PASSWORD_RESET_REQUEST_MAX_PER_WINDOW,
    PASSWORD_RESET_JTI_PREFIX,
    _sso_states_fallback,
    _sso_states_lock,
    _redis_client,
    _redis_client_init,
    _login_fail_fallback,
    _password_reset_req_fallback,
    _password_reset_jti_fallback,
    _REDIS_RECONNECT_BACKOFF,
    _redis_last_attempt_at,
    force_redis_reconnect,
    get_sso_redis,
    register_sso_state,
    consume_sso_state,
    consume_sso_state_payload,
    login_bucket,
    LOGIN_ACCOUNT_MULTIPLIER,
    login_account_bucket,
    login_lock_ttl,
    _redis_circuit_break,
    register_login_failure,
    clear_login_failure,
    password_reset_bucket,
    register_password_reset_request,
    store_password_reset_jti,
    is_current_password_reset_jti,
    consume_password_reset_token,
)

from app.services.auth_service.mfa import (  # noqa: F401
    organizacion_exige_mfa,
    exigir_reautenticacion,
    guardar_secreto_de_mfa,
    generar_codigos_de_respaldo,
    borrar_codigos_de_respaldo,
    consumir_codigo_de_respaldo,
    estado_de_mfa,
    mfa_challenge_query,
    issue_mfa_challenge,
    read_mfa_challenge,
    consume_mfa_challenge,
)

from app.services.auth_service.sso import (  # noqa: F401
    resolve_sso_role,
    resolve_sso_organization_id,
    validate_https_discovery_url,
    get_active_sso_providers,
    get_saml_health,
    get_sso_config_or_404,
    rol_desde_grupos,
    _dominio_permitido,
    create_or_update_sso_user,
    sso_timeout_http,
    sso_holgura_de_reloj,
)

from app.services.auth_service.tokens_y_cookies import (  # noqa: F401
    b64url_encode,
    b64url_decode,
    create_ephemeral_token,
    read_ephemeral_token,
    COOKIE_OPTS,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_PATH_ANTIGUA,
    issue_password_reset_token,
    send_password_reset_email,
    revocar_sesiones_del_usuario,
    complete_password_reset,
)

from app.services.auth_service.sesiones_y_usuarios import (  # noqa: F401
    soc_svc,
    commit_db,
    lookup_user_by_id_active,
    lookup_user_by_credentials,
    lookup_user_by_identifier,
    lookup_active_refresh_session,
    get_active_user_sessions,
    revoke_one_session,
    revoke_all_user_sessions_except_current,
    organizacion_desactivada,
    correo_de_usuario,
)

from app.services.auth_service.webauthn import (  # noqa: F401
    user_has_passkeys,
    get_active_user_credentials,
    get_active_webauthn_credential,
    has_remaining_active_credentials,
    get_webauthn_credential_for_auth,
    get_credential_by_credential_id,
    upsert_webauthn_credential,
)

from app.services.auth_service._comun import (  # noqa: F401
    logger,
)
