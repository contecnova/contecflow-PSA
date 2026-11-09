"""Escenarios: la demanda total y el reparto salen de sus proyectos (revisión 2026-11).

Medido antes: esas líneas estaban sangradas dentro del bucle de reservas; sin
reservas el reparto salía vacío y la demanda a 0, y con reservas repetía el
último proyecto una vez por semana reservada.
"""
from __future__ import annotations

from datetime import date

from app.models.mfa import ScenarioModel, ScenarioProject
from app.services.scenarios_service import compute_scenario


def test_EL_HALLAZGO_cada_proyecto_cuenta_una_vez(db):
    esc = ScenarioModel(id="esc-1", name="Q1", base_date=date(2027, 1, 4), horizon_weeks=12, organization_id="1")
    db.add(esc)
    db.add_all([
        ScenarioProject(scenario_id="esc-1", name="ERP", start_date=date(2027, 1, 4), end_date=date(2027, 2, 1),
                        total_hours=200, organization_id="1"),
        ScenarioProject(scenario_id="esc-1", name="CRM", start_date=date(2027, 1, 11), end_date=date(2027, 3, 1),
                        total_hours=120, organization_id="1"),
    ])
    db.commit()
    r = compute_scenario("esc-1", db)
    assert r["total_demand_hours"] == 320.0
    assert sorted(p["name"] for p in r["project_breakdown"]) == ["CRM", "ERP"]
