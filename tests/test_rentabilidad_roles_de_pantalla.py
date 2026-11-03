"""Rentabilidad: los roles de la API son los de sus pantallas (admin y PM).

Auditoria 2026-11: el PM abria el panel de finanzas y la pagina de rentabilidad
y el resumen le daba 403; a la vez, cualquier empleado leia los margenes de
todos los proyectos por `/profitability/projects`.
"""
import pytest

from tests.conftest import auth


@pytest.mark.parametrize("ruta", ["/api/v1/profitability/summary", "/api/v2/profitability/summary",
                                  "/api/v1/profitability/projects"])
def test_pm_entra_y_empleado_no(client, pm_token, dev_token, ruta):
    assert client.get(ruta, headers=auth(pm_token)).status_code == 200
    assert client.get(ruta, headers=auth(dev_token)).status_code == 403

