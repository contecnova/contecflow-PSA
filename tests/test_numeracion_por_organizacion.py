"""Numeracion por organizacion.

Medido el 2026-11-02 con dos organizaciones: la secuencia de `project` de la
organizacion A dejaba a la B con «RuntimeError: No se pudo inicializar la
secuencia», y los numeros de ticket se calculaban por organizacion contra una
unicidad de toda la base. Cada prueba repite la sonda que lo destapo.
"""
from __future__ import annotations


def _como(db, org):
    db.info["organization_id"] = org
    db.info["is_superadmin"] = False


def test_cada_organizacion_tiene_su_secuencia(db):
    from app.services.numbering import next_numbered_code

    _como(db, "org-a")
    assert next_numbered_code(db, "project", prefix="PRJ", padding=4) == "PRJ-0001"
    db.commit()
    _como(db, "org-b")
    assert next_numbered_code(db, "project", prefix="PRJ", padding=4) == "PRJ-0001"
    db.commit()
    _como(db, "org-a")
    assert next_numbered_code(db, "project", prefix="PRJ", padding=4) == "PRJ-0002"


def test_una_organizacion_sigue_desde_la_secuencia_antigua_sin_organizacion(db):
    from app.models.advanced_config import NumberingSequence
    from app.services.numbering import next_numbered_code
    from tests.conftest import fila_global

    with fila_global(db):
        db.add(NumberingSequence(entity="task", prefix="TSK", padding=5, current_value=41))
        db.commit()
    _como(db, "org-a")
    assert next_numbered_code(db, "task", prefix="T", padding=4) == "TSK-00042", (
        "arrancar de cero repetiria numeros ya emitidos con la secuencia unica")


def test_dos_organizaciones_tienen_su_inc_0001(db):
    from app.models.service_desk import Ticket
    from app.services.sla_service import next_ticket_number

    for org in ("org-a", "org-b"):
        _como(db, org)
        db.add(Ticket(number=next_ticket_number("incident", db), ticket_type="incident",
                      title="t", description="d", organization_id=org))
        db.commit()
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        numeros = sorted((t.organization_id, t.number) for t in db.query(Ticket).all())
    assert ("org-a", "INC-0001") in numeros and ("org-b", "INC-0001") in numeros


def test_sin_sesion_de_peticion_se_numera_en_la_organizacion_indicada(db):
    from app.models.service_desk import Ticket
    from app.services.sla_service import next_ticket_number

    db.add(Ticket(number="INC-0009", ticket_type="incident", title="t", description="d", organization_id="org-a"))
    db.commit()
    db.info.pop("organization_id", None)
    db.info.pop("is_superadmin", None)
    assert next_ticket_number("incident", db, "org-a") == "INC-0010"
    assert next_ticket_number("incident", db, "org-b") == "INC-0001"


def test_la_deteccion_de_problemas_no_mezcla_organizaciones(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.incident_intelligence_service import (
        PROBLEM_DETECTION_THRESHOLD, detect_recurring_incidents,
    )

    db.info.pop("organization_id", None)
    db.info.pop("is_superadmin", None)
    for org in ("org-a", "org-b"):
        for i in range(PROBLEM_DETECTION_THRESHOLD):
            db.add(Ticket(number=f"INC-{i + 1:04d}", ticket_type="incident", title="caida",
                          description="d", priority="p2_high", organization_id=org))
    db.commit()
    grupos = detect_recurring_incidents(db)
    assert sorted(g["organization_id"] for g in grupos) == ["org-a", "org-b"]
    for g in grupos:
        assert len(g["ticket_ids"]) == PROBLEM_DETECTION_THRESHOLD, "sin servicio, la lista salia vacia"
        assert g["priority"] == "p2_high"
