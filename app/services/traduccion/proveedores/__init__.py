"""Proveedores de traduccion intercambiables (`TRANSLATION_PROVIDER`).

- `ai`: el proveedor de IA de la empresa (por defecto).
- `deepl`: DeepL API, con las credenciales cifradas de la empresa.
- `azure`: Azure AI Translator, con las credenciales cifradas de la empresa.

`FABRICAS` es el unico sitio que sabe construirlos: los tests ponen ahi un
doble con la misma interfaz (`ProveedorDeTraduccion`).
"""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.services.traduccion.proveedores.base import (  # noqa: F401
    ErrorDeTraduccion, ProveedorDeTraduccion, Traducido, credenciales_de_la_empresa,
)


def _ia(db: Session, org_id: Optional[str], user_id: Optional[str]):
    from app.services.traduccion.ajustes import max_tokens_ia
    from app.services.traduccion.proveedores.ia import ProveedorIA
    return ProveedorIA(db, org_id, user_id, max_tokens=max_tokens_ia(db, org_id))


def _deepl(db: Session, org_id: Optional[str], user_id: Optional[str]):
    from app.services.traduccion.proveedores.deepl import ProveedorDeepL
    return ProveedorDeepL(db, org_id)


def _azure(db: Session, org_id: Optional[str], user_id: Optional[str]):
    from app.services.traduccion.proveedores.azure import ProveedorAzure
    return ProveedorAzure(db, org_id)


FABRICAS: dict[str, Callable[[Session, Optional[str], Optional[str]], ProveedorDeTraduccion]] = {
    "ai": _ia,
    "deepl": _deepl,
    "azure": _azure,
}


def proveedor_de(db: Session, org_id: Optional[str], nombre: str, user_id: Optional[str] = None):
    fabrica = FABRICAS.get(nombre)
    if fabrica is None:
        raise ErrorDeTraduccion("provider_not_configured")
    return fabrica(db, org_id, user_id)
