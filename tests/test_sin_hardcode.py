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
    # Prompts de IA y textos de Slack/Teams (barrido 2026-11, cierre)
    "app/api/v1/endpoints/ai_chat.py", "app/api/v1/endpoints/ai_modules.py",
    "app/api/v1/endpoints/ai_providers.py", "app/services/ai_modules/client_portal.py",
    "app/services/ai_modules/voice.py", "app/api/v1/endpoints/integrations_hub.py",
    "app/services/integrations.py",
]
_MARCA_TECNICA = re.compile(r"^(contecflow[.:_/-]|X-Contecflow-|Contecflow-Test/)", re.I)
# `/contecflow` es el nombre del comando de barra de Slack/Teams: un identificador
# que se registra en la app de Slack, no texto de marca.
_COMANDO_DE_BARRA = re.compile(r"/contecflow\b")


@pytest.mark.parametrize("rel", _SALIDA)
def test_marca_desde_constante(rel):
    src = (RAIZ / rel).read_text(encoding="utf-8")
    malos = [f"{rel}:{ln} {v[:60]!r}" for ln, v in _cadenas(src)
             if re.search("contecflow", _COMANDO_DE_BARRA.sub("", v), re.I) and not _MARCA_TECNICA.match(v)
             and not v.lstrip().startswith("#!/")]
    assert not malos, "Nombre del producto en duro; usa NOMBRE_DEL_PRODUCTO:\n" + "\n".join(malos)


def test_nombre_del_producto_sale_de_settings():
    from app.core.config import settings
    from app.core.constantes import NOMBRE_DEL_PRODUCTO
    assert NOMBRE_DEL_PRODUCTO == settings.PROJECT_NAME


# ── 8. Estados de ticket y de tarea ───────────────────────────────────────────
# Grupos de estados: `ESTADOS_DE_TICKET_*` (models/service_desk/_enums.py) y
# `ESTADOS_DE_TAREA_TERMINADOS` (models/task.py).
_ESTADOS_LITERALES = [
    (re.compile(r"""[\[\(\{]\s*["'](resolved|closed|cancelled)["']\s*,\s*["'](resolved|closed|cancelled)["']"""),
     "ESTADOS_DE_TICKET_RESUELTOS/_CERRADOS"),
    (re.compile(r"""["']new["']\s*,\s*["']assigned["']\s*,\s*["']in_progress["']"""), "ESTADOS_DE_TICKET_EN_CURSO/_ABIERTOS"),
    (re.compile(r"""[\[\(\{]\s*["']pending_client["']\s*,\s*["']pending_third["']\s*[\]\)\}]"""), "ESTADOS_DE_TICKET_EN_ESPERA"),
    (re.compile(r"""[\[\(\{]\s*["']done["']\s*,\s*["'](closed\s*["']\s*,\s*["'])?cancelled["']\s*[\]\)\}]"""), "ESTADOS_DE_TAREA_TERMINADOS"),
    (re.compile(r"""\[\s*["']p1_critical["']\s*,\s*["']p2_high["']\s*,\s*["']p3_medium["']\s*,\s*["']p4_low["']\s*\]"""), "PRIORIDADES_DE_TICKET"),
]
_ESTADOS_PERMITIDOS = {
    "app/services/ai_copilot_service.py": "estados de PROYECTO (closed/cancelled/archived), no de ticket",
    "app/models/service_desk/_enums.py": "es la definicion",
    "app/models/task.py": "es la definicion",
}


def test_estados_por_constante():
    malos = [f"{rel}:{i} -> {nombre}" for rel, src in _ficheros()
             if rel.startswith(("app/services/", "app/api/")) and rel not in _ESTADOS_PERMITIDOS
             for i, linea in enumerate(src.splitlines(), 1) if not linea.lstrip().startswith("#")
             for rx, nombre in _ESTADOS_LITERALES if rx.search(linea)]
    assert not malos, "Tupla de estados en duro; usa la constante del enum:\n" + "\n".join(malos)


def test_grupos_de_estados_coherentes_con_los_enums():
    from app.models.service_desk import TicketStatus, TicketPriority
    from app.models.service_desk._enums import (
        ESTADOS_DE_TICKET_ABIERTOS, ESTADOS_DE_TICKET_CERRADOS, ESTADOS_DE_TICKET_EN_CURSO,
        ESTADOS_DE_TICKET_EN_ESPERA, PRIORIDADES_DE_TICKET)
    from app.models.task import ESTADOS_DE_TAREA_TERMINADOS, TaskStatus
    assert set(ESTADOS_DE_TICKET_ABIERTOS) | set(ESTADOS_DE_TICKET_CERRADOS) == {s.value for s in TicketStatus}
    assert not set(ESTADOS_DE_TICKET_ABIERTOS) & set(ESTADOS_DE_TICKET_CERRADOS)
    assert set(ESTADOS_DE_TICKET_EN_CURSO) | set(ESTADOS_DE_TICKET_EN_ESPERA) == set(ESTADOS_DE_TICKET_ABIERTOS)
    assert PRIORIDADES_DE_TICKET == tuple(p.value for p in TicketPriority)
    assert set(ESTADOS_DE_TAREA_TERMINADOS) <= {s.value for s in TaskStatus}


# ── 9. Valores que pasaron a Settings (cierre del barrido 2026-11) ────────────
# (fichero, patron que ya no debe aparecer, ajuste que lo sustituye)
_A_SETTINGS = [
    ("app/services/billing_reports_service/sla.py", r"timedelta\(hours=[24]\)", "SLA_AT_RISK_WINDOW_HOURS"),
    ("app/services/bookings_service/pipeline_e_informes.py", r"timedelta\(hours=2\)", "SLA_AT_RISK_WINDOW_HOURS"),
    ("app/services/service_desk/ai_auto_resolution_service.py",
     r"^(AUTO_CLOSE_HOURS_AFTER_RESOLUTION|VALIDATION_WINDOW_HOURS)\s*=\s*\d", "SD_AUTO_CLOSE_/SD_VALIDATION_WINDOW_HOURS"),
    ("app/services/service_desk/known_error_service.py", r"^KEDB_DEFAULT_REVIEW_DAYS\s*=\s*\d", "KEDB_DEFAULT_REVIEW_DAYS"),
    ("app/api/v1/endpoints/service_desk/problem_management.py", r"_days:\s*int\s*=\s*Field\(\d", "KEDB_DEFAULT_REVIEW_DAYS"),
    ("app/api/v1/endpoints/organizations.py", r"max_(users|projects):\s*int\s*=\s*\d", "ORG_DEFAULT_MAX_USERS/_PROJECTS"),
    ("app/core/constantes.py", r"1700|0\.32|=\s*[\"']Contecflow", "DEFAULT_PRODUCTIVE_HOURS_YEAR/DEFAULT_EMPLOYER_COST_PCT/PROJECT_NAME"),
]


@pytest.mark.parametrize("rel,patron,ajuste", _A_SETTINGS)
def test_valor_movido_a_settings(rel, patron, ajuste):
    src = (RAIZ / rel).read_text(encoding="utf-8")
    assert not re.search(patron, src, re.M), f"{rel}: valor en duro; usa {ajuste}"


def test_ajustes_nuevos_con_su_valor_de_siempre():
    from app.core.config import settings
    esperados = {
        "SLA_AT_RISK_WINDOW_HOURS": 2.0, "SD_AUTO_CLOSE_HOURS_AFTER_RESOLUTION": 72,
        "SD_VALIDATION_WINDOW_HOURS": 48, "KEDB_DEFAULT_REVIEW_DAYS": 90,
        "ORG_DEFAULT_MAX_USERS": 25, "ORG_DEFAULT_MAX_PROJECTS": 100,
        "DEFAULT_PRODUCTIVE_HOURS_YEAR": 1700.0, "DEFAULT_EMPLOYER_COST_PCT": 0.32,
    }
    campos = type(settings).model_fields
    assert {k: campos[k].default for k in esperados} == esperados


# ── 10. Paletas de los PDF ───────────────────────────────────────────────────
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@pytest.mark.parametrize("rel", ["app/services/report_pdf_service.py", "app/services/signature_pdf.py"])
def test_pdf_sin_colores_propios(rel):
    malos = [f"{rel}:{ln} {v}" for ln, v in _cadenas((RAIZ / rel).read_text(encoding="utf-8")) if _HEX.match(v)]
    assert not malos, "Color en duro en un PDF; va a app/services/_pdf_marca.py:\n" + "\n".join(malos)


# ── 11. Frontend ─────────────────────────────────────────────────────────────
FRONT = RAIZ / "frontend" / "src"


def _fuentes_frontend():
    for p in sorted(list(FRONT.rglob("*.ts")) + list(FRONT.rglob("*.tsx"))):
        rel = p.relative_to(RAIZ).as_posix()
        if "/__tests__/" in rel or ".test." in rel or "/i18n/" in rel:
            continue
        yield rel, p.read_text(encoding="utf-8")


def test_frontend_sin_zona_horaria_por_defecto_en_duro():
    """La zona sale de la empresa (`useOrgSettings`) o del navegador; la lista, de constants/timezones.ts."""
    malos = [f"{rel}:{i}" for rel, src in _fuentes_frontend() if rel != "frontend/src/constants/timezones.ts"
             for i, linea in enumerate(src.splitlines(), 1) if "Europe/Madrid" in linea]
    assert not malos, "Zona horaria en duro en el frontend:\n" + "\n".join(malos)


def test_bpmn_mismo_target_namespace_en_frontend_y_backend():
    from app.services.bpmn_process_service import BPMN_TARGET_NAMESPACE
    front = (FRONT / "constants" / "bpmn.ts").read_text(encoding="utf-8")
    assert f"'{BPMN_TARGET_NAMESPACE}'" in front
    malos = [rel for rel, src in _fuentes_frontend() if "targetNamespace=\"http" in src]
    assert not malos, f"targetNamespace en duro: {malos}"


def test_las_excepciones_siguen_existiendo():
    """Una excepcion cuyo fichero ya no existe sobra: se quita de la lista."""
    for tabla in (_ZONA_PERMITIDA, _LOCALE_PERMITIDO, _CORREO_PERMITIDO, _TOPE_PERMITIDO, _ESTADOS_PERMITIDOS):
        for rel in tabla:
            assert (RAIZ / rel).exists(), f"excepcion obsoleta: {rel}"
