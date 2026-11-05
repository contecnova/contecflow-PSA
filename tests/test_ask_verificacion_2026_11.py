"""Ask-the-Data: verificación de que la consulta responde a ESTA pregunta (revisión 2026-11).

Antes solo se comprobaba que la consulta se ejecutara: «horas de marzo»
contestada con todo el histórico daba un número real, y más alto.
"""
from __future__ import annotations

import pytest

from app.services.ask_verificacion import verificar

CASOS = [
    ("¿Cuántas horas se imputaron en marzo?", "SELECT SUM(hours) FROM fact_imputations", "warning", "time_window"),
    ("¿Cuántas horas se imputaron en marzo?",
     "SELECT SUM(i.hours) FROM fact_imputations i JOIN dim_date d ON d.date_key=i.date_key WHERE d.month=3", "verified", None),
    ("Top 5 proyectos con más horas", "SELECT project_id, SUM(hours) h FROM fact_imputations GROUP BY project_id LIMIT 5", "warning", "ranking"),
    ("Horas por proyecto", "SELECT SUM(hours) FROM fact_imputations", "warning", "breakdown"),
    ("¿Cuántos clientes distintos tienen tickets?", "SELECT COUNT(client_id) FROM fact_tickets", "warning", "distinct"),
    ("¿Cuántos clientes distintos tienen tickets?", "SELECT COUNT(DISTINCT client_id) FROM fact_tickets", "verified", None),
    ("Porcentaje de tickets con SLA incumplido", "SELECT COUNT(*) FROM fact_tickets WHERE sla_breached", "warning", "units"),
    ("Hours by project last month", "SELECT SUM(hours) FROM fact_imputations", "warning", "time_window"),
    ("proyectos con presupuesto mayor que 1000", "SELECT name FROM dim_project WHERE budget>1000", "not_checked", None),
    # Chino (revisión 2026-11): antes todas quedaban «sin comprobar».
    ("三月份登记了多少工时？", "SELECT SUM(hours) FROM fact_imputations", "warning", "time_window"),
    ("三月份登记了多少工时？",
     "SELECT SUM(i.hours) FROM fact_imputations i JOIN dim_date d ON d.date_key=i.date_key WHERE d.month=3", "verified", None),
    ("按项目统计工时", "SELECT SUM(hours) FROM fact_imputations", "warning", "breakdown"),
    ("工时最多的前5个项目", "SELECT project_id, SUM(hours) h FROM fact_imputations GROUP BY project_id LIMIT 5", "warning", "ranking"),
    ("有工单的不同客户有多少？", "SELECT COUNT(client_id) FROM fact_tickets", "warning", "distinct"),
    ("SLA 违约工单的占比", "SELECT COUNT(*) FROM fact_tickets WHERE sla_breached", "warning", "units"),
    ("项目的平均利润率", "SELECT SUM(margin) FROM fact_projects", "warning", "units"),
    ("列出进行中的项目", "SELECT name FROM dim_project WHERE status='active'", "not_checked", None),
]


@pytest.mark.parametrize("pregunta,sql,veredicto,aviso", CASOS)
def test_EL_HALLAZGO_detecta_la_respuesta_a_otra_pregunta(pregunta, sql, veredicto, aviso):
    r = verificar(pregunta, sql)
    assert r["verdict"] == veredicto, r
    avisos = [c["name"] for c in r["checks"] if c["status"] == "warning"]
    assert (aviso in avisos) if aviso else not avisos


def test_lo_que_no_se_mira_no_se_da_por_verificado():
    assert verificar("Lista los proyectos activos", "SELECT name FROM dim_project WHERE status='active'")["verdict"] == "not_checked"
    assert verificar("¿horas de marzo?", "esto no es sql")["verdict"] == "not_checked"


def test_ask_devuelve_la_verificacion_de_la_consulta_del_modelo(db, monkeypatch):
    from app.services import ask_the_data as atd
    monkeypatch.setattr(atd, "_generate_sql", lambda *a, **k: "SELECT SUM(hours) AS h FROM fact_imputations")
    monkeypatch.setattr(atd, "_execute_on_olap", lambda sql, params=None: [{"h": 120}])
    r = atd.ask("¿Cuántas horas se imputaron en marzo?", db, org_id="1")
    assert r["error"] is None and r["verification"]["verdict"] == "warning"
