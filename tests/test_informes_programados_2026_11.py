"""Informes programados (revisión 2026-11).

Medido antes: el PDF salía sin datos (la métrica no se consultaba), el enlace
de vista previa apuntaba a una ruta que no existe y pintaba filas de ejemplo,
sin SMTP el envío quedaba como correcto, y la programación ignoraba la hora y
el día.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.billing_reports import ScheduledReport
from app.models.imputation import Imputation
from app.services import scheduled_reports as sr
from app.services.report_pdf_service import datos_de_la_metrica
from tests.conftest import auth

LUNES_10H = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)   # lunes


@pytest.mark.parametrize("freq,extra,esperado", [
    ("daily", {"send_hour": 7}, datetime(2026, 11, 10, 7, tzinfo=timezone.utc)),
    ("daily", {"send_hour": 18}, datetime(2026, 11, 9, 18, tzinfo=timezone.utc)),
    ("weekly", {"send_hour": 9, "day_of_week": 4}, datetime(2026, 11, 13, 9, tzinfo=timezone.utc)),
    ("weekly", {"send_hour": 9, "day_of_week": 0}, datetime(2026, 11, 16, 9, tzinfo=timezone.utc)),
    ("monthly", {"send_hour": 8, "day_of_month": 31}, datetime(2026, 11, 30, 8, tzinfo=timezone.utc)),
])
def test_EL_HALLAZGO_la_proxima_ejecucion_respeta_hora_y_dia(freq, extra, esperado):
    assert sr._get_next_run(freq, LUNES_10H, **extra) == esperado


def test_EL_HALLAZGO_el_pdf_lleva_los_datos_de_la_metrica(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    db.add(Project(id="p-inf", code="P-INF", name="Inf", status=ProjectStatus.active,
                   project_type=ProjectType.consulting, organization_id="1"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id="pm-test-id", project_id="p-inf", date=date.today(), hours=6,
                      organization_id="1", description="x"))
    db.commit()
    filas, resumen, _ = datos_de_la_metrica(SimpleNamespace(metric="hours_by_month", filters_json="{}"), db, "1")
    assert filas and resumen["Filas"] == len(filas)
    with pytest.raises(ValueError):
        datos_de_la_metrica(SimpleNamespace(metric="inventada", filters_json="{}"), db, "1")


def test_sin_correo_el_envio_falla_y_lo_dice(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SMTP_HOST", "", raising=False)
    r = ScheduledReport(name="Horas", metric="hours_by_month", frequency="weekly", recipients='["a@b.example"]',
                        report_type="custom", include_pdf=True, organization_id="1")
    db.add(r); db.commit()
    res = sr.execute_report_now(r.id, db)
    db.refresh(r)
    assert res["ok"] is False and r.last_status == "error" and "SMTP" in r.last_error


def test_el_alta_guarda_hora_y_dia_y_la_vista_previa_es_el_pdf(client, db, admin_token):
    r = client.post("/api/v1/billing-reports/scheduled-reports", headers=auth(admin_token), json={
        "name": "Horas", "metric": "hours_by_month", "frequency": "weekly", "recipients": ["a@b.example"],
        "day_of_week": 4, "send_hour": 9})
    assert r.status_code in (200, 201), r.text
    rid = r.json()["data"]["id"]
    fila = db.get(ScheduledReport, rid)
    assert (fila.day_of_week, fila.send_hour, fila.next_run_at.weekday(), fila.next_run_at.hour) == (4, 9, 4, 9)
    pdf = client.get(f"/api/v1/billing-reports/scheduled-reports/{rid}/preview-pdf", headers=auth(admin_token))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
