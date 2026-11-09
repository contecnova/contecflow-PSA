"""Gastos: kilometraje, políticas que bloquean o avisan, justificantes, reparto y flujo (revisión 2026-11)."""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from app.models.expenses import Expense, ExpenseStatus
from app.models.project import Project, ProjectStatus, ProjectType
from app.services import settings_service
from tests.conftest import auth

URL = "/api/v1/expenses"


@pytest.fixture
def proyectos(db):
    for pid, code in (("p-g1", "PRJ-G1"), ("p-g2", "PRJ-G2")):
        db.add(Project(id=pid, code=code, name=code, status=ProjectStatus.active,
                       project_type=ProjectType.development, organization_id="1"))
    db.commit()
    return ("p-g1", "p-g2")


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    """Los ficheros, en un directorio temporal (el almacén local escribe en uploads/)."""
    import app.services.s3_service as s3
    monkeypatch.setattr(s3, "_LOCAL_UPLOAD_ROOT", tmp_path)


def _gasto(client, token, **extra):
    cuerpo = {"category": "meals", "description": "Comida con cliente", "amount": 40, "expense_date": "2026-11-03",
              "is_billable": False, **extra}
    r = client.post(URL, headers=auth(token), json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _politica(client, token, **campos):
    r = client.post(f"{URL}/policies", headers=auth(token), json={"nombre": "Comidas", **campos})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_el_kilometraje_lo_calcula_el_servidor_con_la_tarifa_de_admin(client, db, dev_token):
    g = _gasto(client, dev_token, category="travel", amount=1, km=100)
    assert g["amount"] == 26.0 and g["km"] == 100
    settings_service.set_runtime_value(db, "gastos", "EXPENSE_MILEAGE_RATE", 0.3, "1")
    db.commit()
    settings_service.invalidate_cache()
    r = client.patch(f"{URL}/my/{g['id']}", headers=auth(dev_token), json={"km": 50})
    assert r.json()["data"]["amount"] == 15.0


def test_EL_HALLAZGO_una_politica_que_bloquea_impide_enviar_y_dice_por_que(client, db, admin_token, dev_token):
    _politica(client, admin_token, categoria="meals", limite_por_gasto=30, accion="bloquear")
    g = _gasto(client, dev_token)
    chequeo = client.get(f"{URL}/{g['id']}/policy-check", headers=auth(dev_token)).json()["data"]
    assert chequeo["bloquea"] is True and chequeo["incumplimientos"][0]["regla"] == "limite_por_gasto"
    r = client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token))
    assert r.status_code == 422 and "supera el tope de 30.00" in r.json()["detail"]
    assert db.get(Expense, g["id"]).status == ExpenseStatus.draft
    # Otra categoría no la toca.
    t = _gasto(client, dev_token, category="training", amount=500)
    assert client.post(f"{URL}/my/{t['id']}/submit", headers=auth(dev_token)).status_code == 200


def test_avisar_deja_enviar_marcado_y_el_flujo_de_lo_que_excede_se_elige(client, db, admin_token, dev_token):
    from app.models.billing_reports import ApprovalWorkflow
    from app.services.approval_engine._base import elegir_flujo
    db.add(ApprovalWorkflow(id="wf-normal", name="Normal", entity_type="expense", is_active=True, is_default=True,
                            organization_id="1"))
    db.add(ApprovalWorkflow(id="wf-excede", name="Excede política", entity_type="expense", is_active=True,
                            is_default=False, organization_id="1", trigger_conditions=json.dumps({"policy_exceeded": True})))
    db.commit()
    _politica(client, admin_token, limite_por_gasto=30, accion="avisar")
    g = _gasto(client, dev_token)
    assert client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token)).status_code == 200
    e = db.get(Expense, g["id"])
    assert e.status == ExpenseStatus.submitted and json.loads(e.policy_flags)[0]["accion"] == "avisar"
    assert elegir_flujo(db, "expense", {"amount": 40, "policy_exceeded": True}).id == "wf-excede"
    assert elegir_flujo(db, "expense", {"amount": 40, "policy_exceeded": False}).id == "wf-normal"


def test_el_tope_diario_suma_los_gastos_del_dia_de_la_persona(client, admin_token, dev_token):
    _politica(client, admin_token, categoria="meals", limite_diario=60, accion="bloquear")
    _gasto(client, dev_token, amount=35)
    segundo = _gasto(client, dev_token, amount=30)
    otro_dia = _gasto(client, dev_token, amount=30, expense_date="2026-11-04")
    assert client.post(f"{URL}/my/{segundo['id']}/submit", headers=auth(dev_token)).status_code == 422
    assert client.post(f"{URL}/my/{otro_dia['id']}/submit", headers=auth(dev_token)).status_code == 200


def test_justificante_obligatorio_varios_adjuntos_y_solo_los_ve_quien_debe(client, db, admin_token, dev_token, hr_token):
    _politica(client, admin_token, justificante_desde=20, accion="bloquear")
    g = _gasto(client, dev_token)
    assert client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token)).status_code == 422
    ids = []
    for nombre in ("ticket.pdf", "factura.pdf"):
        r = client.post(f"{URL}/{g['id']}/attachments", headers=auth(dev_token),
                        files={"file": (nombre, b"%PDF-1.4 justificante", "application/pdf")})
        assert r.status_code == 200, r.text
        ids.append(r.json()["data"]["id"])
    lista = client.get(f"{URL}/{g['id']}/attachments", headers=auth(dev_token)).json()["data"]["items"]
    assert [a["filename"] for a in lista] == ["ticket.pdf", "factura.pdf"]
    assert client.get(f"{URL}/attachments/{ids[0]}/url", headers=auth(dev_token)).json()["data"]["url"]
    # Otra persona sin rol de gestión no ve el justificante.
    assert client.get(f"{URL}/attachments/{ids[0]}/url", headers=auth(hr_token)).status_code == 404
    assert client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token)).status_code == 200
    # Enviado: el dueño ya no quita justificantes.
    assert client.delete(f"{URL}/attachments/{ids[1]}", headers=auth(dev_token)).status_code == 409


def test_EL_HALLAZGO_el_reparto_suma_100_y_cada_proyecto_cuenta_su_parte(client, db, dev_token, admin_token, proyectos):
    g = _gasto(client, dev_token, amount=200, project_id="p-g1")
    r = client.put(f"{URL}/{g['id']}/allocations", headers=auth(dev_token),
                   json=[{"project_id": "p-g1", "percentage": 60}, {"project_id": "p-g2", "percentage": 30}])
    assert r.status_code == 400 and "suma 90" in r.json()["detail"]
    r = client.put(f"{URL}/{g['id']}/allocations", headers=auth(dev_token),
                   json=[{"project_id": "p-g1", "percentage": 60}, {"project_id": "p-g2", "percentage": 40}])
    assert r.status_code == 200
    e = db.get(Expense, g["id"])
    e.status = ExpenseStatus.reimbursed          # reembolsado sigue siendo coste
    sin_reparto = Expense(id=str(uuid.uuid4()), code="EXP-X", user_id=e.user_id, project_id="p-g2", category="other",
                          description="x", amount=10, expense_date=date(2026, 11, 3), status=ExpenseStatus.approved,
                          organization_id="1")
    db.add(sin_reparto)
    db.commit()
    from app.services.gastos_avanzados import totales_por_proyecto
    assert totales_por_proyecto(db, ["p-g1", "p-g2"]) == {"p-g1": 120.0, "p-g2": 90.0}
    resumen = client.get(f"{URL}/summary/p-g2", headers=auth(admin_token)).json()["data"]
    assert resumen["total"] == 90.0 and resumen["count"] == 2


def test_un_rechazado_se_corrige_y_se_vuelve_a_enviar(client, db, dev_token, pm_token):
    g = _gasto(client, dev_token)
    client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token))
    client.post(f"{URL}/{g['id']}/review", headers=auth(pm_token), json={"approved": False, "rejection_reason": "Falta ticket"})
    assert db.get(Expense, g["id"]).status == ExpenseStatus.rejected
    r = client.patch(f"{URL}/my/{g['id']}", headers=auth(dev_token), json={"notes": "Ticket adjunto"})
    assert r.status_code == 200 and db.get(Expense, g["id"]).status == ExpenseStatus.draft
    assert client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token)).status_code == 200
    db.expire_all()
    e = db.get(Expense, g["id"])
    assert e.status == ExpenseStatus.submitted and e.rejection_reason is None


def test_crear_un_borrador_no_dispara_el_evento_de_enviado(client, monkeypatch, dev_token):
    vistos = []
    import app.core.events as ev
    original = ev.emit
    monkeypatch.setattr(ev, "emit", lambda db, tipo, *a, **k: vistos.append(tipo) or original(db, tipo, *a, **k))
    g = _gasto(client, dev_token)
    assert ev.EventType.EXPENSE_SUBMITTED not in vistos
    client.post(f"{URL}/my/{g['id']}/submit", headers=auth(dev_token))
    assert vistos.count(ev.EventType.EXPENSE_SUBMITTED) == 1


def test_un_pdf_va_al_lector_como_documento(monkeypatch):
    import asyncio
    import io
    from app.core.config import settings
    from app.services import expense_service
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "k", raising=False)
    enviado = {}

    class _R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def falso(req, timeout=None):
        enviado.update(json.loads(req.data), timeout=timeout)
        return _R(json.dumps({"content": [{"text": json.dumps({"amount": 12.5, "currency": "EUR"})}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", falso)
    r = asyncio.run(expense_service.ocr_receipt(b"%PDF-1.4", "application/pdf"))
    bloque = enviado["messages"][0]["content"][0]
    assert bloque["type"] == "document" and bloque["source"]["media_type"] == "application/pdf"
    assert r["amount"] == 12.5 and enviado["timeout"] > 0


def test_sin_proyecto_el_selector_vacio_no_rompe(client, dev_token):
    """Medido en el navegador el 09-11-2026: «Sin proyecto» enviaba "" y crear el gasto daba 500."""
    g = _gasto(client, dev_token, project_id="", contract_id="")
    assert g["project_id"] is None
