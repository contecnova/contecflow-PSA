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


# ── Detalles de pantalla ──────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_historial_de_predicciones_trae_el_nombre_del_proyecto(db):
    from app.models.ml_model import MLPredictionLog
    from app.services.ml_trainer import get_prediction_logs
    p = _proyecto(db, code="LOG")
    db.add(MLPredictionLog(organization_id="1", project_id=p.id, used_heuristic=True,
                           predicted_at=datetime.now(timezone.utc)))
    db.commit()
    assert [x["project_name"] for x in get_prediction_logs(db, "1")] == [p.name]


def test_EL_HALLAZGO_los_proyectos_en_riesgo_traen_CPI_y_SPI(db, monkeypatch):
    from app.services import ml_trainer
    _proyecto(db, code="RSK")
    monkeypatch.setattr(ml_trainer, "predict_project", lambda *a, **k: {
        "risk_level": "high", "cpi": 0.71, "spi": 0.84, "cost_overrun_prob": 0.8, "schedule_overrun_prob": 0.6})
    fila = ml_trainer.portfolio_risk_summary(db, "1")["at_risk_projects"][0]
    assert (fila["cpi"], fila["spi"]) == (0.71, 0.84)


def test_EL_HALLAZGO_cada_anomalia_dice_de_que_mes_es(client, pm_token, monkeypatch):
    from app.services.bi_smart_alerts import metrics
    meses = [f"2026-{m:02d}" for m in range(1, 9)]
    monkeypatch.setattr(metrics, "serie_con_meses", lambda db, k, o: ([10, 11, 10, 12, 11, 10, 95, 11], meses))
    r = client.post("/api/v1/bi/anomaly/detect", headers=auth(pm_token), json={"metric": "revenue", "method": "zscore"})
    assert r.status_code == 200, r.text
    assert "2026-07" in [a["period"] for a in r.json()["data"]["anomalies"]]


def test_EL_HALLAZGO_la_ejecucion_en_streaming_queda_en_el_historial(db, monkeypatch):
    import contextlib
    from app.api.v1.endpoints.ai_chat import _guardando_ejecucion
    # Una segunda conexion a SQLite esperaria al cerrojo de la de la prueba.
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: contextlib.nullcontext(db))
    from app.services.ai_chat.agent_execution_service import list_agent_executions
    eventos = [b'data: {"type": "step"}\n\n', b'data: {"type": "done", "result": "Hecho", "steps": [1, 2]}\n\n']
    assert list(_guardando_ejecucion("resume el proyecto", _pm(db), iter(eventos))) == eventos
    db.expire_all()
    fila = list_agent_executions(db, "pm-test-id")[0]
    assert (fila["result"], fila["steps_count"], fila["status"]) == ("Hecho", 2, "done")


# ── Riesgo: datos medidos en vez de constantes ────────────────────────────────

def _imputar(db, proyecto, usuario, horas, dias_atras=3):
    from app.models.imputation import Imputation
    db.add(Imputation(user_id=usuario, project_id=proyecto.id, organization_id="1",
                      date=date.today() - timedelta(days=dias_atras), hours=horas))


def test_EL_HALLAZGO_la_carga_del_equipo_se_mide_y_no_es_un_85_fijo(db):
    from app.services.ml_features import carga_del_equipo
    p, otro = _proyecto(db, code="CRG"), _proyecto(db, code="CRG2")
    assert carga_del_equipo(db, p.id)["load_pct"] is None, "sin nadie imputando no hay carga que medir"
    _imputar(db, p, "dev-test-id", 100)      # 40 h/sem × 4 = 160 de capacidad
    _imputar(db, otro, "dev-test-id", 100)   # cuenta todo lo que hace la persona
    _imputar(db, p, "pm-test-id", 40)
    db.commit()
    c = carga_del_equipo(db, p.id)
    assert c == {"load_pct": 75.0, "overloaded_members": 1, "team_size": 2}


def test_EL_HALLAZGO_el_riesgo_de_presupuesto_usa_el_coste_real(db):
    from app.models.imputation import Imputation
    from app.services.cab_service import _risk_budget
    p = _proyecto(db, code="BGT", budget_amount=1000)
    db.add(Imputation(user_id="dev-test-id", project_id=p.id, organization_id="1",
                      date=date.today(), hours=10, cost_amount=1200))
    db.commit()
    # 10 h × 80 €/h = 800 € (80 %, sin riesgo); el coste real es 1.200 € (120 %).
    assert _risk_budget(db, p) == pytest.approx(40)


def test_EL_HALLAZGO_la_etiqueta_de_entrenamiento_compara_euros(db):
    from app.core.config import settings
    from app.models.task import Task
    from app.services.ml_features import extract_training_dataset
    p = _proyecto(db, code="LBL", budget_amount=1000, start_date=date(2026, 1, 1),
                  end_date_planned=date(2026, 6, 1))
    p.status = ProjectStatus.completed
    p.end_date_real = date(2026, 6, 1)
    db.add(Task(code="TSK-LBL", project_id=p.id, title="T", status="done", organization_id="1"))
    # 200 h sin `cost_amount`: antes se comparaban 200 «euros» con 1.100 y no
    # habia sobrecoste; en euros son 200 × tarifa, muy por encima.
    _imputar(db, p, "dev-test-id", 200)
    db.commit()
    assert 200 * settings.AI_REVENUE_HOURLY_RATE_FALLBACK > 1100
    _, y, ids = extract_training_dataset(db, "1")
    assert y[ids.index(p.id)] == 1


def test_EL_HALLAZGO_sin_datos_no_cuenta_como_riesgo_bajo(db, monkeypatch):
    from app.services import ml_trainer
    _proyecto(db, code="SND")
    monkeypatch.setattr(ml_trainer, "predict_project", lambda *a, **k: {"error": "Datos insuficientes"})
    r = ml_trainer.portfolio_risk_summary(db, "1")
    assert r["risk_counts"]["low"] == 0 and r["without_data"] >= 1


def test_EL_HALLAZGO_el_tiempo_de_espera_de_la_IA_es_un_ajuste(db, monkeypatch):
    import contextlib
    from app.services import settings_service
    from app.services.ai_provider_service import espera_de_ia
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: contextlib.nullcontext(db))
    assert espera_de_ia("AI_LOCAL_HTTP_TIMEOUT_SECONDS") == 120
    settings_service.set_runtime_value(db, "timeouts", "AI_LOCAL_HTTP_TIMEOUT_SECONDS", 300, None)
    db.commit()
    settings_service.invalidate_cache()
    assert espera_de_ia("AI_LOCAL_HTTP_TIMEOUT_SECONDS") == 300


def test_EL_HALLAZGO_los_pesos_del_riesgo_se_cambian_desde_admin(db):
    from app.services import settings_service
    from app.services.cab_service import compute_risk_score
    p = _proyecto(db, code="PES", start_date=date.today() - timedelta(days=50),
                  end_date_planned=date.today() + timedelta(days=50))
    from app.models.task import Task
    db.add(Task(code="TSK-PES", project_id=p.id, title="T", status="todo", organization_id="1"))
    db.commit()
    antes = compute_risk_score(db, p)
    assert antes["schedule_risk"] == pytest.approx(75, abs=1)   # 50 % de tiempo, 0 hecho, × 1,5
    settings_service.set_runtime_value(db, "risk", "RISK_WEIGHT_SCHEDULE", 1.0, None)
    settings_service.set_runtime_value(db, "risk", "RISK_LEVEL_CRITICAL", 90, None)
    settings_service.set_runtime_value(db, "risk", "RISK_LEVEL_HIGH", 70, None)
    db.commit()
    settings_service.invalidate_cache()
    despues = compute_risk_score(db, p)
    assert despues["overall_score"] == pytest.approx(despues["schedule_risk"], abs=0.1)
    assert despues["level"] == "high"


def test_EL_HALLAZGO_el_detalle_tiene_historial_y_no_escribe_en_cada_clic(db):
    from app.models.cab import ProjectRiskScore
    from app.services.cab_service import get_project_risk_score
    p = _proyecto(db, code="HIS")
    for _ in range(3):
        d = get_project_risk_score(p.id, db)
    assert db.query(ProjectRiskScore).filter(ProjectRiskScore.project_id == p.id).count() == 1
    previa = db.query(ProjectRiskScore).filter(ProjectRiskScore.project_id == p.id).one()
    previa.overall_score = 99   # una puntuacion anterior distinta, de hace una hora
    previa.computed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    d = get_project_risk_score(p.id, db)
    assert [h["overall_score"] for h in d["history"]] == [99]
    d = get_project_risk_score(p.id, db)
    assert [h["overall_score"] for h in d["history"]][0] == 99 and len(d["history"]) == 2


def test_EL_HALLAZGO_ver_la_cartera_no_repite_el_historial(db):
    from app.models.ml_model import MLPredictionLog
    from app.models.task import Task
    from app.services.ml_trainer import portfolio_risk_summary
    p = _proyecto(db, code="REP", budget_amount=1000)
    db.add(Task(code="TSK-REP", project_id=p.id, title="T", status="todo", organization_id="1"))
    db.commit()
    for _ in range(3):
        portfolio_risk_summary(db, "1")
    assert db.query(MLPredictionLog).filter(MLPredictionLog.project_id == p.id).count() == 1
