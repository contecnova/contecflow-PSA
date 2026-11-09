"""Tablero y alta de planes de capacidad: sólo responsables (revisión 2026-11).

Medido antes: cualquier empleado leía las horas planificadas de todos y
creaba planes para cualquiera; editar y borrar ya exigían responsable.
"""
from __future__ import annotations

from tests.conftest import auth


def test_EL_HALLAZGO_un_empleado_no_ve_ni_planifica_a_todos(client, dev_token, pm_token):
    assert client.get("/api/v1/capacity/board", headers=auth(dev_token)).status_code == 403
    assert client.post("/api/v1/capacity/plans", headers=auth(dev_token),
                       json={"user_id": "pm-test-id", "week_start": "2026-11-09", "planned_hours": 8}).status_code == 403
    assert client.get("/api/v1/capacity/board", headers=auth(pm_token)).status_code == 200
