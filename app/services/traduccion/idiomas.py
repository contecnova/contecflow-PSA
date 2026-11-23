"""Idiomas: codigos admitidos, normalizacion y deteccion local.

Sin dependencias de la aplicacion (lo usan los modelos al guardar).

**Codigos.** ISO 639-1 en minusculas (`es`, `en`, `zh`...). `zh` es chino
simplificado; `zh-hant`, tradicional. Lo que llega como `pt-BR`, `EN_us` o
`zh-CN` se normaliza (`normalizar`).

**Deteccion local** (`detectar`): gratis, sin red y determinista. Primero el
sistema de escritura (Han, kana, hangul, cirilico, arabe, hebreo, griego,
tailandes, devanagari) y, en alfabeto latino, palabras funcionales y letras
propias de cada idioma. Devuelve `(idioma, confianza 0-1)`; con poca confianza
(textos cortos, mezclas) quien llama no decide y deja que el proveedor detecte
al traducir (el idioma que devuelve se guarda en el mensaje).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

#: Idiomas a los que se puede traducir y su nombre en ingles (lo lee el modelo
#: de IA; la interfaz pinta el nombre en el idioma de quien mira con
#: `Intl.DisplayNames`, nunca con esta tabla).
IDIOMAS: dict[str, str] = {
    "es": "Spanish", "en": "English", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "pl": "Polish", "zh": "Chinese (Simplified)", "zh-hant": "Chinese (Traditional)",
    "ja": "Japanese", "ko": "Korean", "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic", "he": "Hebrew",
    "nl": "Dutch", "sv": "Swedish", "da": "Danish", "nb": "Norwegian (Bokmal)", "fi": "Finnish",
    "cs": "Czech", "sk": "Slovak", "ro": "Romanian", "hu": "Hungarian", "el": "Greek", "tr": "Turkish",
    "bg": "Bulgarian", "hr": "Croatian", "sl": "Slovenian", "et": "Estonian", "lv": "Latvian",
    "lt": "Lithuanian", "id": "Indonesian", "ms": "Malay", "th": "Thai", "vi": "Vietnamese",
    "hi": "Hindi", "ca": "Catalan", "eu": "Basque", "gl": "Galician",
}

#: Idiomas de la interfaz de los operadores (`frontend/src/i18n/langs`).
IDIOMAS_DE_OPERADOR = ("es", "en", "zh")
#: Idiomas del portal de clientes (`frontend/src/i18n/portal`).
IDIOMAS_DEL_PORTAL = ("es", "en", "fr", "de", "it", "pt", "pl", "zh")

_ALIAS = {
    "zh-cn": "zh", "zh-hans": "zh", "zh-sg": "zh", "zh-tw": "zh-hant", "zh-hk": "zh-hant", "zh-mo": "zh-hant",
    "no": "nb", "nn": "nb", "iw": "he", "in": "id",
}


def normalizar(codigo: Optional[str]) -> Optional[str]:
    """`pt-BR` -> `pt`, `zh_TW` -> `zh-hant`, `EN` -> `en`. None si no es un idioma admitido."""
    if not codigo:
        return None
    c = str(codigo).strip().lower().replace("_", "-")
    if c in _ALIAS:
        return _ALIAS[c]
    if c in IDIOMAS:
        return c
    corto = c.split("-")[0]
    corto = _ALIAS.get(corto, corto)
    return corto if corto in IDIOMAS else None


# ── Deteccion por sistema de escritura ───────────────────────────────────────

_ESCRITURAS = (
    ("hangul", re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏]"), "ko"),
    ("kana", re.compile(r"[぀-ヿ]"), "ja"),
    ("han", re.compile(r"[一-鿿㐀-䶿]"), "zh"),
    ("cirilico", re.compile(r"[Ѐ-ӿ]"), "ru"),
    ("arabe", re.compile(r"[؀-ۿ]"), "ar"),
    ("hebreo", re.compile(r"[֐-׿]"), "he"),
    ("griego", re.compile(r"[Ͱ-Ͽ]"), "el"),
    ("tailandes", re.compile(r"[฀-๿]"), "th"),
    ("devanagari", re.compile(r"[ऀ-ॿ]"), "hi"),
)
_LETRA = re.compile(r"[^\W\d_]", re.UNICODE)
#: Letras del ucraniano que el ruso no tiene.
_UCRANIANO = re.compile(r"[іїєґІЇЄҐ]")
_TRADICIONAL = re.compile(r"[們這個說時來對會為學國後還過見長開關門問題體]")

# ── Alfabeto latino: palabras funcionales y letras propias ───────────────────

_PALABRAS: dict[str, frozenset[str]] = {
    "es": frozenset("el la los las de del que y en un una por con para es no se su al lo como mas pero sus le ya "
                    "o este esta hay muy tengo puede gracias hola favor necesito problema cuando donde desde ayuda".split()),
    "en": frozenset("the of and to in is it you that for on with as are this be at have not or from but my "
                    "can was we your please thanks hello need issue when where would could".split()),
    "fr": frozenset("le la les de des du et en un une est pour que qui dans pas ne sur au avec ce il je vous "
                    "nous mais merci bonjour besoin probleme quand ou sont".split()),
    "de": frozenset("der die das und ist nicht ein eine ich sie es mit den dem zu von auf fur bitte danke "
                    "hallo wir haben kann sind wie wenn aber auch problem".split()),
    "it": frozenset("il lo la gli le di del che e un una per non sono con su come ma ho mi grazie ciao "
                    "buongiorno problema quando dove anche questo questa".split()),
    "pt": frozenset("o a os as de do da que e em um uma para com nao por se mais como mas eu voce obrigado "
                    "ola problema quando onde estou tenho isso ajuda".split()),
    "pl": frozenset("i w nie na sie z jest to do ze co jak ale tak po mam czy dziekuje prosze dzien dobry "
                    "problem kiedy gdzie jestem moze".split()),
    "nl": frozenset("de het een en van is dat niet ik je op te met voor zijn maar wij hebben dank bedankt "
                    "hallo probleem wanneer waar kunt".split()),
    "ca": frozenset("el la els les de del que i en un una per amb es no al com pero gracies hola "
                    "necessito problema quan on aixo ajuda".split()),
}
_LETRAS_PROPIAS: dict[str, re.Pattern] = {
    "es": re.compile(r"[ñ¿¡]"),
    "pt": re.compile(r"[ãõ]"),
    "de": re.compile(r"[ß]"),
    "pl": re.compile(r"[ąęłśźżćń]"),
    "fr": re.compile(r"[œ]"),
    "ca": re.compile(r"l·l"),
}
_PALABRA = re.compile(r"[^\W\d_]+", re.UNICODE)
#: En cuantos idiomas aparece cada palabra funcional (para su peso).
_IDIOMAS_DE_LA_PALABRA: dict[str, int] = {}
for _lista in _PALABRAS.values():
    for _p in _lista:
        _IDIOMAS_DE_LA_PALABRA[_p] = _IDIOMAS_DE_LA_PALABRA.get(_p, 0) + 1


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


#: Cuota minima de letras de un sistema de escritura para darlo por ese idioma.
_CUOTA_MINIMA_DE_ESCRITURA = 0.3
#: Palabras a partir de las cuales la cantidad de texto ya no resta confianza.
_PALABRAS_PARA_CONFIANZA_PLENA = 8
#: Lo que pesa una letra propia de un idioma frente a una palabra funcional.
_PESO_DE_LETRA_PROPIA = 2


def _por_escritura(texto: str) -> Optional[tuple[str, float]]:
    letras = _LETRA.findall(texto)
    if not letras:
        return None
    total = len(letras)
    cuentas = {nombre: len(patron.findall(texto)) for nombre, patron, _ in _ESCRITURAS}
    # El japones mezcla kanji (Han) con kana: con kana, japones.
    if cuentas["kana"]:
        cuentas["kana"] += cuentas["han"]
        cuentas["han"] = 0
    for nombre, _, idioma in _ESCRITURAS:
        n = cuentas[nombre]
        if not n:
            continue
        if nombre == "han" and _TRADICIONAL.search(texto):
            idioma = "zh-hant"
        if nombre == "cirilico" and _UCRANIANO.search(texto):
            idioma = "uk"
        cuota = n / total
        if cuota >= _CUOTA_MINIMA_DE_ESCRITURA:
            return idioma, min(1.0, 0.5 + cuota / 2)
    return None


def detectar(texto: Optional[str]) -> tuple[Optional[str], float]:
    """`(idioma, confianza)` sin red. `(None, 0.0)` si no hay con que decidir."""
    if not texto or not texto.strip():
        return None, 0.0
    escritura = _por_escritura(texto)
    if escritura is not None:
        return escritura
    minus = texto.lower()
    palabras = [_sin_tildes(p) for p in _PALABRA.findall(minus)]
    if not palabras:
        return None, 0.0
    puntos: dict[str, float] = {}
    # Revisión 16-11-2026: cada palabra pesa 1/(idiomas que la tienen). Una palabra
    # comun a varios («la», «no», «hola») apenas distingue; contarla entera dejaba
    # al espanol a la par del catalan (medido: 0,375 de confianza en una frase
    # espanola de 13 palabras), asi que se pagaba al proveedor por detectarla.
    for idioma, funcionales in _PALABRAS.items():
        puntos[idioma] = sum(1.0 / _IDIOMAS_DE_LA_PALABRA[p] for p in palabras if p in funcionales)
    for idioma, patron in _LETRAS_PROPIAS.items():
        puntos[idioma] = puntos.get(idioma, 0.0) + _PESO_DE_LETRA_PROPIA * len(patron.findall(minus))
    orden = sorted(puntos.items(), key=lambda kv: kv[1], reverse=True)
    mejor, segundo = orden[0], orden[1]
    if mejor[1] <= 0:
        return None, 0.0
    # Ventaja sobre el segundo y cuanto texto hay: «ok» no decide nada.
    ventaja = (mejor[1] - segundo[1]) / mejor[1]
    cantidad = min(1.0, len(palabras) / _PALABRAS_PARA_CONFIANZA_PLENA)
    return mejor[0], round(ventaja * cantidad, 3)


def detectar_si_seguro(texto: Optional[str], minima: float) -> Optional[str]:
    """El idioma si la confianza llega a `minima`; si no, None (que detecte el proveedor)."""
    idioma, confianza = detectar(texto)
    return idioma if idioma and confianza >= minima else None
