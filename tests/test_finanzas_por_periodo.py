"""El selector de periodo del panel de finanzas cambia las cifras.

Auditoria 2026-11: la pantalla mandaba `date_from`/`date_to` a
`/profitability/summary` y `/profitability/projects`, que los ignoraban.
"""
from datetime import date, timedelta

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth


def _datos(db):
    p = Project(code="FINP", name="Fin", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1", is_billable=True, billing_rate=100.0, currency="EUR")
    db.add(p)
    db.commit()
    hoy = date.today()
    for dias, horas in ((5, 2.0), (200, 10.0)):
        db.add(Imputation(user_id="dev-test-id", project_id=p.id, organization_id="1",
                          date=hoy - timedelta(days=dias), hours=horas, is_billable=True, cost_amount=horas * 40))
    db.commit()
    return p


def test_EL_HALLAZGO_el_periodo_cambia_ingresos_y_costes(client, pm_token, db):
    _datos(db)
    hoy = date.today()
    todo = client.get("/api/v1/profitability/summary", headers=auth(pm_token)).json()["data"]["portfolio"]
    mes = client.get("/api/v1/profitability/summary", headers=auth(pm_token), params={
        "date_from": str(hoy - timedelta(days=30)), "date_to": str(hoy)}).json()["data"]["portfolio"]
    assert todo["total_revenue"] == 1200 and todo["total_cost"] == 480
    assert mes["total_revenue"] == 200 and mes["total_cost"] == 80


def test_la_lista_de_proyectos_tambien(client, pm_token, db):
    p = _datos(db)
    hoy = date.today()
    filas = client.get("/api/v1/profitability/projects", headers=auth(pm_token), params={
        "date_from": str(hoy - timedelta(days=30)), "date_to": str(hoy)}).json()
    filas = filas.get("data", filas) if isinstance(filas, dict) else filas
    filas = filas.get("items", filas) if isinstance(filas, dict) else filas
    fila = next(f for f in filas if f.get("project_id", f.get("id")) == p.id)
    assert fila["internal_cost"] == 80
