"""Lo traído de contecmind y contecintelligence (23-11-2026, migración 207).

Cubre lo crítico de cada punto del encargo:
- motor semántico: corregir una asignación (sin el `manager_confirm:<uuid>` en una
  columna de 36), rechazo al reasignar (también si ya estaba confirmada), caché del
  historial al cerrar, veredicto decidido por el servidor, cola de casos dudosos y
  aislamiento por empresa;
- fichas del conector de contecmind para lecciones, gastos y presupuestos;
- anomalías de una métrica certificada y el token incrustable (solo con origen permitido);
- preguntas sin respuesta → tarea → cierre al publicar el artículo;
- memoria de conversación de Ask-the-Data, borrado, aislamiento y supresión RGPD.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.db.contexto_de_tenant import con_empresa
from app.models.semantic_engine import SemAssignment, SemEmbeddingCache, SemFeedback
from app.models.service_desk.tickets import Ticket
from app.models.user import User, UserRole, UserStatus
from tests.conftest import HASH_DE_PRUEBA, auth

ORG = "1"
OTRA = "org-otra-207"


# ── Utilidades ────────────────────────────────────────────────────────────────

def _usuario(db, uid, org, rol=UserRole.employee):
    u = User(id=uid, username=uid, email=f"{uid}@x.test", full_name=uid.upper(), role=rol,
             status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id=org,
             weekly_capacity_hours=40.0, currency="EUR")
    db.add(u)
    db.flush()
    return u


def _otra_empresa(db):
    from app.models.mfa import Organization
    if db.get(Organization, OTRA) is None:
        db.add(Organization(id=OTRA, name="Otra", slug="otra-207"))
        db.flush()


def _ticket(db, tid="t-207", org=ORG, asignado=None):
    t = Ticket(id=tid, number=f"INC-{tid}", ticket_type="incident", title="La VPN no conecta",
               description="Desde casa no entra", organization_id=org, assigned_to_user_id=asignado)
    db.add(t)
    db.flush()
    return t


def _proyecto(db, pid="p-207", org=ORG):
    from app.models.project import Project, ProjectStatus, ProjectType
    db.add(Project(id=pid, code=f"PRJ-{pid}", name="Proyecto 207", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id=org))
    db.flush()
    return pid


def _sugerencia(uid, conf=0.4):
    return {"suggested_user_id": uid, "confidence": conf, "engine_mode": "semantic", "top_scores": {uid: conf},
            "needs_review": conf < 0.5, "reasoning": "prueba"}


# ── Motor semántico: bucle de aprendizaje ────────────────────────────────────

def test_corregir_asignacion_guarda_el_id_y_el_tipo_no_el_texto_de_52(db):
    from app.services import semantic_engine_service as svc
    _usuario(db, "ana-207", ORG)
    _usuario(db, "luis-207", ORG)
    t = _ticket(db, asignado="ana-207")
    svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t.id, item_title=t.title,
                                        sugerencia=_sugerencia("ana-207"))
    db.commit()
    jefe = db.get(User, "admin-test-id")
    with con_empresa(db, ORG):
        r = svc.corregir_asignacion(db, jefe, {"item_type": "ticket", "item_id": t.id, "correct_user_id": "luis-207",
                                               "original_engine_mode": "llm", "confirmed": True})
    assert r["correction_kind"] == "correccion" and r["was_accepted"] is False
    fb = db.query(SemFeedback).one()
    assert fb.corrected_by == "admin-test-id" and len(fb.corrected_by) <= 36
    assert fb.correction_kind == "correccion" and fb.correct_user_id == "luis-207"
    sa = db.query(SemAssignment).one()
    assert sa.was_accepted is False and sa.accepted_user_id == "luis-207"
    # La persona correcta entra en el historial del nivel 3 y la corrección queda auditada.
    assert db.query(SemEmbeddingCache).filter(SemEmbeddingCache.assigned_user_id == "luis-207").count() == 1
    from app.models.enterprise import AuditLog
    assert db.query(AuditLog).filter(AuditLog.resource == "sem_assignment").count() == 1


def test_confirmar_una_propuesta_del_modelo_de_lenguaje(db):
    from app.services import semantic_engine_service as svc
    _usuario(db, "ana-207", ORG)
    t = _ticket(db, asignado="ana-207")
    svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t.id, item_title=t.title,
                                        sugerencia={**_sugerencia("ana-207"), "engine_mode": "llm"})
    db.commit()
    with con_empresa(db, ORG):
        r = svc.corregir_asignacion(db, db.get(User, "admin-test-id"),
                                    {"item_type": "ticket", "item_id": t.id, "correct_user_id": "ana-207",
                                     "original_engine_mode": "llm", "confirmed": True})
    assert r == {"ok": True, "persisted_as_expert": True, "correction_kind": "confirmacion_responsable",
                 "was_accepted": True}
    assert db.query(SemFeedback).one().corrected_by == "admin-test-id"


def test_corregir_con_una_persona_de_otra_empresa_es_no_encontrado(db):
    from app.core.errores import ErrorDeDominio
    from app.services import semantic_engine_service as svc
    _otra_empresa(db)
    _usuario(db, "ajeno-207", OTRA)
    t = _ticket(db)
    db.commit()
    with con_empresa(db, ORG), pytest.raises(ErrorDeDominio) as e:
        svc.corregir_asignacion(db, db.get(User, "admin-test-id"),
                                {"item_type": "ticket", "item_id": t.id, "correct_user_id": "ajeno-207"})
    assert e.value.status_code == 404
    assert db.query(SemFeedback).count() == 0


def test_reasignar_rechaza_aunque_ya_estuviera_confirmada_y_volver_a_la_sugerida_no(db):
    from app.services import semantic_engine_service as svc
    t = _ticket(db, asignado="dev-test-id")
    sa = svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t.id, item_title=t.title,
                                             sugerencia=_sugerencia("dev-test-id"))
    db.commit()
    # Volver a la sugerida: ni rechaza ni confirma.
    assert svc.resolver_por_reasignacion(db, "ticket", t.id, "dev-test-id") is None
    assert sa.was_accepted is None
    # Ya confirmada (True) y luego reasignada a otra persona: pasa a False.
    sa.was_accepted = True
    db.commit()
    assert svc.resolver_por_reasignacion(db, "ticket", t.id, "pm-test-id") is False
    db.commit()
    db.refresh(sa)
    assert sa.was_accepted is False and sa.accepted_user_id == "pm-test-id"


def test_cerrar_guarda_el_historial_y_decide_el_veredicto(db):
    from app.services import semantic_engine_service as svc
    t1 = _ticket(db, "t-207a", asignado="dev-test-id")
    t2 = _ticket(db, "t-207b", asignado="pm-test-id")
    for t in (t1, t2):
        svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t.id, item_title=t.title,
                                            sugerencia=_sugerencia("dev-test-id"))
    db.commit()
    with con_empresa(db, ORG):
        r1 = svc.cerrar_item(db, "ticket", t1.id, texto="La VPN no conecta desde casa", user_id="dev-test-id")
        r2 = svc.cerrar_item(db, "ticket", t2.id, texto="La impresora no imprime", user_id="pm-test-id")
        db.commit()
    assert r1 == {"historial": True, "veredicto": True} and r2 == {"historial": True, "veredicto": False}
    cache = {c.item_id: c.assigned_user_id for c in db.query(SemEmbeddingCache).all()}
    assert cache == {t1.id: "dev-test-id", t2.id: "pm-test-id"}
    assert all(c.organization_id == ORG for c in db.query(SemEmbeddingCache).all())
    # El historial del nivel 3 ya devuelve algo para esa persona.
    hist = svc.get_assigner(db)._get_history_embeddings("dev-test-id", "ticket")
    assert len(hist) == 1


def test_la_precision_cuenta_aceptadas_y_rechazadas_reales(db):
    from app.services import semantic_engine_service as svc
    for i, (quien, cierra) in enumerate((("dev-test-id", "dev-test-id"), ("dev-test-id", "pm-test-id"),
                                         ("dev-test-id", None))):
        t = _ticket(db, f"t-207p{i}", asignado=quien)
        svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t.id, item_title=t.title,
                                            sugerencia=_sugerencia(quien))
        db.commit()
        if cierra:
            svc.cerrar_item(db, "ticket", t.id, texto=f"texto {i}", user_id=cierra)
            db.commit()
    s = svc.get_stats(db)
    assert (s["accepted"], s["rejected"], s["pending"], s["accuracy_pct"], s["resolved"]) == (1, 1, 1, 50, 2)


def test_registrar_asignacion_el_veredicto_lo_pone_el_servidor(client, db, pm_token):
    from app.models.task import Task
    pid = _proyecto(db)
    db.add(Task(id="tk-207", code="TSK-207", title="Montar VPN", project_id=pid, organization_id=ORG))
    db.commit()
    base = {"item_type": "task", "item_id": "tk-207", "suggested_user_id": "dev-test-id", "was_accepted": True}
    r = client.post("/api/v1/semantic/record-assignment", headers=auth(pm_token), json=base)
    assert r.status_code == 200
    r = client.post("/api/v1/semantic/record-assignment", headers=auth(pm_token),
                    json={**base, "accepted_user_id": "pm-test-id"})
    assert r.status_code == 200
    estados = [a.was_accepted for a in db.query(SemAssignment).order_by(SemAssignment.created_at).all()]
    assert sorted(estados, key=lambda v: str(v)) == [False, None]   # nunca el True que manda el cliente
    # Un elemento que no existe (o de otra empresa) no deja rastro.
    r = client.post("/api/v1/semantic/record-assignment", headers=auth(pm_token), json={**base, "item_id": "nada"})
    assert r.status_code == 404


def test_el_alta_de_ticket_con_autoasignacion_registra_la_sugerencia_pendiente(db, monkeypatch):
    from app.services.service_desk import ticket_creation_service as tcs
    t = _ticket(db, "t-207auto")
    t._sugerencia_semantica = _sugerencia("dev-test-id")
    t.assigned_to_user_id = "dev-test-id"
    tcs._registrar_sugerencia_semantica(db, t)
    db.commit()
    sa = db.query(SemAssignment).one()
    assert (sa.item_id, sa.suggested_user_id, sa.was_accepted) == ("t-207auto", "dev-test-id", None)


def test_cola_de_casos_dudosos_ordena_y_no_cruza_empresas(db):
    from app.services import semantic_engine_service as svc
    _otra_empresa(db)
    t_poca = _ticket(db, "t-207q1")
    t_mucha = _ticket(db, "t-207q2")
    t_ajeno = _ticket(db, "t-207q3", org=OTRA)
    svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t_poca.id, item_title="a",
                                        sugerencia=_sugerencia("dev-test-id", 0.2))
    svc.registrar_sugerencia_automatica(db, item_type="ticket", item_id=t_mucha.id, item_title="b",
                                        sugerencia=_sugerencia("dev-test-id", 0.95))
    db.add(SemAssignment(item_type="ticket", item_id=t_ajeno.id, item_title="ajeno", organization_id=OTRA,
                         suggested_user_id="dev-test-id", confidence=0.1))
    db.commit()
    with con_empresa(db, ORG):
        cola = svc.cola_de_revision(db, 10)
    assert [c["item_id"] for c in cola] == [t_poca.id, t_mucha.id]
    assert cola[0]["priority_score"] > cola[1]["priority_score"]


def test_toca_reentrenar_segun_el_intervalo():
    from app.services.semantic_engine_service import toca_reentrenar
    medianoche = datetime(2026, 11, 23, 0, 23, tzinfo=timezone.utc)
    una = datetime(2026, 11, 23, 1, 23, tzinfo=timezone.utc)
    assert toca_reentrenar(24, medianoche) and not toca_reentrenar(24, una)
    assert toca_reentrenar(1, una) and not toca_reentrenar(0, medianoche)


def test_no_queda_el_nombre_del_cliente_en_el_codigo():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    for ruta in ("app/models/semantic_engine.py", "app/services/semantic_classifier.py",
                 "app/services/semantic_engine_service.py"):
        assert "ficosa" not in (raiz / ruta).read_text(encoding="utf-8").lower(), ruta


# ── Fichas del conector de contecmind ────────────────────────────────────────

def test_lecciones_gastos_y_presupuestos_son_fichas_con_su_control_de_acceso(db):
    from app.core.errores import ErrorDeDominio
    from app.models.expenses import Expense
    from app.services.conectores import fichas
    assert {"lesson", "expense", "budget"} <= set(fichas.FICHAS)
    gasto = Expense(id="g-207", code="EXP-0207", user_id="dev-test-id", description="Taxi", amount=12,
                    currency="EUR", category="travel", organization_id=ORG,
                    expense_date=datetime(2026, 11, 20).date())
    db.add(gasto)
    db.commit()
    dev = db.get(User, "dev-test-id")
    otro = _usuario(db, "otro-207", ORG)
    f, g = fichas.cargar(db, dev, "expense", "g-207")
    assert f.nombre(g) == "EXP-0207 — Taxi"
    # Un empleado que no es el dueño ni gestiona gastos: 404, como en la pantalla del gasto.
    with pytest.raises(ErrorDeDominio):
        fichas.cargar(db, otro, "expense", "g-207")
    # Presupuestos: solo quien los gestiona.
    with pytest.raises(ErrorDeDominio):
        fichas.cargar(db, dev, "budget", "cualquiera")


def test_la_ficha_desconocida_sigue_siendo_404():
    from app.core.errores import ErrorDeDominio
    from app.services.conectores import fichas
    with pytest.raises(ErrorDeDominio):
        fichas.ficha("factura")


# ── contecintelligence: anomalías y token incrustable ────────────────────────

@pytest.fixture
def doble_ci(db, monkeypatch):
    from tests import test_conectores_contec_2026_11 as base

    class Doble(base._Doble):
        def _ci(self, req, ruta, rol, alcances, cuerpo):
            if ruta == "/metrics/anomalies":
                return httpx.Response(200, json={
                    "metrica": cuerpo["metric"], "metodo": "mad", "sql": "SELECT 1",
                    "puntos": [{"etiqueta": "2026-11-01", "valor": 10, "esperado": 10, "desviacion": 0,
                                "es_anomalia": False},
                               {"etiqueta": "2026-11-02", "valor": 90, "esperado": 11, "desviacion": 7.2,
                                "es_anomalia": True}],
                    "anomalias": ["2026-11-02"]})
            return super()._ci(req, ruta, rol, alcances, cuerpo)

    d = Doble()
    monkeypatch.setattr(base.anfitrion, "httpx", base._Shim(d))
    base.anfitrion.olvidar_tokens()
    for clave, valor in (("base_url", base.BASE_CI), ("client_id", "cid"), ("client_secret", "secreto"),
                         ("source_id", "s-erp")):
        base.creds.set_credential(db, "contecintelligence", clave, valor, ORG)
    db.commit()
    yield d
    base.anfitrion.olvidar_tokens()


def test_anomalias_de_una_metrica_certificada(client, doble_ci, pm_token):
    r = client.post("/api/v1/conectores/contecintelligence/metricas/anomalias", headers=auth(pm_token),
                    json={"source_id": "s-erp", "metric": "ventas_netas", "time_column": "fecha",
                          "start": "2026-11-01", "end": "2026-11-30", "granularity": "day"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["anomalias"] == ["2026-11-02"] and [p["es_anomalia"] for p in d["puntos"]] == [False, True]
    pedido = [c for _, ruta, c in doble_ci.llamadas if ruta.endswith("/metrics/anomalies")][-1]
    assert pedido["time_column"] == "fecha" and pedido["granularity"] == "day"


def test_sin_origen_permitido_no_se_emite_token(client, doble_ci, pm_token, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CONTECINTELLIGENCE_EMBED_ORIGINS", "")
    d = client.post("/api/v1/conectores/contecintelligence/token", headers=auth(pm_token), json={}).json()["data"]
    assert d["incrustable"] is False and d["access_token"] is None
    assert not [1 for _, ruta, _ in doble_ci.llamadas if ruta.endswith("/tokens/exchange")]


def test_la_csp_solo_abre_los_origenes_bien_formados(monkeypatch):
    from app.core.config import settings
    from app.services.conectores.contecintelligence import origenes_incrustables
    monkeypatch.setattr(settings, "CONTECINTELLIGENCE_EMBED_ORIGINS",
                        "https://ci.test, https://malo.test/ruta, https://x.test; script-src *,http://ci2.test:8443/")
    assert origenes_incrustables() == ["https://ci.test", "http://ci2.test:8443"]


def test_la_csp_de_la_spa_lleva_el_origen_configurado(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CONTECINTELLIGENCE_EMBED_ORIGINS", "https://ci.test")
    csp = client.get("/health").headers.get("content-security-policy", "")
    assert "connect-src 'self' https://ci.test ws: wss:" in csp


# ── Preguntas sin respuesta como tareas ──────────────────────────────────────

def test_pregunta_sin_respuesta_a_tarea_y_se_cierra_al_publicar_el_articulo(db):
    from app.models.enterprise import Notification
    from app.models.service_desk import KBArticle, KBStatus
    from app.models.service_desk.kb_calidad import KBGap
    from app.models.task import Task
    from app.services.service_desk import kb_calidad
    from app.services.service_desk.kb_service import apply_kb_article_update
    from app.schemas.service_desk import KBArticleUpdate
    pid = _proyecto(db)
    hueco = KBGap(id="g-207", question_key="vpn casa", question="¿Cómo conecto la VPN desde casa?",
                  source="portal_chat", organization_id=ORG)
    db.add(hueco)
    db.commit()
    admin = db.get(User, "admin-test-id")
    with con_empresa(db, ORG):
        r = kb_calidad.convertir_en_tarea(db, admin, "g-207", pid, owner_id="dev-test-id",
                                          due_date=datetime(2026, 12, 1).date())
        tarea = db.get(Task, r["task_id"])
        assert tarea.assignee_id == "dev-test-id" and tarea.project_id == pid
        assert r["follow_status"] == "en_curso"
        assert db.query(Notification).filter(Notification.user_id == "dev-test-id",
                                             Notification.resource == "kb_gap").count() == 1
        # Enlazar un artículo en borrador no la cierra; publicarlo sí (y su tarea).
        art = KBArticle(id="kb-207", number="KB-0207", title="VPN desde casa", body="Pasos…",
                        status=KBStatus.draft, organization_id=ORG, author_id="admin-test-id")
        db.add(art)
        db.commit()
        kb_calidad.enlazar_articulo(db, admin, "g-207", "kb-207")
        assert db.get(KBGap, "g-207").status == "open"
        apply_kb_article_update(db, art, KBArticleUpdate(status="published"), changed_by_user_id="admin-test-id")
        db.commit()
    hueco = db.get(KBGap, "g-207")
    assert (hueco.status, hueco.follow_status, hueco.closed_by) == ("answered", "hecho", "admin-test-id")
    assert getattr(db.get(Task, r["task_id"]).status, "value", None) == "done"


def test_seguimiento_valida_estado_y_responsable_de_la_empresa(db):
    from app.core.errores import ErrorDeDominio
    from app.models.service_desk.kb_calidad import KBGap
    from app.services.service_desk import kb_calidad
    _otra_empresa(db)
    _usuario(db, "ajeno-207", OTRA)
    db.add(KBGap(id="g-207b", question_key="otra", question="Otra pregunta larga", source="assistant",
                 organization_id=ORG))
    db.commit()
    admin = db.get(User, "admin-test-id")
    with con_empresa(db, ORG):
        with pytest.raises(ErrorDeDominio):
            kb_calidad.actualizar_seguimiento(db, admin, "g-207b", {"follow_status": "inventado"})
        with pytest.raises(ErrorDeDominio):
            kb_calidad.actualizar_seguimiento(db, admin, "g-207b", {"owner_id": "ajeno-207"})
        r = kb_calidad.actualizar_seguimiento(db, admin, "g-207b", {"owner_id": "pm-test-id",
                                                                    "follow_status": "en_curso"})
    assert (r["owner_id"], r["follow_status"]) == ("pm-test-id", "en_curso")


def test_las_preguntas_de_otra_empresa_no_se_tocan(db):
    from app.core.errores import ErrorDeDominio
    from app.models.service_desk.kb_calidad import KBGap
    from app.services.service_desk import kb_calidad
    _otra_empresa(db)
    db.add(KBGap(id="g-207c", question_key="ajena", question="Pregunta de otra empresa", source="assistant",
                 organization_id=OTRA))
    db.commit()
    with con_empresa(db, ORG), pytest.raises(ErrorDeDominio):
        kb_calidad.actualizar_seguimiento(db, db.get(User, "admin-test-id"), "g-207c", {"follow_status": "hecho"})


# ── Ask-the-Data con memoria ─────────────────────────────────────────────────

@pytest.fixture
def ask_falso(monkeypatch):
    from app.services import ask_the_data as atd
    prompts: list = []

    def generar(question, db, **kw):
        prompts.append(atd._CONTEXTO_DE_CONVERSACION.get())
        return f"SELECT horas FROM fact_timesheets -- {question}"

    monkeypatch.setattr(atd, "_generate_sql", generar)
    monkeypatch.setattr(atd, "validate_sql", lambda sql, org=None: (sql, {}))
    monkeypatch.setattr(atd, "_execute_on_olap", lambda sql, params=None: [{"horas": 40}])
    monkeypatch.setattr(atd, "_verificar", lambda p, s: {"verdict": "not_checked", "checks": []})
    return prompts


def test_la_pregunta_de_seguimiento_lleva_el_contexto_y_se_guarda(db, ask_falso):
    from app.models.ai_chat import AskDataTurn
    from app.services.ask_the_data import ask
    r1 = ask("¿Cuántas horas imputó el equipo en septiembre?", db, org_id=ORG, user_id="pm-test-id")
    r2 = ask("¿y en octubre?", db, org_id=ORG, user_id="pm-test-id", conversation_id=r1["conversation_id"])
    assert r1["conversation_id"] == r2["conversation_id"] and r2["with_context"] is True
    assert ask_falso[0] == "" and "septiembre" in ask_falso[1] and "SQL usada" in ask_falso[1]
    turnos = db.query(AskDataTurn).filter(AskDataTurn.conversation_id == r1["conversation_id"]).all()
    assert [t.question for t in turnos] == ["¿Cuántas horas imputó el equipo en septiembre?", "¿y en octubre?"]
    assert all(t.row_count == 1 for t in turnos)
    # Las filas del resultado no se guardan en ningún sitio de la conversación.
    assert "40" not in json.dumps([(t.question, t.sql, t.error) for t in turnos])


def test_el_contexto_se_acota_con_el_ajuste(db, ask_falso, monkeypatch):
    from app.core.config import settings
    from app.services.ask_the_data import ask
    monkeypatch.setattr(settings, "ASK_DATA_CONTEXT_TURNS", 1)
    c = ask("primera pregunta", db, org_id=ORG, user_id="pm-test-id")["conversation_id"]
    ask("segunda pregunta", db, org_id=ORG, user_id="pm-test-id", conversation_id=c)
    ask("tercera pregunta", db, org_id=ORG, user_id="pm-test-id", conversation_id=c)
    assert "segunda" in ask_falso[2] and "primera" not in ask_falso[2]
    monkeypatch.setattr(settings, "ASK_DATA_CONTEXT_TURNS", 0)
    ask("cuarta", db, org_id=ORG, user_id="pm-test-id", conversation_id=c)
    assert ask_falso[3] == ""


def test_la_conversacion_de_otra_persona_o_empresa_no_se_abre(db, ask_falso):
    from app.core.errores import ErrorDeDominio
    from app.services import ask_memoria
    from app.services.ask_the_data import ask
    _otra_empresa(db)
    c = ask("mi pregunta privada", db, org_id=ORG, user_id="pm-test-id")["conversation_id"]
    with pytest.raises(ErrorDeDominio):
        ask("¿y en octubre?", db, org_id=ORG, user_id="dev-test-id", conversation_id=c)
    with pytest.raises(ErrorDeDominio):
        ask("¿y en octubre?", db, org_id=OTRA, user_id="pm-test-id", conversation_id=c)
    assert ask_memoria.listar(db, ORG, "dev-test-id") == []
    assert ask_memoria.listar(db, OTRA, "pm-test-id") == []
    assert [x["id"] for x in ask_memoria.listar(db, ORG, "pm-test-id")] == [c]


def test_api_de_conversaciones_borrar_una_y_todas_auditado(client, db, ask_falso, pm_token, dev_token):
    from app.models.ai_chat import AskDataConversation, AskDataTurn
    from app.models.enterprise import AuditLog
    url = "/api/v1/analytics/ask"
    c1 = client.post(url, headers=auth(pm_token), json={"question": "horas de septiembre"}).json()["data"]
    client.post(url, headers=auth(pm_token), json={"question": "¿y octubre?", "conversation_id": c1["conversation_id"]})
    client.post(url, headers=auth(pm_token), json={"question": "otra cosa"})
    items = client.get(f"{url}/conversations", headers=auth(pm_token)).json()["data"]["items"]
    assert len(items) == 2
    assert client.get(f"{url}/conversations", headers=auth(dev_token)).json()["data"]["items"] == []
    assert client.get(f"{url}/conversations/{c1['conversation_id']}", headers=auth(dev_token)).status_code == 404
    assert client.delete(f"{url}/conversations/{c1['conversation_id']}", headers=auth(dev_token)).status_code == 404
    r = client.delete(f"{url}/conversations/{c1['conversation_id']}", headers=auth(pm_token))
    assert r.json()["data"]["deleted"] == 1
    assert db.query(AskDataTurn).filter(AskDataTurn.conversation_id == c1["conversation_id"]).count() == 0
    assert client.delete(f"{url}/conversations", headers=auth(pm_token)).json()["data"]["deleted"] == 1
    assert db.query(AskDataConversation).count() == 0
    borrados = db.query(AuditLog).filter(AuditLog.resource == "ask_data_conversation").all()
    assert len(borrados) == 2 and all("horas" not in (b.metadata_ or "") for b in borrados)


def test_supresion_rgpd_borra_sus_conversaciones(db, ask_falso):
    from app.models.ai_chat import AskDataConversation
    from app.services.ask_the_data import ask
    from app.services.supresion_service import suprimir_persona
    ask("pregunta de dev", db, org_id=ORG, user_id="dev-test-id")
    ask("pregunta de pm", db, org_id=ORG, user_id="pm-test-id")
    informe = suprimir_persona(db, db.get(User, "dev-test-id"))
    db.commit()
    assert informe["conversaciones_ask"] == 1
    assert {c.user_id for c in db.query(AskDataConversation).all()} == {"pm-test-id"}


def test_las_conversaciones_tienen_retencion_y_bloqueo_legal():
    import app.db.bloqueo_legal as bl
    tipo = bl.TIPOS["ask_data_conversations"]
    assert tipo.modelo().__tablename__ == "ask_data_conversations" and set(tipo.campos) == {"id", "user_id"}
    assert {"owner_id", "task_id"} <= set(bl.TIPOS["sd_kb_gaps"].campos)
