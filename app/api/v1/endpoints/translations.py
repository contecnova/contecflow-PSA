import logging
from fastapi import APIRouter, Depends, Query
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
import json
from pathlib import Path

router = APIRouter()

TRANSLATIONS_PATH = Path(__file__).resolve().parent / '../../../frontend/src/i18n/langs'
TRANSLATIONS_PATH = TRANSLATIONS_PATH.resolve()

SUPPORTED_LANGS = {"es", "en", "fr", "de", "it", "pt", "pl", "zh"}

@router.get("", summary="Traducciones de la UI")
def get_translations(
    lang: str = Query(settings.DEFAULT_LANGUAGE, description="Código de idioma: es, en, fr, ..."),
    current_user: User = Depends(get_current_user)
):
    """
    Devuelve el diccionario de traducciones de la UI para el idioma solicitado.
    """
    if lang not in SUPPORTED_LANGS:
        return APIResponse.ok(data={"translations": {}, "error": f"Idioma '{lang}' no soportado"})
    lang_file = (TRANSLATIONS_PATH / f"{lang}.mjs").resolve()
    if TRANSLATIONS_PATH not in lang_file.parents or not lang_file.is_file():
        return APIResponse.ok(data={"translations": {}, "error": f"Idioma '{lang}' no soportado"})
    # Leer el archivo y extraer el objeto JS
    with open(lang_file, encoding="utf-8") as f:
        content = f.read()
    # Extraer el objeto JS entre { ... }
    start = content.find('{')
    end = content.rfind('}')
    if start == -1 or end == -1:
        return APIResponse.ok(data={"translations": {}, "error": "Formato de archivo inválido"})
    js_obj = content[start:end+1]
    # Reemplazar comillas simples por dobles y quitar comentarios JS
    import re
    js_obj = re.sub(r"//.*", "", js_obj)
    js_obj = js_obj.replace("'", '"')
    try:
        translations = json.loads(js_obj)
    except Exception as e:
        logging.getLogger(__name__).debug("get_translations: excepcion ignorada", exc_info=True)
        return APIResponse.ok(data={"translations": {}, "error": f"Error al parsear: {str(e)}"})
    return APIResponse.ok(data={"translations": translations})
