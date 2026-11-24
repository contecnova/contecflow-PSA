"""Rutas anónimas y sesiones a mano: contexto de tenant DECLARADO (auditoría 22-11-2026, M8).

Informe `docs/auditoria/2026-11-22/01_backend_nucleo_api_seguridad.md`, M8: las
rutas sin `get_current_user` (webhooks, formularios públicos, login, SCIM,
WebSockets...) trabajaban con una sesión sin contexto, y ni el ORM ni RLS
filtraban. Desde el 23-11-2026 `TENANT_SESION_SIN_CONTEXTO=cerrar` es el
defecto: una sesión sin empresa, sin superadmin y sin contexto de sistema
declarado lanza `TenantIsolationError`. Para que eso no rompa nada, cada ruta
anónima declara su contexto:

- su sesión es `Depends(sesion_de_sistema("<motivo>"))` (la búsqueda de la
  credencial —firma, token, slug— corre entre empresas, con nombre), y en
  cuanto resuelve la empresa, `publicar_empresa`/`publicar_contexto_de_tenant`;
- o lo declara en su cuerpo o en lo que llama (`contexto_de_sistema`,
  `declarar_sistema`, `fijar_contexto`, `con_empresa`...);
- o no toca la base, y está en `SIN_BASE` con su motivo.

Tabla ruta → credencial → empresa: `docs/seguridad/rutas_anonimas.md`.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from app.main import app

#: Dependencias que autentican a un usuario o a un cliente del portal.
AUTENTICAN = frozenset({
    "get_current_user", "get_current_client", "get_current_portal_client", "get_portal_client_or_user",
})

#: Llamadas que declaran el contexto de la sesión (empresa o sistema con motivo).
DECLARAN = (
    "sesion_de_sistema(", "contexto_de_sistema(", "declarar_sistema(", "fijar_contexto(",
    "publicar_contexto_de_tenant(", "publicar_empresa(", "con_empresa(", "como_organizacion(",
    "trabajo_de_sistema(", "sin_filtro_de_tenant(",
)

#: Medido el 23-11-2026 importando `app.main` y recorriendo `app.routes`: 93
#: rutas sin ninguna dependencia de `AUTENTICAN` (2 757 rutas en total).
#: Por credencial (detalle en docs/seguridad/rutas_anonimas.md):
#:   25 entrada e identidad (login, MFA/passkey, SSO, refresco, contraseña,
#:      portal, OAuth del portal de desarrolladores, ticket WS del portal);
#:   28 webhooks y canales con firma o secreto (Slack, Teams, WhatsApp, Twilio,
#:      Stripe, GitHub/GitLab, Jira, DocuSign/Adobe, reuniones, correo/SMS
#:      entrante, monitorización, CAB, colaboración);
#:   13 SCIM (token de la empresa, que debe coincidir con {org_id});
#:   13 enlaces o tokens propios (formularios públicos, vista de proyecto,
#:      descarga firmada, marcador compartido, embebido BI, BI por token,
#:      aprobación por correo, agente CMDB);
#:    6 WebSocket (ticket de un uso o JWT fuera de producción);
#:    2 públicas por slug (status page JSON y HTML);
#:   10 sin credencial y sin base (JS estáticos, health/ready, ayudas).
#: De las 93, 13 no abren sesión ORM (`SIN_BASE`).

RUTAS_ANONIMAS = 102  # 23-11-2026 (prueba global): +1 WS /ws/notebook/{page_id} («Mi cuaderno», ticket de un uso, `declarar_sistema` hasta resolver al usuario); +4 del restablecimiento de contraseña (operador y portal); +4 de SAML (login, ACS, canje, SLO)

#: Rutas anónimas que no abren sesión ORM, con su motivo.
SIN_BASE = {
    "POST /api/v1/portal/auth/logout": "revoca el jti del token en Redis/memoria; sin base",
    "GET /api/v1/auth/saml/metadata": "XML estático con BASE_URL",
    "GET /api/v1/collaboration/slash/help": "tabla de comandos del servicio",
    "OPTIONS /api/v1/collaboration/tus": "cabeceras del protocolo tus",
    "GET /api/v1/collaboration/push/public-key": "clave pública VAPID de la configuración",
    "GET /api/v1/esign/webhooks/adobe": "eco del client id de Adobe Sign (global)",
    "GET /api/v1/ai-governance/pii-types": "lista fija de tipos de PII",
    "POST /api/v1/client-errors": "solo escribe en el log",
    "GET /status/page.js": "JavaScript estático",
    "GET /status/embed.js": "JavaScript estático",
    "GET /widget/ticket.js": "JavaScript estático",
    "GET /health": "SELECT 1 por el engine, sin ORM",
    "GET /ready": "SELECT 1 por el engine y ping a Redis, sin ORM",
}


def _nombre(llamable) -> str:
    return getattr(llamable, "__name__", None) or type(llamable).__name__


def _dependencias(dep):
    for d in dep.dependencies:
        yield d.call
        yield from _dependencias(d)


#: Guardas de router de `app.main` (`_ROUTER_GUARDS`), comunes a toda la API.
_GUARDAS_DE_ROUTER = frozenset({"bind_request_timezone", "apply_abac_for_route", "enforce_grc_matrix"})


def _dependencias_propias(dep):
    for d in dep.dependencies:
        if _nombre(d.call) in _GUARDAS_DE_ROUTER:
            continue
        yield d.call
        yield from _dependencias_propias(d)


def _clave(ruta) -> str:
    metodos = sorted(getattr(ruta, "methods", None) or ["WS"])
    return f"{','.join(metodos)} {ruta.path}"


def _rutas_anonimas():
    salida = []
    for ruta in app.routes:
        dep = getattr(ruta, "dependant", None)
        if dep is None:
            continue
        if {_nombre(c) for c in _dependencias(dep)} & AUTENTICAN:
            continue
        salida.append(ruta)
    return salida


def _fuente(llamable) -> str:
    try:
        return textwrap.dedent(inspect.getsource(inspect.unwrap(llamable)))
    except (OSError, TypeError):
        return ""


def _llamadas_del_modulo(funcion) -> list:
    """Funciones del mismo paquete `app.` a las que llama `funcion` (un nivel)."""
    fuente = _fuente(funcion)
    if not fuente:
        return []
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return []
    globales = getattr(inspect.unwrap(funcion), "__globals__", {})
    salida = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        objetivo = None
        if isinstance(f, ast.Name):
            objetivo = globales.get(f.id)
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = globales.get(f.value.id)
            objetivo = getattr(base, f.attr, None) if base is not None else None
        if callable(objetivo) and str(getattr(objetivo, "__module__", "")).startswith("app."):
            salida.append(objetivo)
    return salida


def _como_declara(ruta) -> str | None:
    """El motivo o la marca con que la ruta declara su contexto; None si no lo hace."""
    for llamable in _dependencias(ruta.dependant):
        motivo = getattr(llamable, "motivo_de_sistema", None)
        if motivo:
            return f"sesion_de_sistema: {motivo}"
    candidatos = [ruta.endpoint, *_dependencias(ruta.dependant)]
    candidatos += _llamadas_del_modulo(ruta.endpoint)
    for llamable in candidatos:
        fuente = _fuente(llamable)
        for marca in DECLARAN:
            if marca in fuente:
                return marca
    return None


def test_recuento_exacto_de_rutas_anonimas():
    """Una ruta anónima nueva (o una que deja de serlo) cambia este número a propósito."""
    claves = sorted(_clave(r) for r in _rutas_anonimas())
    assert len(claves) == RUTAS_ANONIMAS, claves


def test_cada_ruta_anonima_declara_su_contexto_o_no_toca_la_base():
    sin_declarar = []
    for ruta in _rutas_anonimas():
        clave = _clave(ruta)
        if clave in SIN_BASE:
            continue
        if _como_declara(ruta) is None:
            sin_declarar.append(clave)
    assert not sin_declarar, (
        "Ruta anónima sin contexto de tenant declarado: usa "
        "`Depends(sesion_de_sistema(\"<motivo>\"))` y publica la empresa al resolverla "
        f"(`publicar_empresa`), o añádela a SIN_BASE con su motivo: {sin_declarar}")


def test_las_de_sin_base_existen_y_no_piden_sesion():
    anonimas = {_clave(r): r for r in _rutas_anonimas()}
    sobran = sorted(set(SIN_BASE) - set(anonimas))
    assert not sobran, f"En SIN_BASE pero ya no es una ruta anónima: {sobran}"
    for clave in SIN_BASE:
        # Sin las guardas de router de `app.main` (`_ROUTER_GUARDS`: zona horaria,
        # ABAC y matriz GRC): cuelgan de TODA la API, piden `get_db` y, sin
        # usuario, vuelven sin consultar. Lo que se mira es la ruta.
        nombres = {_nombre(c) for c in _dependencias_propias(anonimas[clave].dependant)}
        assert "get_db" not in nombres, f"{clave} está en SIN_BASE pero pide sesión"
        assert "SessionLocal(" not in _fuente(anonimas[clave].endpoint), clave


def test_el_defecto_es_cerrar():
    from app.core.config import Settings
    assert Settings.model_fields["TENANT_SESION_SIN_CONTEXTO"].default == "cerrar"




# ── Sesiones creadas a mano en app/ ───────────────────────────────────────────

#: Funciones de `app/` que crean `SessionLocal()` sin declarar el contexto en su
#: cuerpo, con el motivo. Medido el 23-11-2026: antes, 48 sitios con código (54
#: líneas con «SessionLocal()» contando comentarios) y 42 sin declarar nada; hoy
#: 50 sitios (otros cambios añadieron 2), y todos declaran salvo estos.

SESION_SIN_DECLARAR_EN_LA_FUNCION = {
    ("app/db/session.py", "get_db"): "la sesión de la petición: la declara `get_current_user`/portal o `sesion_de_sistema`",
    ("app/db/session.py", "worker_db_session"): "la usan tareas de Celery (`TareaDeSistema`) o `segundo_plano._llamar`, que declaran",
    ("app/db/session.py", "sesion_de_sistema"): "la propia fábrica de la dependencia",
}


def _sitios_de_sesion_a_mano():
    for ruta in sorted(Path("app").rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8")
        if "SessionLocal()" not in texto:
            continue
        arbol = ast.parse(texto)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # la función más interna que contiene la llamada (no las anidadas)
            crea = any(
                isinstance(n, ast.Call)
                and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("SessionLocal", "_SessionLocal")
                for n in _walk_sin_anidadas(nodo))
            if crea:
                yield ruta.as_posix(), nodo.name, ast.get_source_segment(texto, nodo) or ""


def _walk_sin_anidadas(funcion):
    pila = list(funcion.body)
    while pila:
        n = pila.pop()
        yield n
        for hijo in ast.iter_child_nodes(n):
            if not isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pila.append(hijo)


def test_toda_sesion_a_mano_de_app_declara_su_contexto():
    sin_declarar = []
    vistos = 0
    for fichero, funcion, fuente in _sitios_de_sesion_a_mano():
        vistos += 1
        if (fichero, funcion) in SESION_SIN_DECLARAR_EN_LA_FUNCION:
            continue
        if not any(m in fuente for m in DECLARAN):
            sin_declarar.append(f"{fichero}::{funcion}")
    assert vistos >= 40, vistos   # el detector sigue viendo los sitios
    assert not sin_declarar, (
        "`SessionLocal()` a mano sin contexto: añade `declarar_sistema(db, \"<motivo>\")` "
        f"o `fijar_contexto(db, org, \"<motivo>\")` justo después: {sin_declarar}")


# ── Comportamiento: cerrar de verdad, y las anónimas siguen funcionando ──────

def test_sesion_sin_contexto_cierra_con_el_defecto(db):
    from app.db.session import TenantIsolationError
    from app.models.user import User
    from tests.conftest import TestSession
    s = TestSession()
    try:
        with pytest.raises(TenantIsolationError):
            s.query(User).first()
    finally:
        s.close()


def test_declarar_y_fijar_contexto(db):
    from app.db import contexto_de_tenant as ctx
    from tests.conftest import TestSession
    s = TestSession()
    try:
        ctx.declarar_sistema(s, "test")
        assert ctx.estado(s.info) == ctx.LIBRE
        ctx.fijar_contexto(s, "1", "test")
        assert ctx.estado(s.info) == ctx.EMPRESA and s.info["organization_id"] == "1"
    finally:
        s.close()
    s = TestSession()
    try:
        ctx.fijar_contexto(s, None, "sin empresa")
        assert ctx.motivo_de_sistema(s.info) == "sin empresa"
    finally:
        s.close()


@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/api/v1/sd/status-page"),
    ("get", "/status"),
    ("get", "/api/v1/auth/entry-config"),
    ("get", "/api/v1/forms/public/no-existe"),
    ("get", "/api/v1/portal/view/no-es-un-token"),
    ("post", "/api/v1/auth/password/forgot"),
])
def test_rutas_anonimas_responden_con_cerrar(client, metodo, ruta):
    """Con `cerrar`, una ruta anónima no da 500 por sesión sin contexto."""
    kwargs = {"json": {"email_or_username": "nadie@example.com"}} if metodo == "post" else {}
    r = getattr(client, metodo)(ruta, **kwargs)
    assert r.status_code < 500, (ruta, r.status_code, r.text[:300])


def test_login_con_cerrar(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "mala"})
    assert r.status_code in (400, 401, 403, 429), r.text[:300]
