"""Mensajes de error de las herramientas del asistente, en el idioma de quien pregunta (23-11-2026).

Antes eran castellano fijo dentro de cada herramienta; ahora salen de
`textos_de_salida` (claves `ia_tool.*`, bloque `textos_de_salida_servicios_a_l`).
"""
from __future__ import annotations

from app.services.formato_regional import idioma_de_salida
from app.services.textos_de_salida import texto


def mensaje(db, user, clave: str, **params) -> str:
    """El texto `ia_tool.<clave>` en el idioma del usuario (o de su empresa)."""
    idioma = idioma_de_salida(db, user_id=getattr(user, "id", None),
                              org_id=getattr(user, "organization_id", None))
    return texto(f"ia_tool.{clave}", idioma, **params)
