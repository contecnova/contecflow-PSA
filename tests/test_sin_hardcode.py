"""Guarda: nada en duro que deba ser configuracion o constante (barrido 2026-11).

Solo cubre las categorias que se detectan sin falsos positivos. Cada excepcion va
en una lista explicita con su motivo; anadir una entrada exige justificarla.

Fuera de alcance a proposito: tests, migraciones de Alembic (historicas por
naturaleza) y datos de demostracion (`app/db/seed*`).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app"


def _ficheros():
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(RAIZ).as_posix()
        if rel.startswith("app/db/seed"):
            continue
        yield rel, p.read_text(encoding="utf-8")


def _cadenas(src: str):
    """(linea, valor) de cada literal de texto que no es un docstring."""
    arbol = ast.parse(src)
    docs = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            primero = n.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                docs.add(id(primero.value))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            yield n.lineno, n.value


# ── 1. Zonas horarias IANA ────────────────────────────────────────────────────
# La zona por defecto es `settings.DEFAULT_TIMEZONE` (y el ajuste por empresa).
_ZONA = re.compile(r"^(Europe|America|Asia|Africa|Australia|Atlantic|Pacific|Indian)/[A-Za-z_]+$")
_ZONA_PERMITIDA = {
    "app/core/config.py": "es la definicion de DEFAULT_TIMEZONE",
}


def test_sin_zona_horaria_literal():
    malos = [f"{rel}:{ln} {v!r}" for rel, src in _ficheros() if rel not in _ZONA_PERMITIDA
             for ln, v in _cadenas(src) if _ZONA.match(v)]
    assert not malos, "Zona horaria en duro; usa settings.DEFAULT_TIMEZONE:\n" + "\n".join(malos)


# ── 2. Locales BCP-47 ('es-ES') ───────────────────────────────────────────────
_LOCALE = re.compile(r"^[a-z]{2}[-_][A-Z]{2}$")
_LOCALE_PERMITIDO = {
    "app/core/config.py": "defaults de AZURE_STT_LANGUAGE / GOOGLE_STT_LANGUAGE",
    "app/services/formato_regional.py": "tabla idioma -> region por defecto (_REGION_POR_DEFECTO)",
}


def test_sin_locale_literal():
    malos = [f"{rel}:{ln} {v!r}" for rel, src in _ficheros() if rel not in _LOCALE_PERMITIDO
             for ln, v in _cadenas(src) if _LOCALE.match(v)]
    assert not malos, "Locale en duro; usa formato_regional.a_bcp47 / los ajustes:\n" + "\n".join(malos)


# ── 3. Idioma de respaldo ─────────────────────────────────────────────────────
# `or "es"` / `TEXTOS["es"]` como respaldo: va formato_regional.IDIOMA_DE_RESPALDO
# o settings.DEFAULT_LANGUAGE. Las CLAVES "es" de los catalogos de textos son datos.
_RESPALDO = re.compile(r"""\bor\s+["']es["']|\[\s*["']es["']\s*\]|else\s+["']es["']""")


def test_sin_idioma_de_respaldo_literal():
    malos = [f"{rel}:{i}" for rel, src in _ficheros()
             for i, linea in enumerate(src.splitlines(), 1) if _RESPALDO.search(linea)]
    assert not malos, "Idioma de respaldo en duro; usa IDIOMA_DE_RESPALDO:\n" + "\n".join(malos)


# ── 4. Correos electronicos ───────────────────────────────────────────────────
_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}")
_CORREO_PERMITIDO = {
    "app/core/config.py": "default de NOTIFICATION_EMAIL_FROM",
    "app/core/config_groups/proceso_config.py": "default del sujeto VAPID (mailto:) en la configuracion",
    "app/services/billing_reports_service/importacion.py": "filas de ejemplo de la plantilla de importacion (dominio ficticio)",
    "app/services/service_desk/workflow_designer_service.py": "plantilla de ejemplo con example.com (RFC 2606)",
}
_NO_ES_CORREO = {"teamsApp@odata.bind"}  # anotacion OData de Microsoft Graph


def test_sin_correo_literal():
    malos = [f"{rel}:{ln} {v!r}" for rel, src in _ficheros() if rel not in _CORREO_PERMITIDO
             for ln, v in _cadenas(src) if _CORREO.search(v) and v not in _NO_ES_CORREO]
    assert not malos, "Correo en duro; va a Settings o a un ajuste:\n" + "\n".join(malos)


# ── 5. Tope de pagina ─────────────────────────────────────────────────────────
_TOPE = re.compile(r"(Query|Field)\([^)]*\ble=200\b")
_TOPE_PERMITIDO = {
    "app/api/v1/endpoints/jira.py": "pendiente: fichero de otro frente (jira*) — usar MAX_TAMANO_DE_PAGINA",
    "app/api/v1/endpoints/jira_integration.py": "pendiente: fichero de otro frente (jira*) — usar MAX_TAMANO_DE_PAGINA",
}


def test_tope_de_pagina_centralizado():
    malos = [f"{rel}:{i}" for rel, src in _ficheros() if rel not in _TOPE_PERMITIDO
             for i, linea in enumerate(src.splitlines(), 1) if _TOPE.search(linea)]
    assert not malos, "Tope de pagina en duro; usa app.core.constantes.MAX_TAMANO_DE_PAGINA:\n" + "\n".join(malos)


# ── 6. Roles comparados como texto ────────────────────────────────────────────
from app.models.user import UserRole  # noqa: E402

_ROLES = "|".join(r.value for r in UserRole)
# `for role in [...]` es iterar, no comparar: queda fuera (lookbehind de `for `).
_ROL = re.compile(rf"""(?<!for )\b(?:role|user_role)\s*(?:==|!=|not\s+in|in)\s*[\(\[{{]?[^\n]*?["']({_ROLES})["']""")


def test_roles_por_enum():
    malos = [f"{rel}:{i}" for rel, src in _ficheros()
             for i, linea in enumerate(src.splitlines(), 1) if _ROL.search(linea)]
    assert not malos, "Rol comparado como texto; usa UserRole.<rol>:\n" + "\n".join(malos)


# ── 7. Marca en la salida que ve una persona ──────────────────────────────────
# En estos generadores (PDF, correo, SMS, emisor TOTP...) el nombre del producto
# sale de app.core.constantes. Identificadores tecnicos aparte.
_SALIDA = [
    "app/services/invoice_pdf.py", "app/services/report_pdf.py", "app/services/report_pdf_service.py",
    "app/services/signature_pdf.py", "app/api/v1/routers/auth_mfa.py", "app/services/bi_export_service.py",
    "app/api/v1/endpoints/bi_export.py", "app/services/auth_service/tokens_y_cookies.py",
    "app/services/collaboration/_email_digest.py", "app/services/cab_service/correo.py",
    "app/services/service_desk/sms_service.py", "app/services/service_desk/multichannel_service.py",
    "app/services/service_desk/change_management_service.py", "app/services/m365_bi_embed_service.py",
    "app/services/settings_service/generales.py", "app/models/white_label.py",
]
_MARCA_TECNICA = re.compile(r"^(contecflow[.:_/-]|X-Contecflow-|Contecflow-Test/)", re.I)


@pytest.mark.parametrize("rel", _SALIDA)
def test_marca_desde_constante(rel):
    src = (RAIZ / rel).read_text(encoding="utf-8")
    malos = [f"{rel}:{ln} {v[:60]!r}" for ln, v in _cadenas(src)
             if re.search("contecflow", v, re.I) and not _MARCA_TECNICA.match(v)
             and not v.lstrip().startswith("#!/")]
    assert not malos, "Nombre del producto en duro; usa NOMBRE_DEL_PRODUCTO:\n" + "\n".join(malos)


def test_las_excepciones_siguen_existiendo():
    """Una excepcion cuyo fichero ya no existe sobra: se quita de la lista."""
    for tabla in (_ZONA_PERMITIDA, _LOCALE_PERMITIDO, _CORREO_PERMITIDO, _TOPE_PERMITIDO):
        for rel in tabla:
            assert (RAIZ / rel).exists(), f"excepcion obsoleta: {rel}"
