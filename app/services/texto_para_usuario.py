"""El texto de salida en el idioma de quien lo va a leer (23-11-2026).

Atajo sobre `textos_de_salida.texto` + `formato_regional.idioma_de_salida` para los
avisos que el sistema escribe en nombre de otro (notificaciones, historial de
aprobaciones, tickets de remediacion...): cada destinatario lo recibe en el suyo
(sus preferencias o, si no, el de su empresa).
"""
from __future__ import annotations

from typing import Optional


def texto_para(db, user_id: Optional[str], clave: str, *, org_id: Optional[str] = None, **params) -> str:
    """`clave` de `textos_de_salida` en el idioma de `user_id` (o de `org_id` si no hay usuario)."""
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto
    return texto(clave, idioma_de_salida(db, user_id=user_id, org_id=org_id), **params)
