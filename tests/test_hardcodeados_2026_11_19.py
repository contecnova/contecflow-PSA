"""Auditoría de hardcodeados (19-11-2026).

- Cada clave de la configuración dinámica tiene etiqueta en es/en/zh
  (`ajuste_clave.<CLAVE>` en frontend/src/i18n/langs/*.mjs).
- Tipos de proyecto, sectores y categorías de gasto son catálogos editables:
  la clave se valida contra el catálogo de la empresa al guardar.
- STT sin idioma fijo; país por defecto como ajuste por empresa.
"""
import re
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.errores import ErrorDeDominio
from app.services.settings_service import RUNTIME_FLAG_GROUPS
from app.services.settings_service import catalogos_de_clave as cat

LANGS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "langs"


def _bloque(lang: str, nombre: str) -> str:
    texto = (LANGS / f"{lang}.mjs").read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(rf"\n  {nombre}: \{{\n(.*?)\n  \}},", texto, re.S)
    assert m, f"{lang}: falta el bloque {nombre}"
    return m.group(1)


@pytest.mark.parametrize("lang", ["es", "en", "zh"])
def test_cada_ajuste_dinamico_tiene_etiqueta_traducida(lang):
    bloque = _bloque(lang, "ajuste_clave")
    definidas = set(re.findall(r"^    ([A-Z0-9_]+):", bloque, re.M))
    claves = {k for v in RUNTIME_FLAG_GROUPS.values() for k, _, _ in v}
    assert sorted(claves - definidas) == []


def test_stt_sin_idioma_fijo_y_pais_configurable():
    assert settings.AZURE_STT_LANGUAGE == "" or "AZURE_STT_LANGUAGE" in __import__("os").environ
    assert settings.GOOGLE_STT_LANGUAGE == "" or "GOOGLE_STT_LANGUAGE" in __import__("os").environ
    claves = {k for v in RUNTIME_FLAG_GROUPS.values() for k, _, _ in v}
    assert "DEFAULT_COUNTRY" in claves
    from app.services.settings_service.por_empresa import COLUMNAS_POR_EMPRESA
    assert COLUMNAS_POR_EMPRESA["country"] == "DEFAULT_COUNTRY"


def test_catalogos_conservan_las_claves_de_los_enums():
    from app.models.clients import ClientIndustry
    from app.models.expenses import ExpenseCategory
    from app.models.project import ProjectType
    assert {v[0] for v in cat.DEFAULT_CLIENT_INDUSTRIES} == {e.value for e in ClientIndustry}
    assert {v[0] for v in cat.DEFAULT_EXPENSE_CATEGORIES} == {e.value for e in ExpenseCategory}
    assert {v[0] for v in cat.CATALOGOS["project_types"][1]} == {e.value for e in ProjectType}


def test_clave_acepta_enum_antiguo_y_texto():
    from app.models.project import ProjectType
    assert cat.clave(ProjectType.rd) == "rd"
    assert cat.clave(" consulting ") == "consulting"
    assert cat.clave("") is None and cat.clave(None) is None


def test_tipo_de_proyecto_propio_se_guarda_y_uno_inexistente_no(db):
    """Un tipo creado por la empresa vale para `projects.project_type`; uno que no existe da 422."""
    from app.models.project import Project
    from app.models.settings import CustomProjectType
    cat.listar(db, "project_types")  # siembra los del sistema
    db.add(CustomProjectType(value="auditoria_iso", label="Auditoría ISO", color="#123456", sort_order=99))
    db.commit()
    ok = Project(code=f"T-{uuid.uuid4().hex[:6]}", name="Tipo propio", project_type="auditoria_iso")
    db.add(ok)
    db.commit()
    assert ok.project_type == "auditoria_iso"
    malo = Project(code=f"T-{uuid.uuid4().hex[:6]}", name="Tipo inventado", project_type="no_existe_xyz")
    db.add(malo)
    with pytest.raises(ErrorDeDominio) as e:
        db.flush()
    assert e.value.status_code == 422
    db.rollback()


def test_enum_antiguo_se_guarda_como_clave(db):
    from app.models.expenses import ExpenseCategory
    assert cat.exigir_clave(db, "expense_categories", ExpenseCategory.travel) == "travel"
    with pytest.raises(ErrorDeDominio):
        cat.exigir_clave(db, "client_industries", "sector_que_no_existe")


# ── Integraciones y respaldos de desarrollo ──────────────────────────────────

def _copia(**cambios):
    from types import SimpleNamespace
    base = {k: getattr(settings, k) for k in type(settings).model_fields}
    base.update(cambios)
    return SimpleNamespace(**base)


def test_en_desarrollo_no_hay_problemas():
    from app.core import comprobacion_de_produccion as cp
    assert cp.problemas(_copia(ENVIRONMENT="development", APP_PUBLIC_URL="http://localhost:3000")) == []


def test_en_produccion_se_rechazan_los_respaldos_de_desarrollo():
    from app.core import comprobacion_de_produccion as cp
    s = _copia(ENVIRONMENT="production", APP_PUBLIC_URL="http://localhost:3000",
               COLLAB_SEARCH_BACKEND="opensearch", OPENSEARCH_URL="http://localhost:9200",
               COLLAB_BUS_BACKEND="redis", REDIS_URL=None, SMTP_FROM="",
               NOTIFICATION_EMAIL_FROM="alerts@contecflow.local", DOCUSIGN_DEMO=True,
               ADOBE_SIGN_CLIENT_ID="x", ADOBE_SIGN_BASE_URL="")
    fallos = " | ".join(cp.problemas(s))
    for trozo in ("APP_PUBLIC_URL", "OPENSEARCH_URL", "REDIS_URL", "Remitente", "DOCUSIGN_DEMO", "ADOBE_SIGN_BASE_URL"):
        assert trozo in fallos
    with pytest.raises(RuntimeError):
        cp.exigir(s)


def test_produccion_bien_configurada_arranca():
    from app.core import comprobacion_de_produccion as cp
    s = _copia(ENVIRONMENT="production", APP_PUBLIC_URL="", COLLAB_SEARCH_BACKEND="auto",
               COLLAB_BUS_BACKEND="memory", SMTP_FROM="avisos@empresa.es", DOCUSIGN_DEMO=None,
               ADOBE_SIGN_CLIENT_ID="", VAPID_PRIVATE_KEY=None)
    assert cp.problemas(s) == []


def test_docusign_no_es_demo_por_defecto_en_produccion():
    from app.core import comprobacion_de_produccion as cp
    assert cp.docusign_es_demo(None, _copia(ENVIRONMENT="production", DOCUSIGN_DEMO=None)) is False
    assert cp.docusign_es_demo(None, _copia(ENVIRONMENT="development", DOCUSIGN_DEMO=None)) is True
    assert cp.docusign_es_demo("true", _copia(ENVIRONMENT="production", DOCUSIGN_DEMO=None)) is True
    assert cp.docusign_es_demo(None, _copia(ENVIRONMENT="staging", DOCUSIGN_DEMO=True)) is True


def test_github_y_gitlab_con_base_propia():
    from app.core import comprobacion_de_produccion as cp
    assert cp.github_api_base({"api_base": "https://ghe.empresa.es/api/v3/"}) == "https://ghe.empresa.es/api/v3"
    assert cp.github_api_base(None) == settings.GITHUB_API_BASE.rstrip("/")
    assert cp.gitlab_base({"base_url": "https://git.empresa.es"}) == "https://git.empresa.es"
    from app.services.collaboration._integrations import PROVIDERS
    assert PROVIDERS["gitlab"].auth_url.startswith(settings.GITLAB_BASE_URL.rstrip("/"))
    assert PROVIDERS["github"].token_url.startswith(settings.GITHUB_WEB_BASE.rstrip("/"))


def test_url_publica_cae_a_frontend_url():
    from app.core import comprobacion_de_produccion as cp
    assert cp.url_publica_de_la_app(_copia(APP_PUBLIC_URL="", FRONTEND_URL="https://app.empresa.es/")) == "https://app.empresa.es"


def test_modelos_retirados_salen_del_catalogo_json():
    from app.services.ai_provider_service.catalogo import _DEPRECATED_MODELS, _MODELOS
    assert "_retirados" in _MODELOS
    assert "gemini-1.5-pro" in _DEPRECATED_MODELS["gemini"]


def test_sin_max_tokens_literales_en_las_llamadas_de_ia():
    import ast
    raiz = Path(__file__).resolve().parents[1] / "app"
    malos = []
    for p in raiz.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.keyword) and n.arg == "max_tokens" and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, int):
                malos.append(f"{p.relative_to(raiz)}:{n.value.lineno}")
    assert malos == []
