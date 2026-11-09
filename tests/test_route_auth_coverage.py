"""Guardrail: toda ruta /api declara autenticación como DEPENDENCIA, o es pública a propósito.

Por qué existe este test (auditoría 2026-07, docs/AUDIT_2026_07_FULL.md §1.3):

La superficie del portal de cliente autenticaba llamando a `require_portal_client(...)`
DENTRO del handler en lugar de vía `Depends`. Consecuencia: la authz era invisible para
cualquier herramienta, no aparecía en OpenAPI y no había red de seguridad en tiempo de
colección. Dos endpoints acabaron descartando el principal o sin acotar por tenant, y
eso produjo dos IDOR cross-tenant reales (CSAT y comentarios de portal).

Este test recorre `route.dependant` —el árbol que FastAPI resuelve de verdad en cada
request— y exige que cada ruta tenga una dependencia de auth reconocida o figure en
PUBLIC_ROUTES con un motivo. Así, una ruta nueva sin auth rompe CI en vez de pasar
inadvertida.

Si añades una ruta pública legítima, añádela a PUBLIC_ROUTES CON SU MOTIVO. Si la
autenticas dentro del cuerpo, este test fallará: conviértela en dependencia.
"""

from app.main import app


# Dependencias que constituyen autenticación. Nombres EXACTOS a propósito: una
# coincidencia por substring daría falsos positivos y dejaría pasar rutas abiertas.
AUTH_DEPENDENCY_NAMES = frozenset({
    # Usuarios internos
    "get_current_user",
    "require_admin",
    "require_any_manager",
    "require_admin_or_pm",
    "require_superadmin",
    "_require_admin",
    # Clientes del portal
    "get_current_client",
    "get_current_portal_client",
    # Cliente del portal o usuario interno (catalogo y base de conocimiento).
    "get_portal_client_or_user",
    # Tokens de máquina / integraciones
    "_require_scim_token",
    "get_bi_token",
})


# Rutas públicas por diseño. La clave es (método, path); el valor, el motivo.
# Regla: nada entra aquí sin una razón que sobreviva a una revisión de seguridad.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    # ── Flujos de autenticación (no pueden exigir autenticación previa) ──────
    ("POST", "/api/v1/auth/login"): "emite el token",
    ("POST", "/api/v1/auth/refresh"): "rota el token vía cookie",
    ("POST", "/api/v1/auth/mfa/validate"): "segundo factor durante el login",
    ("POST", "/api/v1/auth/mfa/webauthn/authenticate/start"): "reto WebAuthn previo al login",
    # Auditoria 2026-11: acceso con passkey sin contrasena; la passkey es la credencial.
    ("POST", "/api/v1/auth/passkey/login/start"): "reto WebAuthn del acceso sin contraseña",
    ("POST", "/api/v1/auth/passkey/login/finish"): "acceso sin contraseña: verifica la passkey",
    ("GET", "/api/v1/approvals/email-decision"): "enlace del correo de aprobación: el token firmado identifica al aprobador y solo enseña el resumen",
    ("POST", "/api/v1/approvals/email-decision"): "decidir con el enlace del correo: token firmado, de un aprobador y un paso, con caducidad",
    ("POST", "/api/v1/auth/select-organization"): "elegir empresa tras la contraseña: exige el token de elección firmado",
    ("GET", "/api/v1/auth/entry-config"): "el login necesita saber el modo de entrada y la marca de la empresa del host",
    ("POST", "/api/v1/auth/mfa/webauthn/authenticate/finish"): "respuesta WebAuthn que emite el token",
    ("GET", "/api/v1/auth/sso/{config_id}/authorize"): "redirección al IdP",
    ("POST", "/api/v1/auth/password/forgot"): "recuperación de contraseña",
    ("POST", "/api/v1/auth/password/reset"): "reset con token de un solo uso",
    ("GET", "/api/v1/auth/saml/metadata"): "metadata SP de SAML, público por spec",
    ("GET", "/api/v1/auth/sso/providers"): "lista de IdP para pintar el botón de login",
    ("POST", "/api/v1/auth/sso/{config_id}/callback"): "callback del IdP",
    ("POST", "/api/v1/portal/auth/login"): "emite el token de portal",
    ("POST", "/api/v1/portal/auth/logout"): "revoca sesión de portal",
    ("POST", "/api/v1/bookings/api-keys/verify"): "verificación de API key (rate-limit aparte)",
    # ── OAuth2 como proveedor (developer portal) ─────────────────────────────
    ("POST", "/api/v1/developer/token"): "token endpoint OAuth2: autentica por client_credentials",
    ("POST", "/api/v1/developer/token/revoke"): "revocación OAuth2: autentica por el propio token",
    ("GET", "/api/v1/developer/userinfo"): "userinfo OIDC: autentica por bearer del propio flujo",
    ("GET", "/api/v1/collaboration/integrations/oauth/callback"): "callback OAuth de integración",
    # ── Webhooks entrantes: firmados con HMAC dentro del handler ─────────────
    ("POST", "/api/v1/git/webhooks/github"): "HMAC de GitHub",
    ("POST", "/api/v1/git/webhooks/gitlab"): "token de GitLab",
    ("POST", "/api/v1/jira/webhook"): "HMAC de Jira",
    ("POST", "/api/v1/integrations/jira/webhook"): "HMAC de Jira",
    ("POST", "/api/v1/esign/webhooks/docusign"): "HMAC de DocuSign",
    ("POST", "/api/v1/esign/webhooks/adobe"): "HMAC de Adobe Sign",
    ("GET", "/api/v1/esign/webhooks/adobe"): "handshake de verificación de Adobe Sign",
    ("POST", "/api/v1/integrations-hub/slack/commands"): "firma de Slack",
    ("POST", "/api/v1/integrations-hub/teams/commands"): "firma de Teams",
    ("POST", "/api/v1/sd/voice/webhook/twilio"): "firma de Twilio",
    ("POST", "/api/v1/sd/voice/webhook/twilio/gather"): "firma de Twilio",
    ("POST", "/api/v1/sd/inbound-email"): "secreto de email entrante",
    ("POST", "/api/v1/sd/multichannel/inbound/email"): "secreto de email entrante",
    ("POST", "/api/v1/sd/events/{source}"): "token de monitorización de la organización (X-Contecflow-Event-Token)",
    ("POST", "/api/v1/sd/multichannel/inbound/sms"): "secreto de SMS entrante",
    ("POST", "/api/v1/collaboration/webhooks/incoming/{token}"): "token de capacidad en la URL",
    ("POST", "/api/v1/sd/cmdb/agents/checkin"): "token de registro del agente CMDB",
    # Slug secreto con expiración (slug_expires_at) + HMAC X-Contecflow-Signature
    # + rate-limit 20/min. Ver app/api/v1/endpoints/cab.py:180.
    ("POST", "/api/v1/webhooks/fire/{slug}"): "slug secreto caducable + HMAC + rate-limit",
    # ── Enlaces de capacidad: el token de la URL ES la credencial ────────────
    ("GET", "/api/v1/forms/public/{token}"): "formulario público por token",
    ("POST", "/api/v1/forms/public/{token}/submit"): "envío de formulario público por token",
    ("GET", "/api/v1/portal/view/{token}"): "vista de estado compartida por token",
    ("GET", "/api/v1/collaboration/files/by-token/{token}"): "descarga por token de capacidad",
    ("GET", "/api/v1/bi/bookmarks/shared/{share_token}"): "bookmark de BI compartido por token",
    # ── Contenido deliberadamente público (portal/status page) ───────────────
    ("GET", "/api/v1/sd/status-page"): "página de estado pública",
    ("GET", "/api/v1/collaboration/push/public-key"): "clave pública VAPID",
    ("GET", "/api/v1/collaboration/slash/help"): "ayuda estática de comandos",
    ("GET", "/api/v1/ai-governance/pii-types"): "catálogo estático de tipos de PII",
    ("GET", "/api/v1/bi/embed/sdk-config"): "config pública del SDK de embed",
    ("GET", "/api/v1/bi/embed/view"): "página de indicadores para un iframe (Teams, SharePoint); el token de embed es la credencial y se valida dentro",
    ("OPTIONS", "/api/v1/collaboration/tus"): "descubrimiento de capacidades TUS por spec",
    # ── Tickets WebSocket: la credencial se valida al abrir el socket ────────
    ("GET", "/api/v1/ws/portal-ticket"): "emite ticket WS de un solo uso para el portal",
    # El chat IA del portal ya NO está aquí: desde la auditoría 2026-08 §6 exige
    # Depends(get_current_portal_client) y tiene rate limit, así que lo cubre el
    # camino normal de este test.
}


# Los WebSocket no llevan métodos HTTP y autentican por ticket al hacer el handshake.
PUBLIC_WEBSOCKETS = frozenset({
    "/api/v1/ws/notifications",
    "/api/v1/ws/doc/{doc_id}",
    "/api/v1/ws/portal-notifications",
    "/api/v1/collaboration/ws",
    "/api/v1/bi/collaboration/dashboards/{dashboard_key}/updates",
    "/api/v1/bi/intelligence/realtime/stream",
})


def _dependency_names(dependant, seen=None) -> set[str]:
    """Nombres de todas las dependencias del árbol, recursivamente."""
    if seen is None:
        seen = set()
    names: set[str] = set()
    call = getattr(dependant, "call", None)
    if call is not None:
        names.add(getattr(call, "__name__", ""))
    for sub in getattr(dependant, "dependencies", []) or []:
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        names |= _dependency_names(sub, seen)
    return names


def _api_routes():
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        if getattr(route, "dependant", None) is None:
            continue
        yield route, path, sorted(getattr(route, "methods", []) or [])


def test_every_api_route_declares_auth_as_dependency_or_is_explicitly_public() -> None:
    offenders: list[str] = []

    for route, path, methods in _api_routes():
        names = _dependency_names(route.dependant)
        if names & AUTH_DEPENDENCY_NAMES:
            continue
        if not methods:  # WebSocket
            if path not in PUBLIC_WEBSOCKETS:
                offenders.append(f"WS {path}")
            continue
        for method in methods:
            if method in ("HEAD",):
                continue
            if (method, path) not in PUBLIC_ROUTES:
                offenders.append(f"{method} {path}")

    assert not offenders, (
        "Rutas sin dependencia de autenticación y sin entrada en PUBLIC_ROUTES.\n"
        "Si la ruta autentica dentro del handler, conviértela en dependencia "
        "(ver get_current_portal_client). Si es pública de verdad, añádela a "
        "PUBLIC_ROUTES con su motivo.\n  - " + "\n  - ".join(sorted(offenders))
    )


def test_public_allowlist_has_no_stale_entries() -> None:
    """Impide que el allowlist acumule rutas que ya no existen o que ya autentican.

    Sin esto el allowlist se convierte en un cajón de sastre que va tapando rutas
    reales a medida que se renombran paths.
    """
    live: set[tuple[str, str]] = set()
    for route, path, methods in _api_routes():
        names = _dependency_names(route.dependant)
        if names & AUTH_DEPENDENCY_NAMES:
            continue
        for method in methods:
            live.add((method, path))

    stale = sorted(f"{m} {p}" for (m, p) in PUBLIC_ROUTES if (m, p) not in live)
    assert not stale, (
        "Entradas de PUBLIC_ROUTES que ya no corresponden a una ruta sin auth "
        "(renombrada, eliminada, o ya protegida). Bórralas:\n  - " + "\n  - ".join(stale)
    )
