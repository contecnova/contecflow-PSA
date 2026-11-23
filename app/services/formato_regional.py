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


#: M15 (auditoría 22-11-2026): separadores (miles, decimales) por idioma (CLDR).
#: Antes todo salía en formato de EE. UU. («1,234.50 €») también en castellano.
_SEPARADORES = {
    "es": (".", ","), "ca": (".", ","), "gl": (".", ","), "eu": (".", ","), "de": (".", ","),
    "it": (".", ","), "pt": (".", ","), "nl": (".", ","), "pl": ("\u00a0", ","), "fr": ("\u202f", ","),
    "en": (",", "."), "zh": (",", "."), "ja": (",", "."),
}


def formatear_importe(valor: Any, simbolo: str, decimales: int = 0, idioma: Optional[str] = None) -> str:
    """`1234.6` → `"1.235 €"` en castellano, `"1,235 €"` en inglés. `None` → `"—"`.

    `idioma` (ISO 639-1); sin él, el de la instalación (`DEFAULT_LANGUAGE`).
    """
    if valor is None or valor == "":
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return f"{valor} {simbolo}"
    miles, coma = _SEPARADORES.get(_corto(idioma) or _corto(settings.DEFAULT_LANGUAGE) or "en", (",", "."))
    texto = f"{numero:,.{decimales}f}".translate(str.maketrans({",": miles, ".": coma}))
    return f"{texto} {simbolo}"


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


# ── Idioma de salida (IA, PDF, correos) ──────────────────────────────────────
#
# 18-11-2026 (auditoria de textos fijos). Los prompts de IA decian «Responde
# siempre en español» y los PDF / correos salian en castellano aunque el
# usuario, la empresa o el cliente tuvieran otro idioma. Un solo sitio para
# decidir en que idioma sale lo que genera el servidor:
#
#   idioma explicito (el del cliente, el del ticket...) → preferencia del
#   usuario → `Organization.locale` → `DEFAULT_LANGUAGE` de la empresa →
#   `settings.DEFAULT_LANGUAGE` → `"es"`.
#
# Los prompts pueden seguir escritos en castellano: lo que cambia es la
# instruccion del idioma de la respuesta (`instruccion_de_idioma`).

def idioma_de_salida(db=None, *, user_id: Optional[str] = None, org_id: Optional[str] = None,
                     preferido: Optional[str] = None) -> str:
    """Codigo del idioma en que sale un texto generado (18-11-2026).

    `preferido` (el idioma del cliente, del ticket, del documento...) gana si
    es un idioma admitido; si no, `idioma(db, user_id, org_id)`. Si se pasa
    `user_id` sin `org_id`, la empresa se toma del usuario.
    """
    from app.services.traduccion.idiomas import normalizar
    if normalizar(preferido):
        return normalizar(preferido)
    if db is not None and user_id and not org_id:
        try:
            from app.models.user import User
            org_id = db.query(User.organization_id).filter(User.id == user_id).scalar()
        except Exception:
            logger.debug("idioma_de_salida: empresa del usuario no legible", exc_info=True)
    return idioma(db, user_id=user_id, org_id=org_id)


def nombre_del_idioma(codigo: Optional[str]) -> str:
    """Nombre (en ingles, lo lee el modelo) del idioma `codigo`: `"zh"` → `"Chinese (Simplified)"`."""
    from app.services.traduccion.idiomas import IDIOMAS, normalizar
    cod = normalizar(codigo) or _corto(codigo) or IDIOMA_DE_RESPALDO
    return IDIOMAS.get(cod, cod)


def instruccion_de_idioma(codigo: Optional[str], *, conversacional: bool = False) -> str:
    """Frase para el prompt de sistema: en que idioma debe responder la IA (18-11-2026).

    `conversacional` (chats): manda el idioma en que escribe el usuario y
    `codigo` queda de respaldo. Si no, la salida va siempre en `codigo`.
    """
    from app.services.traduccion.idiomas import normalizar
    cod = normalizar(codigo) or _corto(codigo) or IDIOMA_DE_RESPALDO
    nombre = nombre_del_idioma(cod)
    if conversacional:
        return (f"Responde en el idioma en que te escriba el usuario; si no se puede saber, "
                f"en {nombre} (idioma «{cod}»).")
    return (f"Responde siempre en {nombre} (idioma «{cod}»), "
            f"aunque estas instrucciones esten en castellano.")


def instruccion_de_idioma_para(db=None, *, user_id: Optional[str] = None, org_id: Optional[str] = None,
                               preferido: Optional[str] = None, conversacional: bool = False) -> str:
    """`instruccion_de_idioma(idioma_de_salida(...))` en una llamada."""
    return instruccion_de_idioma(idioma_de_salida(db, user_id=user_id, org_id=org_id, preferido=preferido),
                                 conversacional=conversacional)


# ── Fechas y zona horaria ────────────────────────────────────────────────────
#
# 18-11-2026 (auditoria de textos fijos). 17 sitios escribian `%d/%m/%Y` fijo
# y varios ponian «UTC» al lado de `datetime.now()` (hora local del servidor,
# no UTC). Ahora la fecha va con el formato del idioma y la hora en la zona de
# la empresa (`DEFAULT_TIMEZONE`) con su etiqueta real (CET, CEST, EST...).

#: Formato de fecha por idioma (sin caracteres no ASCII: `strftime` en Windows
#: falla con ellos). Lo que no esta aqui usa el de `IDIOMA_DE_RESPALDO`.
_FORMATO_DE_FECHA = {
    "es": "%d/%m/%Y", "ca": "%d/%m/%Y", "gl": "%d/%m/%Y", "eu": "%Y/%m/%d", "fr": "%d/%m/%Y",
    "it": "%d/%m/%Y", "pt": "%d/%m/%Y", "de": "%d.%m.%Y", "pl": "%d.%m.%Y", "nl": "%d-%m-%Y",
    "en": "%Y-%m-%d", "zh": "%Y-%m-%d", "zh-hant": "%Y-%m-%d", "ja": "%Y/%m/%d", "ko": "%Y.%m.%d",
}


def formato_de_fecha(codigo_idioma: Optional[str], *, con_hora: bool = False) -> str:
    """Patron `strftime` de la fecha (y hora, 24 h) para un idioma."""
    from app.services.traduccion.idiomas import normalizar
    cod = normalizar(codigo_idioma) or _corto(codigo_idioma) or IDIOMA_DE_RESPALDO
    fmt = _FORMATO_DE_FECHA.get(cod) or _FORMATO_DE_FECHA[IDIOMA_DE_RESPALDO]
    return f"{fmt} %H:%M" if con_hora else fmt


def zona_horaria(db=None, org_id: Optional[str] = None):
    """`ZoneInfo` de la empresa (`DEFAULT_TIMEZONE`); UTC si no se puede leer."""
    from zoneinfo import ZoneInfo
    nombre = None
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_str
            nombre = get_runtime_str(db, "DEFAULT_TIMEZONE", org_id)
        except Exception:
            logger.debug("zona_horaria: ajuste no legible", exc_info=True)
    for candidato in (nombre, settings.DEFAULT_TIMEZONE, "UTC"):
        if not candidato:
            continue
        try:
            return ZoneInfo(str(candidato))
        except Exception:
            logger.debug("zona_horaria: zona %r no valida", candidato)
    from datetime import timezone as _tz
    return _tz.utc


def ahora_local(db=None, org_id: Optional[str] = None, zona=None):
    """La hora actual en la zona de la empresa (con `tzinfo`)."""
    from datetime import datetime, timezone as _tz
    return datetime.now(_tz.utc).astimezone(zona or zona_horaria(db, org_id))


def formatear_fecha(valor: Any, codigo_idioma: Optional[str] = None, *, con_hora: bool = False,
                    con_zona: bool = False, zona=None) -> str:
    """Fecha (o fecha y hora) en el formato del idioma. `None` → `"—"`.

    Un `datetime` con zona se pasa a `zona` (si se da); uno sin zona se toma
    como UTC si se pide `zona`. `con_zona` añade la etiqueta de la zona
    (`CET`, `EST`...) detras de la hora.
    """
    from datetime import date, datetime, timezone as _tz
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return valor
    if isinstance(valor, datetime) and zona is not None:
        valor = (valor if valor.tzinfo else valor.replace(tzinfo=_tz.utc)).astimezone(zona)
    if not isinstance(valor, (date, datetime)):
        return str(valor)
    hora = con_hora and isinstance(valor, datetime)
    texto = valor.strftime(formato_de_fecha(codigo_idioma, con_hora=hora))
    if hora and con_zona and isinstance(valor, datetime) and valor.tzinfo is not None:
        texto += f" {valor.tzname() or valor.tzinfo}"
    return texto


def sello_de_hora(db=None, org_id: Optional[str] = None, codigo_idioma: Optional[str] = None) -> str:
    """«Ahora» en la zona de la empresa, con hora y etiqueta de zona: `18/11/2026 15:30 CET`."""
    zona = zona_horaria(db, org_id)
    return formatear_fecha(ahora_local(zona=zona), codigo_idioma, con_hora=True, con_zona=True, zona=zona)
