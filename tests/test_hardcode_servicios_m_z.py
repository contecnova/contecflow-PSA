"""Textos fijos de los servicios m-z (23-11-2026): estatico y barato.

Comprueba que las claves nuevas (`textos_de_salida_servicios_m_z`) llevan
es/en/zh con los mismos datos, que `plantillas_aviso` tiene chino en todas sus
entradas y que los literales retirados ya no estan en los servicios.
"""
from __future__ import annotations

import string
from pathlib import Path

from app.services import textos_de_salida_servicios_m_z as bloque
from app.services.textos_de_salida import TEXTOS
from app.services.service_desk.plantillas_aviso import ETIQUETAS, IDIOMAS, POR_DEFECTO

RAIZ = Path(__file__).resolve().parents[1] / "app" / "services"


def _campos(plantilla: str) -> set[str]:
    return {c[1].split(".")[0].split("[")[0] for c in string.Formatter().parse(plantilla) if c[1]}


def test_claves_nuevas_con_es_en_zh():
    assert len(bloque.TEXTOS_SERVICIOS_M_Z) > 250
    for clave, variantes in bloque.TEXTOS_SERVICIOS_M_Z.items():
        for idioma in ("es", "en", "zh"):
            assert variantes.get(idioma), f"{clave} sin {idioma}"
        assert _campos(variantes["es"]) == _campos(variantes["en"]) == _campos(variantes["zh"]), clave
        assert TEXTOS[clave] is variantes, f"{clave}: otro bloque la pisa"


def test_plantillas_de_aviso_con_zh():
    import re
    variables = lambda t: set(re.findall(r"\{\{(\w+)\}\}", t))  # noqa: E731
    assert "zh" in IDIOMAS and "zh" in ETIQUETAS
    for codigo, variantes in POR_DEFECTO.items():
        asunto, cuerpo = variantes["zh"]
        assert asunto and cuerpo, codigo
        # el chino no usa variables que no existan en la versión inglesa
        assert variables(asunto) <= variables(variantes["en"][0]) | variables(variantes["es"][0]), codigo
        assert variables(cuerpo) <= variables(variantes["en"][1]) | variables(variantes["es"][1]), codigo
    assert set(ETIQUETAS["zh"]) == set(ETIQUETAS["en"])


def _fuente(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


RETIRADOS = {
    "presupuestos_preparar.py": ["Presupuesto «{b.name}» sin enviar", "La campaña «"],
    "presupuestos_seguir.py": ['"Rechazado en la bandeja de aprobaciones"', "Presupuesto consumido al ",
                               "La previsión al cierre llega al "],
    "milestone_service.py": ["Milestone aprobado: ", "rechazó el milestone", "Aprobación solicitada: "],
    "perf_reminder_service.py": ["sin fecha de cierre", "Accede al módulo de evaluaciones"],
    "proveedores/portal.py": ["informe nuevo del proveedor", "Revísalo en su ficha"],
    "psa_flows.py": ["Imputación rechazada por manager", "[Devuelto para correccion]", "Decidido en Partes de horas"],
    "metrics/projects.py": ["STATUS_TASK_LABELS", '"Consultoría"', '"Crítico"'],
    "session_security.py": ['"Cambio de IP"', '"IP ausente"', "ASN/ISP con perfil"],
    "raci_service.py": ["Alta tasa de completitud", "Daily standup: escalar", "No hay tareas completadas"],
    "scenarios_service.py": ["El equipo tiene capacidad suficiente", "Proyecto hipotético\")"],
    "resumen_de_avisos.py": ["Abrir la bandeja</a>", "aviso(s) sin leer de las"],
    "teams_bot.py": ["No encuentro nada sobre eso", "Ahora mismo no puedo consultar"],
    "revenue_service.py": ['f"Hito completado', '"Obligación satisfecha', "Reversal de entrada", 'f"Por avance:'],
    "service_desk/rca_wizard_service.py": ["¿Por qué ocurrió el problema?", "Análisis Fishbone:", "5 Whys (Toyota)\","],
    "service_desk/sla_event_service.py": ['"SLA pausado"', "SLA reanudado"],
    "service_desk/canal_slack.py": ['"Uso: ticket <asunto>"', '"Asignarme"', "adjunto no disponible: {nombre}]\")",
                                    '"No encuentro tu usuario'],
    "service_desk/change_management_service.py": ['"Verify all systems online"', "Manual approval before each phase",
                                                  "Automatic rollback triggered for change",
                                                  "[EMERGENCY CAB FAST-TRACK]"],
    "service_desk/governance_compliance_service.py": ['"P1 incidents without Major Incident record"',
                                                      "_CMM_LABELS", "Implementar registro formal de aprobación CAB"],
    "service_desk/problem_service.py": ["[Auto-detected]", "[RFC] Resolver causa raíz", "Unable to determine automatically"],
    "marketplace_service.py": [],
}


def test_literales_retirados_ausentes():
    for ruta, textos in RETIRADOS.items():
        fuente = _fuente(ruta)
        for t in textos:
            assert t not in fuente, f"{ruta}: sigue el literal {t!r}"


def test_hallazgo_de_sla_se_reconoce_por_codigo():
    """La puntuación de SLA ya no depende del texto del título (que se traduce)."""
    fuente = _fuente("service_desk/governance_compliance_service.py")
    assert 'if "SLA" in hallazgo["title"]' not in fuente
    assert "sla_resolution_breach" in fuente


def test_descripciones_del_marketplace_por_clave():
    from app.services.marketplace_service import CONNECTOR_CATALOG
    for item in CONNECTOR_CATALOG:
        assert f"marketplace.desc.{item['slug']}" in TEXTOS, item["slug"]


def test_motivos_de_sesion_por_codigo():
    from app.services.session_security import parse_risk_reasons
    assert parse_risk_reasons('["ip_change", "texto antiguo"]', "zh") == ["IP 地址变化", "texto antiguo"]
    assert parse_risk_reasons('["ip_change"]', "en") == ["IP change"]
