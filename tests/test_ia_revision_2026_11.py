"""IA, previsión y ML: lo que la revisión del 04-11-2026 encontró roto.

Medido contra una copia de la base con Ollama en local. Ninguna de estas rutas
tenía prueba, por eso todas pasaban la suite rotas.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from tests.conftest import auth


def _proyecto(db, code="IA1", **extra):
    p = Project(code=code, name=f"Proyecto {code}", status=ProjectStatus.active,
                project_type=ProjectType.development, organization_id="1", **extra)
    db.add(p)
    db.commit()
    return p


def _pm(db):
    return db.query(User).filter(User.id == "pm-test-id").one()


# ── Voz, triaje, reuniones, planificación ─────────────────────────────────────

def test_EL_HALLAZGO_el_comando_de_voz_no_da_500(db):
    from app.api.v1.endpoints.ai_modules import _process_voice_core
    r = _process_voice_core("crea una tarea revisar el contrato", db, _pm(db), confirm=False)
    assert isinstance(r, dict)


def test_EL_HALLAZGO_la_prioridad_del_triaje_se_traduce_a_la_del_ticket():
    from app.models.service_desk import TicketPriority
    from app.services.ai_planning_service import prioridad_de_ticket
    validas = {p.value for p in TicketPriority}
    for sugerida in ("critical", "high", "medium", "low"):
        assert prioridad_de_ticket(sugerida) in validas
    assert prioridad_de_ticket("p2_high") == "p2_high"


def test_EL_HALLAZGO_crear_tareas_desde_una_reunion_les_pone_codigo(db):
    from app.models.ai_chat import AIMeeting, AIMeetingAction
    from app.models.task import Task
    from app.services.ai_modules.meetings import create_tasks_from_meeting
    p = _proyecto(db)
    m = AIMeeting(project_id=p.id, title="Seguimiento", organization_id="1")
    db.add(m)
    db.flush()
    db.add(AIMeetingAction(meeting_id=m.id, description="Enviar el informe", organization_id="1"))
    db.commit()
    r = create_tasks_from_meeting(db, m.id, {}, _pm(db))
    assert r["tasks_created"] == 1
    t = db.query(Task).filter(Task.id == r["tasks"][0]["task_id"]).one()
    assert t.code and t.code.startswith("TSK")


def test_EL_HALLAZGO_la_planificacion_inteligente_devuelve_ids_de_tarea(db, monkeypatch):
    from app.models.task import Task
    from app.services.ai_modules import client_portal
    p = _proyecto(db)
    tareas = [Task(code=f"TSK-{i}", project_id=p.id, title=f"T{i}", status="todo", organization_id="1")
              for i in (1, 2)]
    db.add_all(tareas)
    db.commit()
    monkeypatch.setattr(client_portal, "call_ai_unified", lambda *a, **k: (
        '[{"task_id": 2, "suggested_start": "2026-11-10", "suggested_due": "2026-11-12", "rationale": "x"}]'))
    r = client_portal.smart_schedule(db, SimpleNamespace(project_id=p.id, max_tasks=10), _pm(db))
    assert [s["task_id"] for s in r["scheduled"]] == [tareas[1].id]


def test_EL_HALLAZGO_la_pista_del_asistente_RCA_lee_el_texto():
    from app.services.service_desk.rca_wizard_service import _texto
    assert _texto("causa probable") == "causa probable"
    assert _texto({"content": "x"}) == "x"
    assert _texto(None) == ""


# ── Embeddings, avisos de IA ──────────────────────────────────────────────────

def test_EL_HALLAZGO_el_embedding_TFIDF_ya_es_una_lista():
    from app.services.ai_modules._base import _a_lista
    assert _a_lista([0.1, 0.2]) == [0.1, 0.2]
    np = pytest.importorskip("numpy")
    assert _a_lista(np.array([1.0, 2.0])) == [1.0, 2.0]


def test_EL_HALLAZGO_sin_proveedor_es_un_aviso_y_no_una_respuesta(db, monkeypatch):
    from app.services import ai_provider_service as s
    assert s.es_aviso_de_ia(s.AVISO_SIN_PROVEEDOR)
    assert not s.es_aviso_de_ia("Una respuesta normal")
    from app.services.ai_modules import _base
    monkeypatch.setattr(_base, "call_claude", None, raising=False)
    monkeypatch.setattr(s, "call_ai", lambda *a, **k: s.AVISO_SIN_PROVEEDOR)
    with pytest.raises(RuntimeError):
        _base.call_ai_unified(db, [{"role": "user", "content": "hola"}])


def test_EL_HALLAZGO_el_modelo_semantico_cae_a_TFIDF_sin_red(monkeypatch):
    import sys
    from app.services import semantic_classifier as sc
    falso = SimpleNamespace(SentenceTransformer=lambda name: (_ for _ in ()).throw(OSError("sin red")))
    monkeypatch.setitem(sys.modules, "sentence_transformers", falso)
    monkeypatch.setattr(sc, "_MODEL_INSTANCE", None)
    modelo, transformer = sc._get_model_real("modelo-que-no-esta", backend_override="transformer")
    assert transformer is False and isinstance(modelo, sc.TFIDFEncoder)


def test_EL_HALLAZGO_ollama_respeta_temperatura_cero_y_cuenta_tokens(monkeypatch):
    from app.services import ai_provider_service as s
    enviado = {}

    def _post(url, json, timeout):
        enviado.update(json)
        return SimpleNamespace(status_code=200, json=lambda: {
            "message": {"content": "ok"}, "prompt_eval_count": 11, "eval_count": 7})
    monkeypatch.setattr(s.httpx, "post", _post)
    prov = SimpleNamespace(provider="ollama", default_model="llama3", max_tokens=100, temperature=0.0,
                           api_key="", api_base_url="http://localhost:11434")
    monkeypatch.setattr(s, "_validate_model", lambda *a: None)
    r = s.call_provider(prov, [{"role": "user", "content": "hola"}])
    assert enviado["options"]["temperature"] == 0.0
    assert (r["tokens_in"], r["tokens_out"]) == (11, 7)


# ── Datos: ingresos, valor ganado ─────────────────────────────────────────────

def test_EL_HALLAZGO_los_ingresos_cuentan_lo_facturado_sin_tarifa(db):
    from app.models.billing_reports import Invoice
    from app.services.bi_intelligence_service import _month_series
    p = _proyecto(db)
    hoy = date.today()
    db.add(Invoice(number="INV-IA-1", project_id=p.id, organization_id="1", client_name="C",
                   issue_date=hoy, status="sent", subtotal=1000, total=1210))
    db.add(Invoice(number="INV-IA-2", project_id=p.id, organization_id="1", client_name="C",
                   issue_date=hoy, status="draft", subtotal=500, total=605))
    db.commit()
    serie = _month_series(db, "1", months_history=2)
    assert serie[-1]["revenue"] == pytest.approx(1000)


def test_EL_HALLAZGO_el_valor_ganado_se_pondera_por_el_avance(db):
    from app.models.task import Task
    from app.services.ml_features import extract_project_features
    p = _proyecto(db, budget_amount=10000, start_date=date.today() - timedelta(days=10),
                  end_date_planned=date.today() + timedelta(days=10))
    # Recien empezado: todo en curso, nada terminado. Antes EV = 0 -> SPI 0 («critico»).
    db.add_all([Task(code=f"TSK-E{i}", project_id=p.id, title=f"T{i}", organization_id="1",
                     status="in_progress") for i in range(4)])
    db.commit()
    db.expire_all()
    f = extract_project_features(db, p.id)
    assert f["spi"] > 0


# ── Planificador ──────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_APScheduler_programa_la_analitica_y_el_ML(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    import app.main as m
    vistos = []

    class _Planificador(BackgroundScheduler):
        def __init__(self, *a, **k):
            super().__init__()

        def start(self, *a, **k):
            vistos.extend(j.id for j in self.get_jobs())
    monkeypatch.setattr("apscheduler.schedulers.background.BackgroundScheduler", _Planificador)
    m._arrancar_planificador(True, False)
    for tarea in ("olap_nightly_etl", "ml_model_retrain", "predictive_scan",
                  "predictive_model_eval_retrain", "bi_kpi_push", "bi_ml_retrain"):
        assert f"ml_{tarea}" in vistos


# ── Oracle ────────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_oracle_dice_si_esta_reconocida_y_de_quien_habla(client, pm_token, db):
    from app.models.ai_chat import AIPrediction
    p = _proyecto(db)
    pred = AIPrediction(prediction_type="project_delay", entity_type="project", entity_id=p.id,
                        probability=0.5, severity="medium", title="Riesgo", organization_id="1")
    db.add(pred)
    db.commit()
    h = auth(pm_token)
    assert client.post(f"/api/v1/oracle/predictions/{pred.id}/acknowledge", headers=h).status_code == 200
    fila = next(x for x in client.get("/api/v1/oracle/predictions", params={"only_unacked": False},
                                      headers=h).json()["items"] if x["id"] == pred.id)
    assert fila["is_acknowledged"] is True and fila["entity_name"] == p.name


def test_EL_HALLAZGO_oracle_usa_el_limite_SLA_de_la_prioridad(db):
    from app.models.service_desk import Ticket, TicketPriority
    from app.services.ai_modules.oracle import _oracle_sla_breach
    ahora = datetime.now(timezone.utc)
    t = SimpleNamespace(id="t1", number="INC-1", priority=TicketPriority.p1_critical,
                        created_at=ahora - timedelta(hours=3))
    alertas = _oracle_sla_breach(db, [t], ahora)
    from app.models.ai_chat import AIPrediction
    texto = next(o for o in db.new if isinstance(o, AIPrediction)).explanation
    assert "TicketPriority" not in texto and "critical" in texto
    assert alertas, "con el limite de «critical» un ticket de 3 h ya esta en riesgo"
    assert Ticket  # importado para el registro de modelos


# ── Escenarios ────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_escenarios_semana_ISO_roles_y_reservas(db):
    from app.models.bookings import ResourceBooking
    from app.models.mfa import ScenarioModel, ScenarioProject
    from app.services.scenarios_service import _semana_iso, compute_scenario
    assert _semana_iso(date(2026, 1, 1)) == "2026-W01"
    assert _semana_iso(date(2027, 1, 1)) == "2026-W53"
    lunes = date(2026, 11, 9)
    s = ScenarioModel(name="E", base_date=lunes, horizon_weeks=2, created_by="pm-test-id", organization_id="1")
    db.add(s)
    db.flush()
    db.add(ScenarioProject(scenario_id=s.id, name="Nuevo", start_date=lunes, end_date=lunes + timedelta(days=7),
                           total_hours=10, organization_id="1"))
    db.add(ResourceBooking(user_id="dev-test-id", start_date=lunes, end_date=lunes + timedelta(days=4),
                           hours_per_day=4, organization_id="1"))
    db.commit()
    r = compute_scenario(s.id, db)
    roles = {getattr(u.role, "value", u.role) for u in db.query(User).filter(User.is_active == True)}
    assert "admin" in roles, "el admin existe y no debe contar"
    assert r["team_size"] == db.query(User).filter(
        User.is_active == True, User.role.in_(["pm", "team_lead", "employee", "subcontractor"])).count()
    assert r["committed_hours"] == 20
    semana = next(c for c in r["capacity_timeline"] if c["week"] == "2026-W46")
    assert semana["demand"] == pytest.approx(30)


# ── Churn, voz del Service Desk, NexusAssist ──────────────────────────────────

def test_EL_HALLAZGO_churn_usa_los_nombres_del_modelo(client, pm_token):
    h = auth(pm_token)

    def prob(**f):
        r = client.post("/api/v1/bi/churn/predict", headers=h, json={"client_id": "c1", "features": f})
        assert r.status_code == 200, r.text
        return r.json()["data"]["churn_probability"]
    base = dict(tickets_last_30d=1, response_time_avg_h=2, nps_score=9, contract_renewal_days=300,
                support_escalations=0, last_login_days_ago=1, active_projects=3)
    # Solo cambian los dos campos que la version vieja ignoraba (leia otros nombres).
    malo = dict(base, last_login_days_ago=90, contract_renewal_days=5)
    assert prob(**malo) > prob(**base)


def test_EL_HALLAZGO_el_agente_de_voz_hace_urgente_lo_urgente_y_le_pone_organizacion(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk import voice_agent_service as v
    v._set_json(db, v._SESSIONS_KEY, "1", {"s1": {
        "intent": "incident", "caller_id": "+34600", "entities": {"urgency_words": ["urgente"]},
        "transcript": [{"speaker": "user", "text": "No funciona el servidor, es urgente"}]}})
    v.create_ticket_from_session(db, "1", "s1", "pm-test-id")
    t = db.query(Ticket).filter(Ticket.source == "voice_agent").one()
    assert getattr(t.priority, "value", t.priority) == "p1_critical"
    assert t.organization_id == "1"


def test_EL_HALLAZGO_el_asistente_sabe_que_proyecto_esta_viendo(db):
    from app.services.ai_chat.core_service import prepare_chat
    p = _proyecto(db, code="CTX")
    _, _, system = prepare_chat(db, None, "pm-test-id", "project", p.id, "¿como va este?", "{context}")
    assert p.name in system


def test_EL_HALLAZGO_el_editor_en_linea_no_llena_el_historial(db):
    from app.models.ai_chat import AIConversation
    from app.services.ai_chat.core_service import prepare_chat
    for texto in ("mejora esto", "y esto otro"):
        _, mensajes, _ = prepare_chat(db, None, "pm-test-id", "inline_editor", None, texto, "{context}")
        assert len(mensajes) == 1
    assert db.query(AIConversation).filter(AIConversation.context_type == "inline_editor").count() == 1
