"""Cliente común de contecflow como aplicación anfitriona de contecmind y contecintelligence.

Revisión 2026-11. Los dos productos exponen el mismo protocolo para una
aplicación de la casa (medido en su OpenAPI el 05-11-2026):

1. credencial de aplicación → token de APLICACIÓN
   (`POST {api}/oauth/token`, `client_credentials`), que se guarda hasta poco
   antes de caducar;
2. ese token se canjea por uno DELEGADO de la persona que está usando
   contecflow (`POST {api}/tokens/exchange` con `tenant`, `subject`, `role`,
   `scopes`, `ttl_s`). El otro producto aplica SUS permisos a esa persona: lo
   que ve en contecflow no amplía lo que ve allí;
3. con el token delegado se llama a la API.

El `tenant` que se manda es la empresa de contecflow; el otro producto lo
traduce por el mapeo de la aplicación (si no está dada de alta, 403 y aquí
`no_alta`). El rol se rebaja según los roles de contecflow configurados en
Admin (`CONTECMIND_WRITER_ROLES`, `CONTECINTELLIGENCE_ANALYST_ROLES`).

Cada llamada queda en `conector_llamadas` (operación, resultado, latencia), que
es lo que enseña el panel de estado. Un fallo al registrar no rompe la llamada.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.services.integration_credentials_service import get_provider_config

logger = logging.getLogger("contecflow.conectores")

_lock = threading.Lock()
_tokens_de_aplicacion: dict[tuple, tuple[float, str]] = {}
_tokens_de_usuario: dict[tuple, tuple[float, str]] = {}
_MARGEN_S = 30


@dataclass(frozen=True)
class Producto:
    clave: str             # la del registro de credenciales
    api: str               # prefijo de su API
    rol_lector: str
    rol_escritor: str
    ajuste_roles: str      # ajuste con los roles de contecflow que reciben el rol alto
    # contecmind: el rol alto sólo para lo que escribe (leer con el mínimo).
    # contecintelligence: el rol es de la PERSONA (un analista ve métricas también al preguntar).
    rol_alto_solo_al_escribir: bool
    # Sus rutas de salud SIN autenticación: «¿está vivo?» y «¿puede atender?».
    # Medido el 05-11-2026: en contecintelligence `/health` exige sesión (401);
    # las públicas son `/livez` y `/readyz`. En contecmind, `/health` y `/health/ready`.
    ruta_vivo: str
    ruta_listo: str


CONTECMIND = Producto("contecmind", "/api/v1", "reader", "writer", "CONTECMIND_WRITER_ROLES", True,
                      "/health", "/health/ready")
CONTECINTELLIGENCE = Producto("contecintelligence", "/api", "viewer", "analyst", "CONTECINTELLIGENCE_ANALYST_ROLES",
                              False, "/livez", "/readyz")
PRODUCTOS = {p.clave: p for p in (CONTECMIND, CONTECINTELLIGENCE)}


class ErrorDeConector(Exception):
    """Un fallo con nombre, para que la pantalla diga QUÉ falla y no «error».

    `codigo`: no_configurado | no_alta | sin_permiso | no_encontrado |
    rechazado | no_responde | no_listo (vivo, pero su `readyz` dice que no puede atender).
    """

    def __init__(self, codigo: str, detalle: str = "", estado_http: Optional[int] = None):
        super().__init__(detalle or codigo)
        self.codigo = codigo
        self.detalle = detalle or codigo
        self.estado_http = estado_http


# ── Ajustes ───────────────────────────────────────────────────────────────────

def _ajuste(db: Session, clave: str, org_id: Optional[str], tipo: str):
    from app.services import settings_service as s
    lector = {"float": s.get_runtime_float, "int": s.get_runtime_int,
              "bool": s.get_runtime_bool, "str": s.get_runtime_str}[tipo]
    return lector(db, clave, org_id)


def timeout(db: Session, org_id: Optional[str]) -> float:
    return float(_ajuste(db, "CONECTOR_TIMEOUT_SECONDS", org_id, "float"))


def roles_altos(db: Session, producto: Producto, org_id: Optional[str]) -> set[str]:
    return {r.strip() for r in str(_ajuste(db, producto.ajuste_roles, org_id, "str") or "").split(",") if r.strip()}


def configuracion(db: Session, producto: Producto, org_id: Optional[str]) -> dict:
    cfg = get_provider_config(db, producto.clave, org_id=org_id)
    if not (cfg.get("base_url") and cfg.get("client_id") and cfg.get("client_secret")):
        raise ErrorDeConector("no_configurado", f"{producto.clave} no está configurado (Ajustes → Integraciones)")
    cfg["base_url"] = str(cfg["base_url"]).rstrip("/")
    return cfg


def configurado(db: Session, producto: Producto, org_id: Optional[str]) -> bool:
    try:
        configuracion(db, producto, org_id)
        return True
    except ErrorDeConector:
        return False


def rol_de(db: Session, producto: Producto, usuario, escribir: bool = False) -> str:
    """El rol que se pide al canjear: el alto sólo si hace falta Y el rol de contecflow lo permite."""
    rol = getattr(getattr(usuario, "role", None), "value", getattr(usuario, "role", None))
    hace_falta = escribir or not producto.rol_alto_solo_al_escribir
    if hace_falta and str(rol) in roles_altos(db, producto, usuario.organization_id):
        return producto.rol_escritor
    return producto.rol_lector


def puede_escribir(db: Session, producto: Producto, usuario) -> bool:
    return rol_de(db, producto, usuario, escribir=True) == producto.rol_escritor


# ── Tokens ────────────────────────────────────────────────────────────────────

def _clave_de_aplicacion(producto: Producto, cfg: dict) -> tuple:
    """Clave de la cache del token de aplicacion.

    Revision multitenant 2026-11b: con (producto, url, client_id) de clave, el
    administrador de otra empresa que escribiera la url y el client_id de esta
    con un secreto cualquiera reutilizaba su token: el secreto no se comprobaba
    nunca. La huella del secreto entra en la clave.
    """
    import hashlib
    huella = hashlib.sha256(str(cfg["client_secret"]).encode()).hexdigest()
    return (producto.clave, cfg["base_url"], cfg["client_id"], huella)


def _token_de_aplicacion(producto: Producto, cfg: dict, plazo: float) -> str:
    clave = _clave_de_aplicacion(producto, cfg)
    with _lock:
        guardado = _tokens_de_aplicacion.get(clave)
        if guardado and guardado[0] > time.monotonic() + _MARGEN_S:
            return guardado[1]
    r = httpx.post(cfg["base_url"] + producto.api + "/oauth/token", timeout=plazo, json={
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"], "grant_type": "client_credentials"})
    if r.status_code in (400, 401, 403):
        raise ErrorDeConector("rechazado", f"{producto.clave} rechaza la credencial de la aplicación", r.status_code)
    r.raise_for_status()
    datos = r.json()
    token = str(datos.get("access_token") or "")
    if not token:
        raise ErrorDeConector("rechazado", f"{producto.clave} no ha devuelto token de aplicación")
    with _lock:
        _tokens_de_aplicacion[clave] = (time.monotonic() + float(datos.get("expires_in") or 300), token)
    return token


def _token_de_usuario(db: Session, producto: Producto, cfg: dict, usuario, alcances: tuple[str, ...],
                      rol: str, plazo: float, extra: Optional[dict] = None) -> str:
    org = str(usuario.organization_id or "")
    if not org:
        raise ErrorDeConector("no_alta", "El usuario no tiene empresa: no se puede canjear su identidad")
    sujeto = usuario.email or usuario.username
    clave = (producto.clave, cfg["base_url"], org, sujeto, rol, alcances, repr(sorted((extra or {}).items())))
    with _lock:
        guardado = _tokens_de_usuario.get(clave)
        if guardado and guardado[0] > time.monotonic() + _MARGEN_S:
            return guardado[1]
    app = _token_de_aplicacion(producto, cfg, plazo)
    ttl = int(_ajuste(db, "CONECTOR_TOKEN_TTL_SECONDS", usuario.organization_id, "int"))
    cuerpo = {"tenant": org, "subject": sujeto, "role": rol, "scopes": list(alcances), "ttl_s": ttl, **(extra or {})}
    r = httpx.post(cfg["base_url"] + producto.api + "/tokens/exchange", timeout=plazo,
                   headers={"Authorization": f"Bearer {app}"}, json=cuerpo)
    if r.status_code == 403:
        raise ErrorDeConector("no_alta", f"Esta empresa no está dada de alta en {producto.clave}, o la aplicación "
                                         f"no tiene esos permisos ({', '.join(alcances)})", 403)
    if r.status_code in (400, 401, 422):
        raise ErrorDeConector("rechazado", f"{producto.clave} rechaza el canje: {r.text[:200]}", r.status_code)
    r.raise_for_status()
    datos = r.json()
    token = str(datos.get("access_token") or datos.get("token") or "")
    if not token:
        raise ErrorDeConector("rechazado", f"{producto.clave} no ha devuelto token delegado")
    with _lock:
        _tokens_de_usuario[clave] = (time.monotonic() + float(datos.get("expires_in") or ttl), token)
    return token


def token_delegado(db: Session, producto: Producto, usuario, alcances: tuple[str, ...], *,
                   escribir: bool = False, extra: Optional[dict] = None) -> tuple[str, int, str]:
    """`(token, segundos, base_url)` para que una pantalla hable con el otro producto directamente.

    Se usa con los componentes de contecintelligence (`<ci-chat>`, `<ci-metric>`),
    que piden el token a contecflow y nunca ven la credencial de la aplicación.
    """
    cfg = configuracion(db, producto, usuario.organization_id)
    plazo = timeout(db, usuario.organization_id)
    inicio = time.monotonic()
    try:
        token = _token_de_usuario(db, producto, cfg, usuario, alcances, rol_de(db, producto, usuario, escribir),
                                  plazo, extra)
    except ErrorDeConector as e:
        registrar(db, producto, "token", usuario, inicio, ok=False, estado=e.estado_http, error=e.detalle)
        raise
    except httpx.HTTPError as e:
        registrar(db, producto, "token", usuario, inicio, ok=False, error=str(e)[:500])
        raise ErrorDeConector("no_responde", f"{producto.clave} no responde") from e
    registrar(db, producto, "token", usuario, inicio, ok=True, estado=200)
    ttl = int(_ajuste(db, "CONECTOR_TOKEN_TTL_SECONDS", usuario.organization_id, "int"))
    return token, ttl, cfg["base_url"]


def olvidar_tokens(producto: Optional[Producto] = None) -> None:
    """Tras cambiar la credencial: los tokens guardados son de la anterior."""
    with _lock:
        for cache in (_tokens_de_aplicacion, _tokens_de_usuario):
            for k in [k for k in cache if producto is None or k[0] == producto.clave]:
                cache.pop(k, None)


# ── Llamada ───────────────────────────────────────────────────────────────────

def registrar(db: Session, producto: Producto, operacion: str, usuario, inicio: float, *, ok: bool,
              estado: Optional[int] = None, error: Optional[str] = None) -> None:
    from app.models.conectores import ConectorLlamada
    try:
        db.add(ConectorLlamada(
            organization_id=getattr(usuario, "organization_id", None), producto=producto.clave, operacion=operacion,
            ok=ok, estado_http=estado, ms=int((time.monotonic() - inicio) * 1000),
            error=(error or None) and str(error)[:500], user_id=getattr(usuario, "id", None)))
        db.commit()
    except Exception:
        logger.warning("No se pudo registrar la llamada al conector", exc_info=True)
        db.rollback()


def _error_de_respuesta(producto: Producto, r: httpx.Response) -> ErrorDeConector:
    try:
        cuerpo = r.json()
        detalle = cuerpo.get("detail") or cuerpo.get("title") or cuerpo.get("message") or r.text
    except ValueError:
        detalle = r.text
    if isinstance(detalle, (list, dict)):
        detalle = str(detalle)
    detalle = str(detalle)[:300]
    codigo = {401: "rechazado", 403: "sin_permiso", 404: "no_encontrado"}.get(r.status_code, "rechazado")
    if r.status_code >= 500:
        codigo = "no_responde"
    return ErrorDeConector(codigo, f"{producto.clave}: {detalle}", r.status_code)


def llamar(db: Session, producto: Producto, usuario, operacion: str, metodo: str, ruta: str, *,
           alcances: tuple[str, ...], escribir: bool = False, params: Optional[dict] = None,
           json: Any = None, data: Optional[dict] = None, files: Any = None,
           headers: Optional[dict] = None, plazo: Optional[float] = None,
           extra_canje: Optional[dict] = None) -> httpx.Response:
    """Una llamada a la API del otro producto con la identidad del usuario. Lanza `ErrorDeConector`."""
    cfg = configuracion(db, producto, usuario.organization_id)
    plazo = plazo or timeout(db, usuario.organization_id)
    inicio = time.monotonic()
    try:
        token = _token_de_usuario(db, producto, cfg, usuario, alcances, rol_de(db, producto, usuario, escribir),
                                  plazo, extra_canje)
        r = httpx.request(metodo, cfg["base_url"] + producto.api + ruta, params=params, json=json, data=data,
                          files=files, timeout=plazo,
                          headers={"Authorization": f"Bearer {token}", **(headers or {})})
    except ErrorDeConector as e:
        registrar(db, producto, operacion, usuario, inicio, ok=False, estado=e.estado_http, error=e.detalle)
        raise
    except httpx.HTTPError as e:
        registrar(db, producto, operacion, usuario, inicio, ok=False, error=f"{type(e).__name__}: {e}"[:500])
        raise ErrorDeConector("no_responde", f"{producto.clave} no responde") from e
    if r.status_code >= 400:
        err = _error_de_respuesta(producto, r)
        registrar(db, producto, operacion, usuario, inicio, ok=False, estado=r.status_code, error=err.detalle)
        raise err
    registrar(db, producto, operacion, usuario, inicio, ok=True, estado=r.status_code)
    return r


def abrir_flujo(db: Session, producto: Producto, usuario, operacion: str, metodo: str, ruta: str, *,
                alcances: tuple[str, ...], json: Any = None, plazo: Optional[float] = None,
                extra_canje: Optional[dict] = None):
    """Para respuestas largas (descargas, SSE): devuelve `(cliente, respuesta)` abiertos.

    Quien llama itera `respuesta.iter_bytes()` y cierra los dos al terminar
    (`cerrar_flujo`). El registro se hace al abrir: lo que importa para el
    estado es si el otro producto contestó.
    """
    cfg = configuracion(db, producto, usuario.organization_id)
    plazo = plazo or timeout(db, usuario.organization_id)
    inicio = time.monotonic()
    try:
        token = _token_de_usuario(db, producto, cfg, usuario, alcances, rol_de(db, producto, usuario), plazo,
                                  extra_canje)
        cliente = httpx.Client(timeout=httpx.Timeout(plazo, read=plazo))
        peticion = cliente.build_request(metodo, cfg["base_url"] + producto.api + ruta, json=json,
                                         headers={"Authorization": f"Bearer {token}"})
        r = cliente.send(peticion, stream=True)
    except ErrorDeConector as e:
        registrar(db, producto, operacion, usuario, inicio, ok=False, estado=e.estado_http, error=e.detalle)
        raise
    except httpx.HTTPError as e:
        registrar(db, producto, operacion, usuario, inicio, ok=False, error=f"{type(e).__name__}: {e}"[:500])
        raise ErrorDeConector("no_responde", f"{producto.clave} no responde") from e
    if r.status_code >= 400:
        r.read()
        err = _error_de_respuesta(producto, r)
        cerrar_flujo(cliente, r)
        registrar(db, producto, operacion, usuario, inicio, ok=False, estado=r.status_code, error=err.detalle)
        raise err
    registrar(db, producto, operacion, usuario, inicio, ok=True, estado=r.status_code)
    return cliente, r


def cerrar_flujo(cliente, respuesta) -> None:
    for cosa in (respuesta, cliente):
        try:
            cosa.close()
        except Exception:
            logger.debug("No se pudo cerrar el flujo del conector", exc_info=True)


# ── Prueba de conexión y estado ───────────────────────────────────────────────

def probar(db: Session, producto: Producto, org_id: Optional[str]) -> dict:
    """Para «Probar conexión»: credencial de aplicación y, si hay, la ruta pública de salud.

    No canjea una identidad (no hay usuario): eso lo prueba `probar_con_usuario`.
    """
    try:
        cfg = configuracion(db, producto, org_id)
    except ErrorDeConector as e:
        return {"ok": False, "codigo": e.codigo, "detail": e.detalle}
    plazo = timeout(db, org_id)
    inicio = time.monotonic()
    try:
        vivo = httpx.get(cfg["base_url"] + producto.ruta_vivo, timeout=plazo)
        if vivo.status_code != 200:
            return {"ok": False, "codigo": "no_responde",
                    "detail": f"{producto.clave} no está vivo: {producto.ruta_vivo} responde {vivo.status_code}"}
        listo = httpx.get(cfg["base_url"] + producto.ruta_listo, timeout=plazo)
        if listo.status_code != 200:
            return {"ok": False, "codigo": "no_listo",
                    "detail": f"{producto.clave} está vivo pero no puede atender: {producto.ruta_listo} "
                              f"responde {listo.status_code} {listo.text[:200]}"}
        _tokens_de_aplicacion.pop(_clave_de_aplicacion(producto, cfg), None)
        _token_de_aplicacion(producto, cfg, plazo)
    except ErrorDeConector as e:
        return {"ok": False, "codigo": e.codigo, "detail": e.detalle}
    except httpx.HTTPError as e:
        return {"ok": False, "codigo": "no_responde", "detail": f"{producto.clave} no responde: {type(e).__name__}"}
    return {"ok": True, "codigo": "ok", "ms": int((time.monotonic() - inicio) * 1000),
            "detail": f"{producto.clave} acepta la credencial de la aplicación"}


def probar_con_usuario(db: Session, producto: Producto, usuario) -> dict:
    """El canje de la identidad de quien prueba: dice si la EMPRESA está dada de alta."""
    alcances = ("documents:search",) if producto is CONTECMIND else ("sources:read",)
    try:
        token_delegado(db, producto, usuario, alcances)
    except ErrorDeConector as e:
        return {"ok": False, "codigo": e.codigo, "detail": e.detalle}
    return {"ok": True, "codigo": "ok", "detail": f"La empresa está dada de alta en {producto.clave}"}
