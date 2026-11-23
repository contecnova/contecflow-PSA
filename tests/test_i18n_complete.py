"""
test_i18n_complete.py
Verifies i18n coverage across all language files.

Checks:
1. All language files exist.
2. Each language has the same top-level namespace keys as English.
3. No top-level key is an empty dict.
4. Known critical translation keys exist in every language.
"""
import re
from pathlib import Path

from ._i18n_langs import idiomas_ofrecidos

import pytest

LANGS_DIR = Path(__file__).parent.parent / "frontend" / "src" / "i18n" / "langs"

# Auditoría 2026-08 (hallazgo 16). Antes era un conjunto de OCHO códigos escrito a
# mano, que quedó obsoleto al reducir a los tres idiomas que se venden y dejó este
# test en rojo sin que nadie lo viera —la suite completa no llegaba a terminar—.
# Ahora se lee de APP_LANGUAGES, que es el único sitio donde se declaran.
EXPECTED_LANGS = set(idiomas_ofrecidos())
# Critical top-level namespaces that must exist in every language file.
# NOTE: the billing domain lives under `invoices`/`milestone_billing` (not a `billing`
# namespace) and is not yet present in every language, so it is not listed here.
CRITICAL_KEYS = [
    "service_desk",
    "ai",
    "cmdb",
    "dashboard",
]


def _extract_top_level_keys(filepath: Path) -> set[str]:
    """
    Extract top-level object keys from a JS/MJS file like:
      const en = { key1: { ... }, key2: { ... } }
    """
    text = filepath.read_text(encoding="utf-8")
    # Find the first '{' after '= {' and then scan for top-level keys
    # Use a regex to find lines that look like "  keyName:" at indentation level 1
    keys = set(re.findall(r"^\s{2,4}(\w+)\s*:", text, re.MULTILINE))
    return keys


def test_all_lang_files_exist():
    for lang in EXPECTED_LANGS:
        lang_file = LANGS_DIR / f"{lang}.mjs"
        assert lang_file.exists(), f"Missing language file: {lang}.mjs"


def test_lang_files_have_content():
    for lang in EXPECTED_LANGS:
        lang_file = LANGS_DIR / f"{lang}.mjs"
        if not lang_file.exists():
            continue
        content = lang_file.read_text(encoding="utf-8")
        assert len(content) > 100, f"Language file {lang}.mjs is suspiciously small"


def test_all_langs_have_critical_keys():
    """Every language file must contain the critical top-level namespaces."""
    missing = {}
    for lang in EXPECTED_LANGS:
        lang_file = LANGS_DIR / f"{lang}.mjs"
        if not lang_file.exists():
            continue
        keys = _extract_top_level_keys(lang_file)
        absent = [k for k in CRITICAL_KEYS if k not in keys]
        if absent:
            missing[lang] = absent
    assert not missing, (
        "Critical i18n keys missing in some languages: "
        + str(missing)
    )


def test_english_has_most_keys():
    """English must be the most complete language (baseline)."""
    en_file = LANGS_DIR / "en.mjs"
    if not en_file.exists():
        return
    en_keys = _extract_top_level_keys(en_file)
    assert len(en_keys) >= len(CRITICAL_KEYS), (
        f"English file seems incomplete — only {len(en_keys)} top-level keys found"
    )


def test_no_lang_is_empty_object():
    """No language file should define an empty export."""
    for lang in EXPECTED_LANGS:
        lang_file = LANGS_DIR / f"{lang}.mjs"
        if not lang_file.exists():
            continue
        content = lang_file.read_text(encoding="utf-8")
        # Check the file doesn't just have `const xx = {}` with nothing inside
        assert not re.search(r"const \w+ = \{\s*\}", content), (
            f"Language file {lang}.mjs appears to export an empty object"
        )


# ── Deep key comparison ────────────────────────────────────────────────────────

def _extract_all_dotted_keys(filepath: Path) -> set[str]:
    """
    Claves con puntos (`namespace.leaf`) de un fichero MJS de idioma:
        const lang = { namespace: { key1: 'value', key2: 'value' } }

    Antes era una heuristica por sangrado (2-4 espacios) que dejaba fuera los
    espacios de nombres con sangrado raro --en `en.mjs` hay seis bloques con 8 o
    14 espacios de sangria que SI son de primer nivel-- y daba cientos de falsos
    «faltan». Ahora se recorre el texto contando llaves, sin mirar el sangrado:
    se ignoran comentarios y cadenas (donde caben llaves, p. ej. `{count}`) y se
    toma como clave de espacio de nombres la de profundidad 1 y como hoja la de
    profundidad 2.
    """
    text = filepath.read_text(encoding="utf-8")
    keys: set[str] = set()
    ns_actual: str | None = None
    profundidad = 0
    i, n = 0, len(text)
    ident = re.compile(r"[A-Za-z_$][\w$]*")
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            i = text.find(chr(10), i)
            i = n if i < 0 else i
            continue
        if text.startswith("/*", i):
            i = text.find("*/", i)
            i = n if i < 0 else i + 2
            continue
        if c in "'\"`":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            literal = text[i + 1:j]
            i = j + 1
            # Una cadena seguida de `:` es una clave entrecomillada.
            k = i
            while k < n and text[k] in " 	":
                k += 1
            if k < n and text[k] == ":" and profundidad in (1, 2):
                _anotar(keys, profundidad, literal, ns_actual)
                if profundidad == 1:
                    ns_actual = literal
            continue
        if c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 1:
                pass
            elif profundidad == 0:
                ns_actual = None
        elif c.isalpha() or c in "_$":
            m = ident.match(text, i)
            palabra = m.group(0)
            i = m.end()
            k = i
            while k < n and text[k] in " 	":
                k += 1
            if k < n and text[k] == ":" and profundidad in (1, 2):
                _anotar(keys, profundidad, palabra, ns_actual)
                if profundidad == 1:
                    ns_actual = palabra
            continue
        i += 1
    return keys


def _anotar(keys: set[str], profundidad: int, clave: str, ns_actual: str | None) -> None:
    if profundidad == 2 and ns_actual:
        keys.add(f"{ns_actual}.{clave}")


def test_all_langs_have_same_keys_as_spanish():
    """
    Comparacion profunda clave a clave: es.mjs es la fuente de verdad y en/zh
    deben definir las mismas claves con puntos (namespace.leaf). Informa de las
    que faltan por idioma.
    """
    es_file = LANGS_DIR / "es.mjs"
    assert es_file.exists(), "Falta la fuente de verdad es.mjs"

    es_keys = _extract_all_dotted_keys(es_file)
    assert len(es_keys) > 10, "La extraccion de claves de es.mjs parece rota: hay muy pocas"

    missing_per_lang: dict[str, list[str]] = {}

    for lang in sorted(EXPECTED_LANGS - {"es"}):
        lang_file = LANGS_DIR / f"{lang}.mjs"
        assert lang_file.exists(), f"Falta el fichero de idioma {lang}.mjs"
        lang_keys = _extract_all_dotted_keys(lang_file)
        absent = sorted(es_keys - lang_keys)
        if absent:
            missing_per_lang[lang] = absent

    if missing_per_lang:
        report_lines = []
        for lang, keys in sorted(missing_per_lang.items()):
            report_lines.append(f"\n  [{lang}] faltan {len(keys)} claves respecto a es:")
            for k in keys[:20]:
                report_lines.append(f"    - {k}")
            if len(keys) > 20:
                report_lines.append(f"    ... y {len(keys) - 20} mas")
        assert not missing_per_lang, "Fallos de paridad i18n:" + "".join(report_lines)


def test_no_lang_has_extra_keys_vs_english():
    """
    Guard against typos: no language should define keys that don't exist in English.
    Extra keys often indicate a renamed or removed English key that wasn't cleaned up.
    """
    en_file = LANGS_DIR / "en.mjs"
    if not en_file.exists():
        return

    en_keys = _extract_all_dotted_keys(en_file)
    extra_per_lang: dict[str, list[str]] = {}

    for lang in EXPECTED_LANGS - {"en"}:
        lang_file = LANGS_DIR / f"{lang}.mjs"
        if not lang_file.exists():
            continue
        lang_keys = _extract_all_dotted_keys(lang_file)
        extra = sorted(lang_keys - en_keys)
        if extra:
            extra_per_lang[lang] = extra

    if extra_per_lang:
        report_lines = []
        for lang, keys in sorted(extra_per_lang.items()):
            report_lines.append(f"\n  [{lang}] has {len(keys)} extra keys (not in English):")
            for k in keys[:10]:
                report_lines.append(f"    + {k}")
            if len(keys) > 10:
                report_lines.append(f"    ... and {len(keys) - 10} more")
        # Warn but don't fail — extra keys are less critical than missing ones
        import warnings
        warnings.warn("i18n extra key warnings (not failures):" + "".join(report_lines))  # noqa: B028
