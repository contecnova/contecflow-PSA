"""Quien pide no aprueba, también fuera de la bandeja (revisión 2026-11).

Medido antes: la bandeja de aprobaciones ya lo impedía, pero las rutas que
aprueban directamente no comparaban al que aprueba con el solicitante; un
responsable podía aprobarse su propia ausencia.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.resources import Absence, AbsenceStatus, AbsenceType
from app.models.user import User
from app.services.approval_engine._base import exigir_que_no_sea_suyo
from tests.conftest import auth
from app.core.errores import ErrorDeDominio


def test_la_regla():
    yo = SimpleNamespace(id="u1", role="admin")
    with pytest.raises((HTTPException, ErrorDeDominio)) as e:
        exigir_que_no_sea_suyo(None, "u1", yo, "absence", "a1")
    assert e.value.status_code == 403
    exigir_que_no_sea_suyo(None, "u2", yo, "absence", "a1")
    exigir_que_no_sea_suyo(None, None, yo, "absence", "a1")


def _ausencia(db, user):
    a = Absence(user_id=user.id, type=list(AbsenceType)[0], start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 2), status=AbsenceStatus.pending, organization_id=user.organization_id)
    db.add(a); db.commit()
    return a


def test_EL_HALLAZGO_un_responsable_no_se_aprueba_su_ausencia(client, db, pm_token):
    pm = db.query(User).filter(User.username == "pm_test").one()
    dev = db.query(User).filter(User.username == "dev_test").one()
    propia, ajena = _ausencia(db, pm), _ausencia(db, dev)
    r = client.post(f"/api/v1/absences/{propia.id}/review", headers=auth(pm_token), json={"approved": True})
    assert r.status_code == 403 and "SoD" in r.json()["detail"]
    r = client.post(f"/api/v1/absences/{ajena.id}/review", headers=auth(pm_token), json={"approved": True})
    assert r.status_code == 200


def test_el_resto_de_caminos_usa_la_misma_regla():
    """Cada aprobación directa llama a la regla con su solicitante."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1] / "app"
    esperado = {
        "api/v1/endpoints/absences.py": "a.user_id", "api/v1/endpoints/changes.py": "cr.requested_by",
        "services/documents_service.py": "doc.created_by", "services/psa_flows.py": "imp.user_id",
        "services/service_desk/change_management_service.py": "change.requester_id",
        "services/service_desk/change_service.py": "change.requester_id",
    }
    for f, campo in esperado.items():
        assert f"exigir_que_no_sea_suyo(db, {campo}, current_user" in (raiz / f).read_text(), f
