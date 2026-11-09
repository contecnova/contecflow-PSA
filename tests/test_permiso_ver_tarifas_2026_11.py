"""`can_see_rates` se aplica (revisión 2026-11).

Medido antes: el interruptor de /project-permissions se guardaba y no lo leía
nadie. La lista de imputaciones de un proyecto daba el coste de cada una
(horas × tarifa), también las de los compañeros.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.enterprise import ProjectPermission
from app.models.imputation import Imputation
from app.models.user import User
from tests.conftest import auth
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1)


def _costes(client, token):
    r = client.get("/api/v1/imputations", params={"project_id": "p-b1"}, headers=auth(token))
    assert r.status_code == 200, r.text
    return {i["description"]: i["cost_amount"] for i in r.json()["items"]}


def test_EL_HALLAZGO_sin_ver_tarifas_las_ajenas_salen_sin_coste(client, db, pm_token, proyecto):
    pm = db.query(User).filter(User.username == "pm_test").one()
    dev = db.query(User).filter(User.username == "dev_test").one()
    for quien, desc in ((pm, "mía"), (dev, "ajena")):
        db.add(Imputation(id=str(uuid.uuid4()), user_id=quien.id, project_id="p-b1", date=date(2026, 3, 2), hours=2,
                          cost_amount=100, organization_id="1", description=desc))
    db.commit()
    assert _costes(client, pm_token) == {"mía": 100, "ajena": 100}
    db.add(ProjectPermission(project_id="p-b1", user_id=pm.id, can_see_rates=False, can_see_financials=True,
                             organization_id="1"))
    db.commit()
    assert _costes(client, pm_token) == {"mía": 100, "ajena": None}
