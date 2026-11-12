"""Moneda e idioma de la organizacion (y del usuario): un solo sitio.

Auditoria 2026-11 (hallazgo 30). El backend escribia `€` en duro en etiquetas,
textos y PDF (≈100 apariciones en salida: catalogos de metricas, narrativas,
resumenes de IA, exportaciones) y `"es"` en la transcripcion y en las
narrativas, aunque la moneda y el idioma ya eran configurables por
organizacion. Aqui se resuelven:

* Moneda: `DEFAULT_CURRENCY` de la organizacion (ajuste en tiempo de
  ejecucion, con `settings.DEFAULT_CURRENCY` de respaldo) y su simbolo de
  `CURRENCY_SYMBOLS`; una moneda sin simbolo se muestra con su codigo ISO.
* Idioma: preferencia del usuario → `Organization.locale` → ajuste
  `DEFAULT_LANGUAGE` de la organizacion → `settings.DEFAULT_LANGUAGE` → `"es"`.

Los catalogos estaticos (etiquetas de metricas, columnas de informes) llevan
`MARCADOR_DE_MONEDA` (`¤`, el «signo de moneda generico» de Unicode) en vez del
simbolo, y `con_moneda()` lo sustituye al servirlos.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Lo que llevan las etiquetas estaticas en lugar del simbolo de una moneda concreta.
MARCADOR_DE_MONEDA = "¤"

IDIOMA_DE_RESPALDO = "es"

#: Region por defecto de cada idioma, para los proveedores de voz que piden BCP-47.
_REGION_POR_DEFECTO = {
    "es": "es-ES", "en": "en-US", "ca": "ca-ES", "fr": "fr-FR", "de": "de-DE",
    "it": "it-IT", "pt": "pt-PT", "zh": "zh-CN", "eu": "eu-ES", "gl": "gl-ES",
}


# ── Moneda ───────────────────────────────────────────────────────────────────

def codigo_de_moneda(db=None, org_id: Optional[str] = None) -> str:
    """El codigo ISO 4217 de la organizacion (`DEFAULT_CURRENCY`)."""
    codigo = None
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_str
            codigo = get_runtime_str(db, "DEFAULT_CURRENCY", org_id)
        except Exception:
            logger.debug("codigo_de_moneda: ajuste no legible", exc_info=True)
    return str(codigo or settings.DEFAULT_CURRENCY or "EUR").strip().upper()


def simbolo_de_moneda(db=None, org_id: Optional[str] = None, moneda: Optional[str] = None) -> str:
    """El simbolo de `moneda` (por defecto, la de la organizacion); sin simbolo, el codigo."""
    from app.services.settings_service import simbolos_de_moneda
    codigo = (moneda or codigo_de_moneda(db, org_id)).strip().upper()
    try:
        simbolos = simbolos_de_moneda(db, org_id)
    except Exception:
        logger.debug("simbolo_de_moneda: ajuste no legible", exc_info=True)
        simbolos = simbolos_de_moneda()
    return simbolos.get(codigo, codigo)


def formatear_importe(valor: Any, simbolo: str, decimales: int = 0) -> str:
    """`1234.6` → `"1,235 €"` (o el simbolo que toque). `None` → `"—"`."""
    if valor is None or valor == "":
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return f"{valor} {simbolo}"
    return f"{numero:,.{decimales}f} {simbolo}"


def con_moneda(obj: Any, simbolo: str) -> Any:
    """Copia de `obj` (str/dict/list/tuple anidados) con `¤` sustituido por `simbolo`."""
    if isinstance(obj, str):
        return obj.replace(MARCADOR_DE_MONEDA, simbolo) if MARCADOR_DE_MONEDA in obj else obj
    if isinstance(obj, dict):
        return {k: con_moneda(v, simbolo) for k, v in obj.items()}
    if isinstance(obj, list):
        return [con_moneda(v, simbolo) for v in obj]
    if isinstance(obj, tuple):
        return tuple(con_moneda(v, simbolo) for v in obj)
    return obj


# ── Idioma ───────────────────────────────────────────────────────────────────

def _corto(valor: Optional[str]) -> Optional[str]:
    if not valor:
        return None
    return str(valor).strip().replace("_", "-").split("-")[0].lower() or None


def idioma(db=None, *, user_id: Optional[str] = None, org_id: Optional[str] = None) -> str:
    """Codigo ISO 639-1 del idioma en que hablarle a este usuario / organizacion."""
    if db is not None:
        if user_id:
            try:
                from app.models.user import UserPreference
                pref = db.query(UserPreference.language).filter(UserPreference.user_id == user_id).scalar()
                if _corto(pref):
                    return _corto(pref)
            except Exception:
                logger.debug("idioma: preferencia de usuario no legible", exc_info=True)
        if org_id:
            try:
                from app.models.mfa import Organization
                loc = db.query(Organization.locale).filter(Organization.id == org_id).scalar()
                if _corto(loc):
                    return _corto(loc)
            except Exception:
                logger.debug("idioma: locale de la organizacion no legible", exc_info=True)
            try:
                from app.services.settings_service import get_runtime_str
                ajuste = get_runtime_str(db, "DEFAULT_LANGUAGE", org_id)
                if _corto(ajuste):
                    return _corto(ajuste)
            except Exception:
                logger.debug("idioma: ajuste no legible", exc_info=True)
    return _corto(settings.DEFAULT_LANGUAGE) or IDIOMA_DE_RESPALDO


def a_bcp47(codigo: Optional[str], preferido: Optional[str] = None) -> Optional[str]:
    """`"es"` → `"es-ES"` para los proveedores que exigen region.

    Si `preferido` (lo configurado en el proveedor, p. ej. `es-MX`) es del mismo
    idioma, gana: el administrador eligio la variante.
    """
    if not codigo:
        return preferido
    if "-" in codigo or "_" in codigo:
        return codigo.replace("_", "-")
    if preferido and _corto(preferido) == codigo.lower():
        return preferido
    return _REGION_POR_DEFECTO.get(codigo.lower(), codigo)
