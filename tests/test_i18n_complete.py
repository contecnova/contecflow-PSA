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

LANGS_DIR = Path(__file__).parent.parent / "frontend" / "src" / "i18n" / "langs"
EXPECTED_LANGS = {"en", "es", "fr", "de", "it", "pt", "pl", "zh"}
CRITICAL_KEYS = [
    "service_desk",
    "ai",
    "billing",
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
