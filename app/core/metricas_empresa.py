"""Métricas por empresa con cardinalidad acotada (22-11-2026).

Todas las métricas «por empresa» llevan la etiqueta `empresa`, y su valor sale
SIEMPRE de `etiqueta_de_empresa()`:

* Es el `slug` de la organización (o su id con `METRICS_TENANT_LABEL=id`). Una
  empresa es una persona jurídica: su identificador no es un dato personal. En
  las etiquetas NUNCA van ids, nombres ni correos de usuarios, IPs ni texto
  libre (lo vigila `tests/test_metricas_observabilidad.py`).
* Solo las `METRICS_TENANT_MAX` primeras empresas por fecha de alta tienen
  etiqueta propia; el resto suma en `otras`. Sin este tope, cada empresa nueva
  multiplicaría las series de Prometheus (ruta × código × empresa…).
* Sin empresa (superadmin de plataforma, peticiones anónimas, trabajos de
  fondo): `sin_empresa`.

El mapa id → etiqueta se cachea por proceso `_TTL` segundos; refrescarlo es una
consulta sobre `organizations` (id, slug, alta). Nada de esto lanza nunca: una
métrica no puede romper una petición.

También vive aquí el middleware HTTP por empresa (peticiones, latencia y
errores por ruta-plantilla y código de error del catálogo) y los contadores de
login y de IA que se incrementan en caliente.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

from prometheus_client import Counter, Histogram

logger = logging.getLogger("contecflow.metrics")

SIN_EMPRESA = "sin_empresa"
OTRAS = "otras"
_TTL = 300.0
_NO_VALIDO = re.compile(r"[^a-z0-9_-]+")

_cache: dict = {"hasta": 0.0, "mapa": {}}
_cerrojo = threading.Lock()


def _limpiar(valor: str) -> str:
    """Solo [a-z0-9_-], 63 caracteres como mucho: una etiqueta de Prometheus segura."""
    return (_NO_VALIDO.sub("-", (valor or "").lower()).strip("-") or "x")[:63]


def _cargar_mapa(db=None) -> dict:
    """{org_id: etiqueta} con las `METRICS_TENANT_MAX` primeras empresas por alta."""
    from app.core.config import settings
    from app.models.mfa import Organization

    propia = db is None
    if propia:
        from app.db.session import SessionLocal
        db = SessionLocal()
    try:
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):
            filas = (db.query(Organization.id, Organization.slug)
                     .order_by(Organization.created_at.asc(), Organization.id.asc()).all())
    finally:
        if propia:
            db.close()
    tope = max(0, int(settings.METRICS_TENANT_MAX or 0))
    por_id = (settings.METRICS_TENANT_LABEL or "slug").strip().lower() == "id"
    mapa = {}
    for i, (org_id, slug) in enumerate(filas):
        if i < tope:
            mapa[str(org_id)] = _limpiar(str(org_id) if por_id or not slug else slug)
        else:
            mapa[str(org_id)] = OTRAS
    return mapa


def mapa_de_empresas(db=None, *, forzar: bool = False) -> dict:
    """El mapa id → etiqueta, cacheado `_TTL` segundos por proceso."""
    ahora = time.monotonic()
    if not forzar and _cache["hasta"] > ahora:
        return _cache["mapa"]
    with _cerrojo:
        if not forzar and _cache["hasta"] > time.monotonic():
            return _cache["mapa"]
        try:
            _cache["mapa"] = _cargar_mapa(db)
            _cache["hasta"] = time.monotonic() + _TTL
        except Exception:
            # Sin base (arranque, pruebas): se reintenta en 30 s con lo que hubiera.
            logger.debug("mapa_de_empresas: no se pudo refrescar", exc_info=True)
            _cache["hasta"] = time.monotonic() + 30.0
        return _cache["mapa"]


def invalidar_cache() -> None:
    _cache["hasta"] = 0.0
    _cache["mapa"] = {}
    _cache.pop("forzado", None)


def etiqueta_de_empresa(org_id, db=None) -> str:
    """La etiqueta `empresa` de una organización (acotada; ver cabecera)."""
    if not org_id:
        return SIN_EMPRESA
    if not _activas():
        # Sin /metrics nadie lee la etiqueta: no se toca la base por ella.
        return OTRAS
    try:
        mapa = mapa_de_empresas(db)
        etiqueta = mapa.get(str(org_id))
        if etiqueta is None:
            # Empresa creada después del último refresco: se refresca, como mucho
            # una vez cada 30 s (un id que no existe no puede costar una consulta
            # por petición).
            if time.monotonic() - _cache.get("forzado", -1e9) > 30.0:
                _cache["forzado"] = time.monotonic()
                mapa = mapa_de_empresas(db, forzar=True)
            etiqueta = mapa.get(str(org_id), OTRAS)
        return etiqueta
    except Exception:
        logger.debug("etiqueta_de_empresa: fallo best-effort", exc_info=True)
        return OTRAS


def _activas() -> bool:
    try:
        from app.core.config import settings
        return bool(settings.METRICS_ENABLED)
    except Exception:
        logger.debug("_activas: excepcion ignorada", exc_info=True)
        return False


# ── Contadores en caliente ───────────────────────────────────────────────────

logins_total = Counter(
    "contecflow_logins_total",
    "Intentos de login por empresa y resultado (correcto | fallido | bloqueado).",
    labelnames=("empresa", "resultado"),
)

ia_peticiones_total = Counter(
    "contecflow_ia_peticiones_total",
    "Llamadas a proveedores de IA por empresa, módulo y resultado (ok | error).",
    labelnames=("empresa", "modulo", "resultado"),
)

ia_tokens_total = Counter(
    "contecflow_ia_tokens_total",
    "Tokens de IA por empresa, módulo y sentido (entrada | salida).",
    labelnames=("empresa", "modulo", "sentido"),
)

ia_coste_usd_total = Counter(
    "contecflow_ia_coste_usd_total",
    "Coste estimado de IA (USD) por empresa y módulo.",
    labelnames=("empresa", "modulo"),
)

ia_presupuesto_agotado_total = Counter(
    "contecflow_ia_presupuesto_agotado_total",
    "Llamadas a IA cortadas por el tope diario de gasto de la empresa (AI_DAILY_BUDGET_USD).",
    labelnames=("empresa",),
)

http_peticiones_empresa_total = Counter(
    "contecflow_http_peticiones_empresa_total",
    "Peticiones HTTP por empresa y estado (2xx/3xx/4xx/5xx; 401, 403, 404 y 429 aparte).",
    labelnames=("empresa", "estado"),
)

http_duracion_empresa_seconds = Histogram(
    "contecflow_http_duracion_empresa_seconds",
    "Latencia de las peticiones HTTP por empresa.",
    labelnames=("empresa",),
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

http_errores_total = Counter(
    "contecflow_http_errores_total",
    "Respuestas de error (>=400) por empresa, ruta-plantilla, estado y código del catálogo de errores.",
    labelnames=("empresa", "ruta", "estado", "codigo"),
)

_CODIGO = re.compile(r"^[a-z0-9_]{1,60}$")
_MODULO = re.compile(r"[^a-z0-9_.-]+")


def _modulo(valor) -> str:
    return (_MODULO.sub("_", str(valor or "desconocido").lower())[:40]) or "desconocido"


def contar_login(resultado: str, org_id=None) -> None:
    """Un intento de login. Nunca lanza; sin METRICS_ENABLED no hace nada."""
    if not _activas():
        return
    try:
        logins_total.labels(empresa=etiqueta_de_empresa(org_id) if org_id else "desconocida",
                            resultado=resultado).inc()
    except Exception:
        logger.debug("contar_login: fallo best-effort", exc_info=True)


def contar_uso_de_ia(org_id, modulo, *, ok: bool, tokens_in=0, tokens_out=0, coste_usd=0.0) -> None:
    if not _activas():
        return
    try:
        empresa, mod = etiqueta_de_empresa(org_id), _modulo(modulo)
        ia_peticiones_total.labels(empresa=empresa, modulo=mod, resultado="ok" if ok else "error").inc()
        if tokens_in:
            ia_tokens_total.labels(empresa=empresa, modulo=mod, sentido="entrada").inc(float(tokens_in))
        if tokens_out:
            ia_tokens_total.labels(empresa=empresa, modulo=mod, sentido="salida").inc(float(tokens_out))
        if coste_usd:
            ia_coste_usd_total.labels(empresa=empresa, modulo=mod).inc(max(0.0, float(coste_usd)))
    except Exception:
        logger.debug("contar_uso_de_ia: fallo best-effort", exc_info=True)


def contar_presupuesto_de_ia_agotado(org_id) -> None:
    if not _activas():
        return
    try:
        ia_presupuesto_agotado_total.labels(empresa=etiqueta_de_empresa(org_id)).inc()
    except Exception:
        logger.debug("contar_presupuesto_de_ia_agotado: fallo best-effort", exc_info=True)


def anotar_empresa_en_peticion(request, org_id) -> None:
    """Deja en `request.state` la etiqueta de la empresa de la petición.

    La llama la dependencia de autenticación (`app/core/deps.py`), que es donde
    se conoce la empresa. `request.state` vive en el `scope` de la petición, así
    que el middleware de abajo la lee al terminar, aunque la dependencia haya
    corrido en otro hilo.
    """
    if not _activas():
        return
    try:
        request.state.empresa_metricas = etiqueta_de_empresa(org_id)
    except Exception:
        logger.debug("anotar_empresa_en_peticion: fallo best-effort", exc_info=True)


def anotar_codigo_de_error(request, codigo) -> None:
    """El código del catálogo de errores de la respuesta (lo llaman los manejadores)."""
    try:
        if codigo and _CODIGO.match(str(codigo)):
            request.state.codigo_error = str(codigo)
    except Exception:
        logger.debug("anotar_codigo_de_error: fallo best-effort", exc_info=True)


def _estado(codigo_http: int) -> str:
    if codigo_http in (401, 403, 404, 429):
        return str(codigo_http)
    return f"{codigo_http // 100}xx"


_EXCLUIDAS = ("/metrics", "/health", "/ready", "/favicon.ico", "/static", "/api/v1/docs",
              "/api/v1/redoc", "/api/v1/openapi.json", "/assets")


class MetricasPorEmpresaMiddleware:
    """Middleware ASGI: peticiones, latencia y errores por empresa.

    La ruta es la PLANTILLA (`/api/v1/tickets/{ticket_id}`), nunca la URL real:
    una URL con ids sería una serie por recurso. Las peticiones que no casan con
    ninguna ruta van como `sin_plantilla`.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or str(scope.get("path", "")).startswith(_EXCLUIDAS):
            await self.app(scope, receive, send)
            return
        inicio = time.perf_counter()
        estado = {"codigo": 500}

        async def _send(mensaje):
            if mensaje.get("type") == "http.response.start":
                estado["codigo"] = int(mensaje.get("status", 500))
            await send(mensaje)

        try:
            await self.app(scope, receive, _send)
        finally:
            self._registrar(scope, estado["codigo"], time.perf_counter() - inicio)

    @staticmethod
    def _registrar(scope, codigo_http: int, duracion: float) -> None:
        try:
            st = scope.get("state") or {}
            empresa = st.get("empresa_metricas") or SIN_EMPRESA
            http_peticiones_empresa_total.labels(empresa=empresa, estado=_estado(codigo_http)).inc()
            http_duracion_empresa_seconds.labels(empresa=empresa).observe(duracion)
            if codigo_http >= 400:
                ruta = getattr(scope.get("route"), "path", None) or "sin_plantilla"
                codigo = st.get("codigo_error") or {
                    401: "no_autenticado", 403: "prohibido", 404: "no_encontrado",
                    405: "metodo_no_permitido", 422: "validacion", 429: "limite_de_peticiones",
                }.get(codigo_http, "sin_codigo")
                http_errores_total.labels(empresa=empresa, ruta=ruta[:120], estado=str(codigo_http),
                                          codigo=codigo).inc()
        except Exception:
            logger.debug("MetricasPorEmpresaMiddleware: fallo best-effort", exc_info=True)


__all__ = [
    "SIN_EMPRESA", "OTRAS", "etiqueta_de_empresa", "mapa_de_empresas", "invalidar_cache",
    "contar_login", "contar_uso_de_ia", "contar_presupuesto_de_ia_agotado",
    "anotar_empresa_en_peticion", "anotar_codigo_de_error", "MetricasPorEmpresaMiddleware",
]
