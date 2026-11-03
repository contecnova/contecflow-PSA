"""UC: el plazo del proveedor mientras el ticket espera a un tercero.

Auditoria 2026-11: no existia. Los contratos de ALM no tenian plazo y nada
media cuanto tardaba un proveedor con un ticket que esperaba por el.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth
from tests.test_sd_avisos_y_sla import ORG, _eventos, _procesar, correos, gente  # noqa: F401

AHORA = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def proveedor(db):
    """Un proveedor con contrato de soporte de 4 horas y un servidor suyo en el CI."""
    from app.models.alm import ALMAsset, ALMContract, ALMVendor
    from app.models.service_desk import CIType, ConfigurationItem, SLAPolicy
    db.add(SLAPolicy(id="pol-24x7", name="24x7", business_hours_only=False, organization_id=ORG))
    db.add(ALMVendor(id="ven-1", name="Dell", organization_id=ORG))
    db.add(ALMContract(id="con-1", title="ProSupport", type="support", vendor_id="ven-1", status="active",
                       resolution_hours=4, organization_id=ORG))
    db.add(ConfigurationItem(id="ci-uc", code="CI-UC", name="srv", ci_type=CIType.server, organization_id=ORG))
    db.add(ALMAsset(id="act-uc", name="PowerEdge", type="server", vendor_id="ven-1", ci_id="ci-uc",
                    organization_id=ORG))
    db.commit()


def _esperando(db, gente, **campos):
    """Un ticket que lleva 5 horas esperando al proveedor."""
    from app.models.service_desk import Ticket, TicketPriority, TicketStatus, TicketType
    t = Ticket(number=campos.pop("number", "INC-0700"), ticket_type=TicketType.incident, title="Disco",
               description="d", priority=TicketPriority.p2_high, organization_id=ORG,
               assigned_to_user_id=gente["agente"].id, assigned_group_id=gente["grupo"].id,
               sla_policy_id="pol-24x7", ci_id="ci-uc", **campos)
    db.add(t)
    db.commit()
    t.status = TicketStatus.pending_third
    db.commit()
    assert t.uc_started_at is not None, "entrar en pendiente de tercero no arranca el reloj"
    t.uc_started_at = AHORA - timedelta(hours=5)
    db.commit()
    return t


def test_el_reloj_corre_solo_mientras_se_espera_al_tercero(db, gente, proveedor):
    from app.models.service_desk import TicketStatus
    t = _esperando(db, gente)
    t.status = TicketStatus.in_progress
    db.commit()
    assert t.uc_started_at is None and t.uc_due is None


def test_vencido_el_uc_avisa_una_vez_con_el_contrato_del_proveedor_del_ci(db, gente, proveedor, correos):
    from app.models.service_desk import SLAEvent
    from app.services.service_desk.sla_monitor_service import escanear
    t = _esperando(db, gente)
    _procesar(db)

    r = escanear(db, ahora=AHORA)
    db.refresh(t)
    assert r["uc_incumplidos"] == 1 and t.uc_breached
    assert t.uc_contract_id == "con-1", "no eligio el contrato del proveedor del activo del CI"
    assert t.uc_due.replace(tzinfo=timezone.utc) == AHORA - timedelta(hours=1)
    assert [e.sla_type for e in db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id)] == ["uc"]
    assert "uc_breached" in _eventos(db, t.id)

    escanear(db, ahora=AHORA + timedelta(minutes=5))
    assert db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id).count() == 1, "avisa cada pasada"

    correos.clear()
    _procesar(db)
    assert {c["para"] for c in correos} == {"agente@example.com", "lider@example.com"}
    assert all("Dell" in c["asunto"] for c in correos)


def test_la_pausa_del_sla_no_para_el_uc(db, gente, proveedor):
    """Esperar al tercero es justo lo que mide, aunque el SLA del cliente se pare."""
    from app.services.service_desk.sla_monitor_service import escanear
    t = _esperando(db, gente)
    t.sla_paused_at = AHORA - timedelta(hours=5)
    db.commit()
    assert escanear(db, ahora=AHORA)["uc_incumplidos"] == 1


def test_con_dos_contratos_posibles_no_elige_ninguno(db, gente, proveedor):
    from app.models.alm import ALMContract
    from app.services.service_desk.sla_monitor_service import escanear
    db.add(ALMContract(id="con-2", title="Garantía", type="maintenance", vendor_id="ven-1", status="active",
                       resolution_hours=48, organization_id=ORG))
    db.commit()
    t = _esperando(db, gente)
    assert escanear(db, ahora=AHORA)["uc_incumplidos"] == 0
    db.refresh(t)
    assert t.uc_contract_id is None and not t.uc_breached


def test_el_agente_elige_el_contrato_y_se_valida(db, client, admin_token, gente, proveedor):
    from app.models.alm import ALMContract
    t = _esperando(db, gente)
    h = auth(admin_token)
    db.add(ALMContract(id="sin-plazo", title="Compra", type="purchase", vendor_id="ven-1", status="active", organization_id=ORG))
    db.commit()
    url = f"/api/v1/sd/tickets/{t.id}"
    assert client.patch(url, headers=h, json={"uc_contract_id": "sin-plazo"}).status_code == 422
    assert client.patch(url, headers=h, json={"uc_contract_id": "con-1"}).status_code == 200
    datos = client.get(url, headers=h).json()["data"]
    assert datos["uc_contract_id"] == "con-1" and datos["uc_contract_name"] == "Dell · ProSupport"


def test_el_plazo_del_contrato_se_guarda_y_se_valida(client, admin_token):
    h = auth(admin_token)
    r = client.post("/api/v1/alm/contracts", headers=h, json={"title": "Soporte", "type": "support", "resolution_hours": "8"})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["id"]
    assert r.json()["data"]["resolution_hours"] == 8
    assert client.patch(f"/api/v1/alm/contracts/{cid}", headers=h, json={"resolution_hours": 0}).status_code == 422
    r = client.patch(f"/api/v1/alm/contracts/{cid}", headers=h, json={"resolution_hours": "", "total_value": ""})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["resolution_hours"] is None
