"""Clases de CI configurables por empresa (mejoras de mercado 16-11-2026, migracion 174).

Cada empresa declara sus clases («Firewall», «Cajero», «Licencia SaaS»…) y cada
una se apoya en una clase base (`CIType`), que es la que siguen entendiendo el
descubrimiento, el analisis de impacto, la topologia y los datos propios de
clase. Un CI con clase propia guarda la clave en `ci_class` y su clase base en
`ci_type`. Todo se acota a la empresa de quien pide.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.service_desk import CIClass, CIType, ConfigurationItem
from app.services.audit import auditar_y_confirmar
from app.core.codigos_de_error import error

CLASES_BASE = tuple(c.value for c in CIType)
CAMPOS_EDITABLES = ("label", "base_type", "description", "is_active", "sort_order")


def serializar(c: CIClass, en_uso: int = 0) -> dict:
    return {"id": c.id, "key": c.key, "label": c.label, "base_type": c.base_type, "description": c.description,
            "is_active": c.is_active, "sort_order": c.sort_order, "ci_count": en_uso}


def _uso(db: Session, org_id, clave: str) -> int:
    return db.query(ConfigurationItem.id).filter(ConfigurationItem.organization_id == org_id,
                                                 ConfigurationItem.ci_class == clave,
                                                 ConfigurationItem.is_active.is_(True)).count()


def _de_la_empresa(db: Session, class_id: str, org_id) -> CIClass:
    c = db.query(CIClass).filter(CIClass.id == class_id, CIClass.organization_id == org_id).first()
    if c is None:
        raise error(404, "no_encontrado", detail="Clase no encontrada", que="clase")
    return c


def listar(db: Session, org_id) -> dict:
    filas = db.query(CIClass).filter(CIClass.organization_id == org_id).order_by(
        CIClass.sort_order, CIClass.label).all()
    return {"base_types": list(CLASES_BASE), "classes": [serializar(c, _uso(db, org_id, c.key)) for c in filas]}


def crear(db: Session, usuario, datos: dict) -> dict:
    if datos.get("base_type") not in CLASES_BASE:
        raise error(422, "ci_clase_base_no_valida")
    if datos.get("key") in CLASES_BASE:
        raise error(422, "ci_clave_de_clase_base")
    org = usuario.organization_id
    if db.query(CIClass.id).filter(CIClass.organization_id == org, CIClass.key == datos.get("key")).first():
        raise error(409, "ci_clase_ya_existe")
    c = CIClass(organization_id=org, **datos)
    db.add(c)
    db.flush()
    auditar_y_confirmar(db, usuario, "CREATE", "sd_ci_class", c.id, c.label, new_values=datos)
    return serializar(c)


def cambiar(db: Session, usuario, class_id: str, datos: dict) -> dict:
    org = usuario.organization_id
    c = _de_la_empresa(db, class_id, org)
    if datos.get("base_type") not in CLASES_BASE:
        raise error(422, "ci_clase_base_no_valida")
    if datos["base_type"] != c.base_type:
        # Sus CIs pasan a la nueva clase base: es lo que leen descubrimiento e impacto.
        db.query(ConfigurationItem).filter(ConfigurationItem.organization_id == org,
                                           ConfigurationItem.ci_class == c.key).update(
            {ConfigurationItem.ci_type: datos["base_type"]}, synchronize_session=False)
    for k in CAMPOS_EDITABLES:
        setattr(c, k, datos.get(k))
    auditar_y_confirmar(db, usuario, "UPDATE", "sd_ci_class", c.id, c.label, new_values=datos)
    return serializar(c, _uso(db, org, c.key))


def desactivar(db: Session, usuario, class_id: str) -> None:
    c = _de_la_empresa(db, class_id, usuario.organization_id)
    c.is_active = False
    auditar_y_confirmar(db, usuario, "DELETE", "sd_ci_class", c.id, c.label)
