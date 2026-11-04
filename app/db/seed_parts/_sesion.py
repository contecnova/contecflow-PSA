"""Sesion de la siembra de demo, con la organizacion de demo publicada.

Auditoria 2026-11: la siembra creaba casi todo con `organization_id` NULL
(imputaciones, hitos, entregables, tickets, KB, catalogo…): sus sesiones no
llevaban organizacion y el sellado automatico (`_sellar_organizacion`) no tenia
que poner. El filtro de tenant esconde esas filas a los usuarios y al portal.

Solo se publica `organization_id`, no `is_superadmin`: el sellado pone la
organizacion en lo nuevo y las lecturas de la siembra siguen sin filtrar.
"""
from app.db.session import SessionLocal

SLUG_DEMO = "contecflow-demo"


def publicar_org_de_demo(db) -> None:
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.slug == SLUG_DEMO).first()
    if org is not None:
        db.info["organization_id"] = org.id


def sesion_de_siembra():
    db = SessionLocal()
    publicar_org_de_demo(db)
    return db
