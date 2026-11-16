"""Marcos de cumplimiento: catálogo de controles con evidencia (revisión GRC 16-11-2026).

Vivía como dos diccionarios en `app/api/v1/endpoints/governance.py` y tenía
tres problemas:

- mezclaba ediciones de ISO 27001: `A.5.17` y `A.5.33` son de la de 2022 y
  `A.9.2` («User access provisioning») de la de 2013, que en 2022 es `A.5.18`;
- el paquete `password_strict` citaba `SOC2-CC6.3`, que no estaba en el
  catálogo (no se podía registrar evidencia para él), y `SOC2-CC6.2` se
  titulaba «Authentication Hardening» cuando CC6.2 es el alta y autorización
  de usuarios;
- los identificadores no casaban con los del informe medido
  (`informe_de_cumplimiento`, que escribe «ISO27001 A.8.5»), así que el estado
  de un control no podía usar lo que el sistema ya mide.

Aquí queda una sola fuente. Los títulos no se guardan: la interfaz los traduce
con `grc.marco_control_<id normalizado>` (ver `clave_de_texto`) y
`tests/test_i18n_codigos_del_backend.py` exige el texto en cada idioma.
"""
from __future__ import annotations

import re

#: framework -> identificadores de control (ISO 27001:2022, SOC 2 TSC 2017).
CONTROLES: dict[str, tuple[str, ...]] = {
    "SOC2": ("SOC2-CC6.1", "SOC2-CC6.2", "SOC2-CC6.3", "SOC2-CC7.2"),
    "ISO27001": ("ISO27001-A.5.17", "ISO27001-A.5.18", "ISO27001-A.5.33", "ISO27001-A.8.5", "ISO27001-A.8.15"),
}

#: Identificadores antiguos que se siguen aceptando y cuentan como el nuevo.
#: Las evidencias ya guardadas con `ISO27001-A.9.2` no se reescriben (no hay
#: migración de datos): se leen como `ISO27001-A.5.18`.
ALIAS: dict[str, str] = {"ISO27001-A.9.2": "ISO27001-A.5.18"}

#: Tipos de evidencia que admite la API (la columna es `String(30)`).
TIPOS_DE_EVIDENCIA: tuple[str, ...] = ("policy", "screenshot", "report", "ticket", "audit_log", "other")

#: Paquetes de políticas por empresa: versión inicial y controles que cubren.
PAQUETES: dict[str, dict] = {
    "access_baseline": {"version": "1.0", "description": "MFA, least privilege y revisión periódica de accesos",
                        "controls": ["SOC2-CC6.1", "SOC2-CC6.2", "SOC2-CC6.3", "ISO27001-A.5.18"]},
    "password_strict": {"version": "1.0", "description": "Política de contraseñas robusta y lockout",
                        "controls": ["SOC2-CC6.1", "ISO27001-A.5.17", "ISO27001-A.8.5"]},
    "audit_retention": {"version": "1.0", "description": "Retención de evidencias y trazabilidad de auditoría",
                        "controls": ["SOC2-CC7.2", "ISO27001-A.5.33", "ISO27001-A.8.15"]},
}


def canonico(control_id: str) -> str:
    """El identificador vigente (aplica `ALIAS`)."""
    return ALIAS.get(control_id, control_id)


def con_alias(control_id: str) -> list[str]:
    """El identificador y los antiguos que equivalen a él (para filtrar evidencias)."""
    return [control_id, *(viejo for viejo, nuevo in ALIAS.items() if nuevo == control_id)]


def del_informe(referencia: str) -> str:
    """«ISO27001 A.8.5» (formato del informe medido) -> «ISO27001-A.8.5»."""
    return referencia.replace(" ", "-", 1)


def clave_de_texto(control_id: str) -> str:
    """Sufijo de la clave i18n del título: «ISO27001-A.5.17» -> «ISO27001_A_5_17»."""
    return re.sub(r"[^A-Za-z0-9]", "_", control_id)
