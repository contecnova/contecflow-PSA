"""OLA de las colas: el tiempo interno que tiene cada cola con un ticket.

Auditoria 2026-11: no existia. El SLA mide al cliente; nada media cuanto
retenia cada cola un ticket antes de resolverlo o pasarlo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth
from tests.test_sd_avisos_y_sla import ORG, _eventos, _procesar, correos, gente  # noqa: F401

AHORA = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def continua(db):
    """Politica 24x7: las horas de OLA son horas de reloj."""
    from app.models.service_desk import SLAPolicy
    p = SLAPolicy(name="24x7", business_hours_only=False, organization_id=ORG)
    db.add(p)
    db.commit()
    return p


def _en_cola(db, gente, continua, horas_ola=4.0, **campos):
    """Un ticket que entro en la cola N1 hace 5 horas."""
    from app.models.service_desk import Ticket, TicketPriority, TicketType
    gente["grupo"].ola_hours = horas_ola
    t = Ticket(number=campos.pop("number", "INC-0300"), ticket_type=TicketType.incident, title="VPN",
               description="d", priority=TicketPriority.p2_high, organization_id=ORG,
               assigned_to_user_id=gente["agente"].id, assigned_group_id=gente["grupo"].id,
               sla_policy_id=continua.id, **campos)
    db.add(t)
    db.commit()
    t.group_assigned_at = AHORA - timedelta(hours=5)
    db.commit()
    return t


def test_entrar_en_una_cola_arranca_el_reloj_y_cambiar_de_cola_lo_reinicia(db, gente):
    from app.models.service_desk import AgentGroup, SupportLevel, Ticket, TicketType
    t = Ticket(number="INC-0301", ticket_type=TicketType.incident, title="t", description="d",
               organization_id=ORG, assigned_group_id=gente["grupo"].id, sla_pause_minutes=30)
    db.add(t)
    db.commit()
    assert t.group_assigned_at is not None and t.ola_pause_base == 30

    t.group_assigned_at, t.ola_breached = AHORA, True
    db.commit()
    db.add(AgentGroup(id="cola-n2", name="N2", support_level=SupportLevel.l2, organization_id=ORG))
    t.assigned_group_id = "cola-n2"
    db.commit()
    assert t.group_assigned_at.replace(tzinfo=timezone.utc) > AHORA and t.ola_breached is False, "la cola nueva empieza de cero"

    t.title = "otro titulo"
    sello = t.group_assigned_at
    db.commit()
    assert t.group_assigned_at == sello, "un cambio que no mueve de cola no toca el reloj"


def test_vencido_el_ola_avisa_una_vez_a_la_cola_que_lo_tenia(db, gente, continua, correos):
    from app.models.service_desk import SLAEvent
    from app.services.service_desk.sla_monitor_service import escanear
    t = _en_cola(db, gente, continua)
    _procesar(db)

    r = escanear(db, ahora=AHORA)
    db.refresh(t)
    assert r["ola_incumplidos"] == 1 and t.ola_breached
    assert t.ola_due.replace(tzinfo=timezone.utc) == AHORA - timedelta(hours=1)
    assert [e.sla_type for e in db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id)] == ["ola"]
    assert "ola_breached" in _eventos(db, t.id)

    escanear(db, ahora=AHORA + timedelta(minutes=5))
    assert db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id).count() == 1, "avisa cada pasada"

    correos.clear()
    _procesar(db)
    assert {c["para"] for c in correos} == {"agente@example.com", "lider@example.com"}
    assert all("N1" in c["asunto"] for c in correos)


def test_la_pausa_dentro_de_la_cola_no_cuenta(db, gente, continua):
    from app.services.service_desk.sla_monitor_service import escanear
    # 5 h en la cola, 2 de ellas esperando al cliente: lleva 3 de sus 4.
    t = _en_cola(db, gente, continua, sla_pause_minutes=150)
    t.ola_pause_base, t.sla_pause_minutes = 30, 150
    db.commit()
    assert escanear(db, ahora=AHORA)["ola_incumplidos"] == 0
    db.refresh(t)
    assert not t.ola_breached


def test_una_cola_sin_ola_no_vigila_nada(db, gente, continua):
    from app.services.service_desk.sla_monitor_service import escanear
    t = _en_cola(db, gente, continua, horas_ola=None)
    assert escanear(db, ahora=AHORA)["ola_incumplidos"] == 0
    db.refresh(t)
    assert t.ola_due is None and not t.ola_breached


def test_el_administrador_pone_y_quita_el_ola_de_la_cola(client, admin_token, db, gente):
    base = "/api/v1/sd/groups"
    cuerpo = {"name": "N1", "support_level": "l1"}
    assert client.patch(f"{base}/cola-n1", headers=auth(admin_token), json={**cuerpo, "ola_hours": 0}).status_code == 422
    assert client.patch(f"{base}/cola-n1", headers=auth(admin_token), json={**cuerpo, "ola_hours": 6}).status_code == 200
    grupos = {g["id"]: g for g in client.get(base, headers=auth(admin_token)).json()["items"]}
    assert grupos["cola-n1"]["ola_hours"] == 6
    client.patch(f"{base}/cola-n1", headers=auth(admin_token), json={**cuerpo, "ola_hours": None})
    db.expire_all()
    assert gente["grupo"].ola_hours is None
