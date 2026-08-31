"""Los idiomas que la aplicación ofrece, leídos del registro y no a mano.

Auditoría 2026-08 (hallazgo 16). Al reducir de siete idiomas a los tres que se
venden —castellano, inglés y chino— quedaron **dos tests con la lista de ocho
escrita a mano**:

  · `tests/test_i18n_complete.py`      → `EXPECTED_LANGS = {…8 códigos…}`
  · `tests/test_business_logic_v239.py` → `_LANGS = [ …8 códigos… ]`

Eran una tercera y cuarta fuente de verdad para la misma lista, exactamente el
mismo problema que el selector de `UserProfilePanel`, que también la llevaba a
mano y por eso podía discrepar del catálogo.

Y hubo una consecuencia peor: esos dos tests llevaban **rotos desde el commit de
la reducción**, y no se detectó porque la suite completa no llegaba a terminar
(en serie tarda más de 90 minutos; con `-n auto`, 13). Un test que nadie termina
de ejecutar no es una red.

Este módulo lee los códigos de `APP_LANGUAGES`, que es el único sitio donde se
declaran. Añadir o quitar un idioma allí actualiza los tests solo.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
I18N = RAIZ / "frontend" / "src" / "i18n"
REGISTRO = I18N / "appTranslations.mjs"
LANGS_DIR = I18N / "langs"

# `{ code: 'es', label: …` — se extrae el código de cada entrada del registro.
_CODIGO = re.compile(r"\{\s*code:\s*'([a-z]{2}(?:-[A-Za-z]{2})?)'")


def idiomas_ofrecidos() -> list[str]:
    """Códigos de `APP_LANGUAGES`, en el orden en que están declarados.

    Se parsea el fichero en lugar de importarlo porque es un módulo de
    JavaScript: no hay forma de importarlo desde Python, y ejecutar Node en cada
    test sería un coste desproporcionado para leer tres cadenas.
    """
    texto = REGISTRO.read_text(encoding="utf-8")
    inicio = texto.index("export const APP_LANGUAGES")
    fin = texto.index("]", inicio)
    codigos = _CODIGO.findall(texto[inicio:fin])
    assert codigos, (
        f"no se pudo leer ningún código de APP_LANGUAGES en {REGISTRO}. "
        "Si ha cambiado su formato, actualizar este ayudante."
    )
    return codigos


def fichero_de(lang: str) -> Path:
    return LANGS_DIR / f"{lang}.mjs"
