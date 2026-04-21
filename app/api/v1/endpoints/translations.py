from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user
from app.models.user import User
import json
import os

router = APIRouter()

TRANSLATIONS_PATH = os.path.join(os.path.dirname(__file__), '../../../frontend/src/i18n/langs')

@router.get("", summary="Traducciones de la UI")
def get_translations(
    lang: str = Query('es', description="Código de idioma: es, en, fr, ..."),
    current_user: User = Depends(get_current_user)
):
    """
    Devuelve el diccionario de traducciones de la UI para el idioma solicitado.
    """
    lang_file = os.path.join(TRANSLATIONS_PATH, f"{lang}.mjs")
    if not os.path.isfile(lang_file):
        return {"translations": {}, "error": f"Idioma '{lang}' no soportado"}
    # Leer el archivo y extraer el objeto JS
    with open(lang_file, encoding="utf-8") as f:
        content = f.read()
    # Extraer el objeto JS entre { ... }
    start = content.find('{')
    end = content.rfind('}')
    if start == -1 or end == -1:
        return {"translations": {}, "error": "Formato de archivo inválido"}
    js_obj = content[start:end+1]
    # Reemplazar comillas simples por dobles y quitar comentarios JS
    import re
    js_obj = re.sub(r"//.*", "", js_obj)
    js_obj = js_obj.replace("'", '"')
    try:
        translations = json.loads(js_obj)
    except Exception as e:
        return {"translations": {}, "error": f"Error al parsear: {str(e)}"}
    return {"translations": translations}
