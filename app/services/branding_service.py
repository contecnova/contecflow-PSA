"""Marca blanca por organización: leer, actualizar y restablecer.

Auditoría 2026-08 (hallazgo 22). Estas consultas vivían en
`endpoints/branding.py`. A diferencia de casi todo el resto del hallazgo, **aquí
las guardas ya estaban bien puestas**: los tres endpoints llaman a
`assert_org_id_is_own` antes de tocar nada, y sus comentarios explican por qué
—`org_id` llega por la ruta, `Organization` es el único modelo sin columna de
tenant, y el `SELECT` filtrado por sí solo dejaría caer un `PUT` en la rama de
creación, donde el `INSERT` no filtra—. Así que el trabajo aquí es mover las
consultas, no arreglar una guarda.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tenancy import assert_org_id_is_own

#: Un nombre de variable CSS y su valor, acotados. Vienen del cliente y acaban
#: en una hoja de estilo: sin tope, una sola variable puede pesar megas.
MAX_LONGITUD_NOMBRE_CSS = 80
MAX_LONGITUD_VALOR_CSS = 100


def _organizacion(db: Session, org_id: str):
    from app.models.mfa import Organization

    fila = db.query(Organization).filter(Organization.id == org_id).first()
    if not fila:
        raise HTTPException(404, "Organization not found")
    return fila


def _marca(db: Session, org_id: str):
    from app.models.white_label import OrgBranding

    return (
        db.query(OrgBranding)
        .filter(OrgBranding.organization_id == org_id)
        .first()
    )


def marca_de_la_organizacion(db: Session, user, org_id: str):
    """La marca de esa organización, o `None` si nunca se configuró.

    `org_id` llega por la ruta, así que se comprueba a mano: `Organization` es el
    único modelo sin columna de tenant y `TenantSession` no lo filtra.
    """
    assert_org_id_is_own(user, org_id, detail="Organization not found")
    _organizacion(db, org_id)
    return _marca(db, org_id)


def _variables_css_seguras(valores: dict) -> dict:
    """Sólo variables CSS de verdad, con nombre y valor acotados."""
    return {
        clave: valor
        for clave, valor in (valores or {}).items()
        if clave.startswith("--")
        and len(clave) < MAX_LONGITUD_NOMBRE_CSS
        and len(str(valor)) < MAX_LONGITUD_VALOR_CSS
    }


def guardar_marca(db: Session, user, org_id: str, cambios: dict):
    """Crea o actualiza la marca de esa organización.

    La comprobación va **antes** del `SELECT`, y no es cosmético: sin ella un
    `org_id` ajeno devuelve `None` en el `SELECT` —eso sí lo filtra
    `TenantSession`— y se cae en la rama de creación, cuyo `INSERT` no filtra
    nada. Se escribiría la marca de otro cliente.
    """
    from app.models.white_label import OrgBranding

    assert_org_id_is_own(user, org_id, detail="Organization not found")
    _organizacion(db, org_id)

    fila = _marca(db, org_id)
    if not fila:
        fila = OrgBranding(organization_id=org_id, created_by=user.id)
        db.add(fila)

    for campo, valor in cambios.items():
        if campo == "custom_css_vars":
            setattr(fila, campo, json.dumps(_variables_css_seguras(valor)))
        else:
            setattr(fila, campo, valor)

    db.commit()
    db.refresh(fila)
    return fila


def restablecer_marca(db: Session, user, org_id: str) -> None:
    """Borra la marca para volver a la de por defecto. Idempotente.

    La guarda explícita está aquí porque el `SELECT` filtrado convertiría al
    filtro de sesión en el control de autorización, y ese filtro es una red de
    seguridad: en esta misma auditoría se comprobó que hay caminos donde no
    actúa.
    """
    assert_org_id_is_own(user, org_id, detail="Organization not found")
    fila = _marca(db, org_id)
    if fila:
        db.delete(fila)
        db.commit()


def variables_css_seguras(valores: Optional[dict]) -> dict:
    """Expuesta para que el saneado se pueda probar por separado."""
    return _variables_css_seguras(valores or {})
