"""Avisos del ciclo de vida del ticket, calendario del SLA y escalado.

Auditoria 2026-11. El bucle de control del Service Desk estaba muerto:

* ningun cambio de ticket avisaba a nadie (ni campana, ni correo, ni webhook);
* el estado del SLA no se guardaba nunca, y las reglas de escalado preguntan
  por ese estado guardado, asi que no saltaban;
* el horario de la politica (`business_start/end/days`) no se leia: el SLA era
  siempre 08-18 de lunes a viernes en UTC;
* el historial guardaba «TicketStatus.resolved» en vez de «resolved».

Cada prueba planta el caso y mira la fila escrita, no la cola en memoria.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

ORG = "1"


@pytest.fixture()
def correos(monkeypatch):
    """Sustituye el envio SMTP y apunta lo que habria salido."""
    from app.services.service_desk import correo

    enviados: list[dict] = []

    def _enviar(db, org_id, para, asunto, html, texto, *, responder_a=None):
        enviados.append({"para": para, "asunto": asunto, "html": html, "responder_a": responder_a})
        return correo.ResultadoEnvio(True, message_id="<x@test>")

    monkeypatch.setattr(correo, "enviar", _enviar)
    return enviados


@pytest.fixture()
def gente(db):
    from app.models.service_desk import AgentGroup, AgentGroupMember, SupportLevel
    from app.models.user import User, UserRole, UserStatus

    def usuario(uid, nombre, **extra):
        u = User(id=uid, username=uid, email=f"{uid}@example.com", full_name=nombre,
                 role=UserRole.employee, status=UserStatus.active, is_active=True,
                 hashed_password="x", organization_id=ORG, **extra)
        db.add(u)
        return u

    jefa = usuario("jefa", "Jefa de Soporte")
    agente = usuario("agente", "Agente Uno", manager_id="jefa")
    lider = usuario("lider", "Lider de Cola")
    grupo = AgentGroup(id="cola-n1", name="N1", support_level=SupportLevel.l1, organization_id=ORG)
    db.add(grupo)
    db.flush()
    db.add_all([
        AgentGroupMember(group_id=grupo.id, user_id=agente.id, organization_id=ORG),
        AgentGroupMember(group_id=grupo.id, user_id=lider.id, is_lead=True, organization_id=ORG),
    ])
    db.commit()
    return {"jefa": jefa, "agente": agente, "lider": lider, "grupo": grupo}


def _ticket(db, **campos):
    from app.models.service_desk import Ticket, TicketPriority, TicketType

    base = dict(
        number=f"INC-{len(campos) + 1:04d}", ticket_type=TicketType.incident,
        title="La VPN no conecta", description="Desde esta mañana",
        priority=TicketPriority.p2_high, organization_id=ORG,
        requester_name="Cliente Externo", requester_email="cliente@example.com",
    )
    base.update(campos)
    t = Ticket(**base)
    db.add(t)
    db.commit()
    return t


def _eventos(db, ticket_id):
    from app.models.service_desk import TicketEvent
    return [e.kind for e in db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at).all()]


def _avisos(db, user_id):
    from app.models.enterprise import Notification
    return db.query(Notification).filter(Notification.user_id == user_id).all()


def _procesar(db):
    from app.services.service_desk.ticket_event_processor import procesar_pendientes
    return procesar_pendientes(db)


# ── La bandeja de eventos ────────────────────────────────────────────────────

def test_cada_cambio_de_ticket_deja_su_evento_en_la_misma_transaccion(db, gente):
    from app.models.service_desk import TicketComment, TicketStatus

    t = _ticket(db, number="INC-0101")
    assert _eventos(db, t.id) == ["created"]

    t.assigned_to_user_id = gente["agente"].id
    t.status = TicketStatus.in_progress
    db.add(TicketComment(ticket_id=t.id, body="Mirando", is_public=True,
                         author_user_id=gente["agente"].id, organization_id=ORG))
    db.commit()
    assert sorted(_eventos(db, t.id)) == ["assigned", "commented", "created", "status_changed"]

    db.rollback()
    t.priority = "p1_critical"
    db.rollback()  # un cambio deshecho no deja evento
    assert "priority_changed" not in _eventos(db, t.id)


def test_crear_avisa_al_solicitante_por_correo_y_al_agente_en_la_campana(db, gente, correos):
    t = _ticket(db, number="INC-0102", assigned_to_user_id=gente["agente"].id)
    r = _procesar(db)
    assert r == {"procesados": 1, "fallidos": 0}

    destinos = {c["para"]: c for c in correos}
    assert "cliente@example.com" in destinos, "el solicitante no recibio acuse"
    assert "[INC-0102]" in destinos["cliente@example.com"]["asunto"], (
        "sin el numero entre corchetes la respuesta del cliente abriria otro ticket")
    assert "agente@example.com" in destinos

    avisos = _avisos(db, gente["agente"].id)
    assert len(avisos) == 1 and avisos[0].resource_id == t.id
    assert avisos[0].action_url == f"/service-desk?ticket={t.id}"

    from app.models.cab import EmailLog
    assert db.query(EmailLog).filter(EmailLog.source_id == t.id, EmailLog.status == "sent").count() == 2

    from app.models.service_desk import TicketEvent
    assert db.query(TicketEvent).filter(TicketEvent.processed_at.is_(None)).count() == 0


def test_un_comentario_interno_nunca_llega_al_solicitante(db, gente, correos):
    from app.models.service_desk import TicketComment

    t = _ticket(db, number="INC-0103", assigned_to_user_id=gente["agente"].id)
    _procesar(db)
    correos.clear()
    db.add(TicketComment(ticket_id=t.id, body="Nota interna: es el firewall", is_public=False,
                         author_user_id=gente["lider"].id, organization_id=ORG))
    db.commit()
    _procesar(db)
    assert [c["para"] for c in correos] == ["agente@example.com"]


def test_quien_hace_el_cambio_no_recibe_aviso_de_su_propio_cambio(db, gente, correos):
    from app.models.service_desk import TicketComment

    t = _ticket(db, number="INC-0104", assigned_to_user_id=gente["agente"].id)
    _procesar(db)
    correos.clear()
    antes = len(_avisos(db, gente["agente"].id))
    db.add(TicketComment(ticket_id=t.id, body="Ya está resuelto", is_public=True,
                         author_user_id=gente["agente"].id, organization_id=ORG))
    db.commit()
    _procesar(db)
    assert len(_avisos(db, gente["agente"].id)) == antes
    assert [c["para"] for c in correos] == ["cliente@example.com"]
    assert "Ya está resuelto" in correos[0]["html"]


def test_el_texto_del_cliente_se_escapa_en_el_correo(db, gente, correos):
    _ticket(db, number="INC-0105", title="<script>alert(1)</script>")
    _procesar(db)
    cuerpo = next(c["html"] for c in correos if c["para"] == "cliente@example.com")
    assert "<script>" not in cuerpo and "&lt;script&gt;" in cuerpo


def test_una_plantilla_inactiva_de_la_organizacion_apaga_ese_aviso(db, gente, correos):
    from app.models.cab import EmailTemplate

    db.add(EmailTemplate(name="Sin acuse", subject="-", body_html="-", code="sd.created.requester",
                         is_active=False, organization_id=ORG))
    db.commit()
    _ticket(db, number="INC-0106")
    _procesar(db)
    assert "cliente@example.com" not in [c["para"] for c in correos]


def test_una_plantilla_personalizada_sustituye_al_texto_por_defecto(db, gente, correos):
    from app.models.cab import EmailTemplate

    db.add(EmailTemplate(name="Acuse propio", subject="Recibido {{ticket_title}}",
                         body_html="<p>Gracias, {{requester_name}}</p>", code="sd.created.requester",
                         organization_id=ORG))
    db.commit()
    _ticket(db, number="INC-0107")
    _procesar(db)
    c = next(c for c in correos if c["para"] == "cliente@example.com")
    assert c["asunto"] == "[INC-0107] Recibido La VPN no conecta"
    assert c["html"] == "<p>Gracias, Cliente Externo</p>"


def test_un_evento_que_falla_se_reintenta_y_deja_su_error(db, gente, monkeypatch):
    from app.models.service_desk import TicketEvent
    from app.services.service_desk import ticket_event_processor as proc

    _ticket(db, number="INC-0108")

    def _rompe(*a, **k):
        raise RuntimeError("smtp caido")
    monkeypatch.setattr(proc, "_avisar", _rompe)
    assert _procesar(db) == {"procesados": 0, "fallidos": 1}
    ev = db.query(TicketEvent).one()
    assert ev.processed_at is None and ev.attempts == 1 and "smtp caido" in ev.last_error


def test_el_webhook_sale_con_la_organizacion_del_evento(db, gente, monkeypatch):
    import app.services.webhooks as wh

    vistos = []
    monkeypatch.setattr(wh, "fire_webhook",
                        lambda db, event, payload, project_id=None: vistos.append((event, db.info.get("organization_id"))) or 0)
    _ticket(db, number="INC-0109")
    _procesar(db)
    assert vistos == [("ticket.created", ORG)]


# ── El historial ─────────────────────────────────────────────────────────────

def test_el_historial_guarda_el_valor_del_enum_y_no_su_nombre(db, gente):
    from app.models.service_desk import TicketHistory, TicketStatus
    from app.services.sla_service import log_history

    t = _ticket(db, number="INC-0110")
    log_history(db, t.id, "status", TicketStatus.resolved, "in_progress")
    db.commit()
    h = db.query(TicketHistory).filter(TicketHistory.ticket_id == t.id).one()
    assert (h.old_value, h.new_value) == ("resolved", "in_progress")


# ── El calendario del SLA ────────────────────────────────────────────────────

def _cal(**kw):
    from app.services.sla_service import CalendarioSLA
    return CalendarioSLA(zona=ZoneInfo(kw.pop("zona", "Europe/Madrid")), **kw)


def test_la_jornada_se_cuenta_en_la_zona_de_la_politica():
    from datetime import time
    from app.services.sla_service import sumar_horas_sla

    cal = _cal(inicio=time(9), fin=time(18))
    # Lunes 10-03-2026 a las 08:00 UTC son las 09:00 en Madrid: 2 h llevan a las 11:00.
    fin = sumar_horas_sla(datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc), 2, cal)
    assert fin == datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc)


def test_los_dias_laborables_de_la_politica_mandan():
    from datetime import time
    from app.services.sla_service import sumar_horas_sla

    sabados = _cal(zona="UTC", inicio=time(8), fin=time(18), dias=frozenset({6}))
    # Viernes 13-03-2026 a mediodia: la primera hora laborable es el sabado a las 08:00.
    fin = sumar_horas_sla(datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc), 1, sabados)
    assert fin == datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)


def test_una_politica_24x7_suma_horas_de_reloj():
    from app.services.sla_service import sumar_horas_sla

    fin = sumar_horas_sla(datetime(2026, 3, 14, 23, 0, tzinfo=timezone.utc), 4, _cal(continuo=True))
    assert fin == datetime(2026, 3, 15, 3, 0, tzinfo=timezone.utc)


def test_los_festivos_sin_politica_cuentan_para_toda_la_organizacion(db):
    from app.models.service_desk import SDSLAHoliday
    from app.services.sla_service import calendario_sla

    db.add(SDSLAHoliday(name="Fiesta local", holiday_date="2026-03-19", organization_id=ORG))
    db.commit()
    cal = calendario_sla(db, None, ORG)
    assert date(2026, 3, 19) in cal.festivos


def test_la_politica_se_lee_entera(db):
    from app.models.service_desk import SLAPolicy
    from app.services.sla_service import calendario_sla

    p = SLAPolicy(name="Soporte EEUU", business_start=7, business_end=15,
                  business_days="1,2,3,4", timezone="America/New_York", organization_id=ORG)
    db.add(p)
    db.commit()
    cal = calendario_sla(db, p)
    assert (cal.inicio.hour, cal.fin.hour, cal.dias, str(cal.zona)) == (7, 15, frozenset({1, 2, 3, 4}), "America/New_York")


def test_en_riesgo_se_mide_en_horas_de_calendario_y_no_de_reloj():
    from datetime import time
    from app.services.sla_service import estado_sla

    cal = _cal(zona="UTC", inicio=time(8), fin=time(18))
    abierto = datetime(2026, 3, 13, 17, 0, tzinfo=timezone.utc)   # viernes, queda 1 h de jornada
    vence = datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc)     # 4 h laborables: lunes 11:00
    domingo = datetime(2026, 3, 15, 20, 0, tzinfo=timezone.utc)
    lunes = datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc)
    assert estado_sla(abierto, vence, 0, cal, 0.7, domingo) == "ok"
    assert estado_sla(abierto, vence, 0, cal, 0.7, lunes) == "at_risk"
    assert estado_sla(abierto, vence, 0, cal, 0.7, vence + timedelta(minutes=1)) == "breached"


# ── El escaneo y el escalado ─────────────────────────────────────────────────

def test_el_escaneo_guarda_el_estado_y_avisa_una_vez_por_transicion(db, gente, correos):
    from app.models.service_desk import SLAEvent
    from app.services.service_desk.sla_monitor_service import escanear

    ahora = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    t = _ticket(db, number="INC-0120", assigned_to_user_id=gente["agente"].id,
                assigned_group_id=gente["grupo"].id,
                created_at=ahora - timedelta(hours=30),
                sla_resolution_due=ahora - timedelta(hours=1))
    _procesar(db)
    escanear(db, ahora=ahora)
    db.refresh(t)
    assert t.sla_resolution_status.value == "breached" and t.sla_resolution_breached
    assert [e.event_type.value for e in db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id)] == ["breached"]

    escanear(db, ahora=ahora + timedelta(minutes=5))
    assert db.query(SLAEvent).filter(SLAEvent.ticket_id == t.id).count() == 1, "avisa cada pasada"

    correos.clear()
    _procesar(db)
    assert {c["para"] for c in correos} == {"agente@example.com", "lider@example.com"}


def test_una_regla_de_escalado_avisa_al_jefe_una_sola_vez(db, gente, correos):
    from app.models.service_desk import EscalationAction, EscalationLog, EscalationRule, EscalationTrigger
    from app.services.service_desk.sla_monitor_service import escanear

    db.add(EscalationRule(name="SLA roto al jefe", trigger=EscalationTrigger.sla_breached,
                          action=EscalationAction.notify_manager, organization_id=ORG))
    db.add(EscalationRule(name="De otra organizacion", trigger=EscalationTrigger.sla_breached,
                          action=EscalationAction.notify_manager, organization_id="otra"))
    ahora = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    _ticket(db, number="INC-0121", assigned_to_user_id=gente["agente"].id,
            created_at=ahora - timedelta(hours=30), sla_resolution_due=ahora - timedelta(hours=1))
    _procesar(db)
    r = escanear(db, ahora=ahora)
    assert r["escalados"] == 1, "la regla de la otra organizacion no puede tocar este ticket"
    escanear(db, ahora=ahora + timedelta(hours=2))
    assert db.query(EscalationLog).count() == 1, "un SLA incumplido no escala cada hora"

    correos.clear()
    _procesar(db)
    assert "jefa@example.com" in [c["para"] for c in correos]


def test_la_regla_de_reapertura_salta(db, gente):
    from app.models.service_desk import EscalationAction, EscalationLog, EscalationRule, EscalationTrigger
    from app.services.service_desk.escalation_service import run_escalation_rules_engine
    from app.services.sla_service import log_history

    db.add(EscalationRule(name="Reabierto sube", trigger=EscalationTrigger.reopened,
                          action=EscalationAction.elevate_priority, target_priority="p1_critical",
                          organization_id=ORG))
    t = _ticket(db, number="INC-0122", status="in_progress")
    log_history(db, t.id, "status", "resolved", "in_progress")
    db.commit()
    run_escalation_rules_engine(db)
    db.commit()
    db.refresh(t)
    assert t.priority.value == "p1_critical"
    assert db.query(EscalationLog).count() == 1


# ── Flujos que arrancan solos ────────────────────────────────────────────────

def _flujo(db, disparador, condicion, estado):
    from app.models.workflow_designer import (
        WorkflowBlueprint, WorkflowBlueprintStatus, WorkflowBlueprintVersion,
    )
    bp = WorkflowBlueprint(name="P1 a curso", process_type="ticket",
                           status=WorkflowBlueprintStatus.published, organization_id=ORG)
    db.add(bp)
    db.flush()
    grafo = {
        "nodes": [
            {"id": "s", "type": "start", "config": {"trigger": disparador, "condition": condicion}},
            {"id": "e1", "type": "state", "config": {"status": estado}},
            {"id": "f", "type": "end"},
        ],
        "edges": [{"source": "s", "target": "e1"}, {"source": "e1", "target": "f"}],
    }
    db.add(WorkflowBlueprintVersion(blueprint_id=bp.id, version=1, graph_json=json.dumps(grafo),
                                    is_published=True, organization_id=ORG))
    db.commit()
    return bp


def test_un_flujo_con_disparador_arranca_y_mueve_el_ticket(db, gente):
    from app.models.workflow_designer import WorkflowRun

    _flujo(db, "created", "priority == p1_critical", "in_progress")
    p1 = _ticket(db, number="INC-0130", priority="p1_critical")
    p3 = _ticket(db, number="INC-0131", priority="p3_medium")
    _procesar(db)
    db.refresh(p1)
    db.refresh(p3)
    assert p1.status.value == "in_progress" and p1.first_response_at is not None
    assert p3.status.value == "new", "la condicion no se cumplia"
    assert db.query(WorkflowRun).count() == 1


def test_un_flujo_que_cambia_el_estado_no_se_dispara_a_si_mismo(db, gente):
    from app.models.workflow_designer import WorkflowRun

    _flujo(db, "status_changed", "", "pending_third")
    t = _ticket(db, number="INC-0132")
    t.status = "in_progress"
    db.commit()
    for _ in range(3):
        _procesar(db)
    assert db.query(WorkflowRun).count() == 1
