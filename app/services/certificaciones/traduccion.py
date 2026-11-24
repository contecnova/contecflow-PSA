"""Certificaciones en el idioma de quien mira (24-11-2026, barrido de traducciones).

El contenido de `app/data/certificaciones/` (marcos, controles, plantillas y
esqueletos de documentos) está redactado en castellano y se siembra por empresa
en castellano. Antes la Biblioteca salía en castellano aunque el usuario tuviera
la interfaz en inglés o chino. Ahora:

* Textos cortos (YAML): catálogo por texto de origen, como gettext, en
  `app/data/certificaciones/i18n/<idioma>.yaml` (`«texto es»: «traducción»`).
  Elegido frente a campos `*_i18n` dentro de cada YAML porque (1) traduce lo ya
  sembrado en la base de datos sin migrar nada: lo que sigue igual que la semilla
  se traduce y lo que la empresa editó (texto propio) se muestra tal cual; (2) no
  ensucia los YAML de origen; (3) se comprueba entero con un test
  (`tests/test_certificaciones_traduccion_2026_11.py`): ningún texto sin traducir.
* Esqueletos de documentos: `documentos/<idioma>/<clave>.md` (misma estructura y
  mismos marcadores `{{...}}` que el original).
* Respaldo: lo que falte sale en castellano.

`traducir(obj, idioma)` recorre la respuesta (dict/list) y sustituye las cadenas
que están en el catálogo, salvo las de campos que son claves (`clave`, `marco`,
`nivel`, `id_control`...). Lo aplica la ruta (`RutaTraducida`) a todas las
respuestas JSON del router de Certificaciones según la cabecera `X-Idioma` (que
manda el cliente con el idioma de la interfaz) o `Accept-Language`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from fastapi import Request, Response
from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2] / "data" / "certificaciones"
IDIOMAS = ("en", "zh")

# Campos cuyo valor es un identificador (nunca se traduce aunque coincida con un texto).
_CAMPOS_CLAVE = frozenset({
    "id", "clave", "clave_comun", "marco", "marcos", "nivel", "niveles", "id_control", "id_semilla", "dominio",
    "estado", "tipo", "codigo", "plantilla_clave", "origen", "resultado", "sede", "organization_id",
})

_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def normalizar(idioma: Optional[str]) -> str:
    cod = (idioma or "").strip().replace("_", "-").split(",")[0].split("-")[0].lower()
    return cod or "es"


def catalogo_de(idioma: str) -> dict[str, str]:
    """`{texto es: traducción}` del idioma (vacío para `es` o si no hay fichero). Se cachea por fecha."""
    idioma = normalizar(idioma)
    if idioma not in IDIOMAS:
        return {}
    ruta = RAIZ / "i18n" / f"{idioma}.yaml"
    try:
        fecha = ruta.stat().st_mtime
    except OSError:
        return {}
    guardado = _CACHE.get(idioma)
    if guardado and guardado[0] == fecha:
        return guardado[1]
    try:
        with ruta.open(encoding="utf8") as f:
            datos = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("Certificaciones: no se pudo leer %s", ruta, exc_info=True)
        datos = {}
    datos = {str(k): str(v) for k, v in datos.items() if v}
    _CACHE[idioma] = (fecha, datos)
    return datos


def texto(valor: Optional[str], idioma: Optional[str]) -> Optional[str]:
    if not valor:
        return valor
    return catalogo_de(idioma or "es").get(valor, valor)


def traducir(obj: Any, idioma: Optional[str], *, campo: Optional[str] = None) -> Any:
    """Copia de `obj` con los textos del catálogo en `idioma` (los identificadores no se tocan)."""
    cat = catalogo_de(idioma or "es")
    if not cat:
        return obj
    return _recorrer(obj, cat, campo)


def _recorrer(obj: Any, cat: dict[str, str], campo: Optional[str]) -> Any:
    if isinstance(obj, str):
        return obj if campo in _CAMPOS_CLAVE else cat.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _recorrer(v, cat, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recorrer(v, cat, campo) for v in obj]
    return obj


def documento(clave: str, idioma: Optional[str], original: str = "") -> str:
    """Esqueleto `documentos/<idioma>/<clave>.md`; si no hay, el original en castellano."""
    idioma = normalizar(idioma)
    if idioma in IDIOMAS:
        ruta = RAIZ / "documentos" / idioma / f"{clave}.md"
        if ruta.is_file():
            try:
                return ruta.read_text(encoding="utf8")
            except OSError:
                logger.warning("Certificaciones: no se pudo leer %s", ruta, exc_info=True)
    return original


def idioma_de_peticion(request: Request) -> str:
    """`X-Idioma` (idioma de la interfaz, lo manda el cliente) → `Accept-Language` → `es`."""
    return normalizar(request.headers.get("x-idioma") or request.headers.get("accept-language"))


class RutaTraducida(APIRoute):
    """Ruta que traduce el contenido de la biblioteca en las respuestas JSON (ver módulo)."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def manejador(request: Request) -> Response:
            respuesta = await original(request)
            idioma = idioma_de_peticion(request)
            if idioma not in IDIOMAS or not catalogo_de(idioma):
                return respuesta
            if "application/json" not in (respuesta.headers.get("content-type") or ""):
                return respuesta
            try:
                datos = json.loads(respuesta.body)
            except (AttributeError, ValueError):
                return respuesta
            cuerpo = json.dumps(traducir(datos, idioma), ensure_ascii=False, separators=(",", ":")).encode("utf8")
            cabeceras = {k: v for k, v in respuesta.headers.items() if k.lower() != "content-length"}
            return Response(content=cuerpo, status_code=respuesta.status_code, headers=cabeceras,
                            media_type="application/json", background=respuesta.background)

        return manejador
