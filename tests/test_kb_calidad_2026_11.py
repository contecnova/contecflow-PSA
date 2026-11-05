"""Calidad de la base de conocimiento (revisión 2026-11, lo que contecmind ya tenía).

Medido antes: el asistente buscaba contexto en `ai_kb_articles` (0 filas) y no
en la base del Service Desk; el chat de IA del portal no miraba la base; el bot
L1 buscaba la pregunta entera como subcadena literal. No había correcciones,
lista de preguntas sin respuesta ni avisos de artículos caducados o
contradictorios.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enterprise import Notification
from app.models.service_desk import KBArticle, KBStatus
from app.models.service_desk.kb_calidad import KBCorrection, KBFinding, KBGap
from app.services.service_desk import kb_calidad
from tests.conftest import auth
from tests.test_portal_wiki_tenant_isolation import _create_portal_client, _create_project, _portal_login

VPN = "Configurar la VPN de la oficina"


def _articulo(db, titulo=VPN, cuerpo="Instala el cliente VPN, usa tu usuario de la oficina y el puerto 443.",
              numero="KB-0901", **kw):
    kw.setdefault("is_public", True)
    a = KBArticle(number=numero, title=titulo, body=cuerpo, status=KBStatus.published,
                  organization_id="1", author_id="admin-test-id", **kw)
    db.add(a)
    db.commit()
    return a


@pytest.fixture
def ia(monkeypatch):
    vistos = []

    def _falso(db, messages, system=None, **k):
        vistos.append(system or "")
        return "respuesta"
    monkeypatch.setattr("app.api.v1.endpoints.ai_chat.call_ai", _falso)
    monkeypatch.setattr("app.services.ai_modules.client_portal.call_ai_unified", _falso)
    return vistos


def _chat(client, token, texto):
    r = client.post("/api/v1/ai/chat", headers=auth(token), json={"message": texto})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_el_asistente_usa_la_base_real_y_cita(client, pm_token, db, ia):
    a = _articulo(db)
    datos = _chat(client, pm_token, "¿Cómo configuro la VPN de la oficina?")
    assert "[KB-0901]" in ia[-1], "el artículo llega al modelo con su número para citarlo"
    assert datos["sources"] == [{"id": a.id, "number": "KB-0901", "title": VPN}]


def test_lo_que_no_es_relevante_no_se_cita(client, pm_token, db, ia):
    _articulo(db)
    assert _chat(client, pm_token, "¿Qué proyectos están en pérdidas este trimestre?")["sources"] == []


def _cliente_del_portal(client, admin_token):
    pid = _create_project(client, admin_token, "KBQ1", "Calidad KB")
    _create_portal_client(client, admin_token, [pid], "kbq@cliente.com", "Portal-KBQ-2026!")
    client.cookies.clear()
    _portal_login(client, "kbq@cliente.com", "Portal-KBQ-2026!")


def _portal_chat(client, texto):
    r = client.post("/api/v1/portal/ai-chat", json={"message": texto})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_la_pregunta_del_cliente_sin_articulo_queda_como_hueco(client, admin_token, db, ia):
    _cliente_del_portal(client, admin_token)
    _portal_chat(client, "¿Puedo cambiar la dirección de facturación de mi contrato?")
    _portal_chat(client, "puedo cambiar la direccion de facturacion de mi contrato")
    hueco = db.query(KBGap).one()
    assert hueco.times_asked == 2 and hueco.source == "portal_chat" and hueco.organization_id == "1"


def test_el_portal_cita_solo_articulos_publicos(client, admin_token, db, ia):
    _articulo(db, is_public=False)
    _cliente_del_portal(client, admin_token)
    assert _portal_chat(client, "Como configuro la VPN de la oficina")["sources"] == []
    _articulo(db, numero="KB-0902")
    assert [s["number"] for s in _portal_chat(client, "Como configuro la VPN de la oficina")["sources"]] == ["KB-0902"]


def test_EL_HALLAZGO_la_correccion_se_aplica_al_momento(client, admin_token, pm_token, db, ia):
    r = client.post("/api/v1/sd/kb/corrections", headers=auth(admin_token), json={
        "question": "¿Cuál es el horario del servicio de soporte?", "answer": "De 8:00 a 18:00, de lunes a viernes."})
    assert r.status_code == 200, r.text
    datos = _chat(client, pm_token, "cual es el horario del servicio de soporte")
    assert datos["correction_applied"] is True and "De 8:00 a 18:00" in ia[-1]
    assert db.query(KBCorrection).one().usage_count == 1


def test_la_correccion_interna_no_llega_al_cliente(client, admin_token, db, ia):
    client.post("/api/v1/sd/kb/corrections", headers=auth(admin_token), json={
        "question": "¿Cuál es el horario del servicio de soporte?", "answer": "Interno: guardia 24h."})
    _cliente_del_portal(client, admin_token)
    _portal_chat(client, "cual es el horario del servicio de soporte")
    assert "guardia 24h" not in ia[-1]


def test_responder_un_hueco_lo_cierra(client, admin_token, db):
    hueco = kb_calidad.registrar_hueco(db, "¿Dónde descargo mis facturas antiguas?", "portal_chat")
    db.commit()
    r = client.post("/api/v1/sd/kb/corrections", headers=auth(admin_token), json={
        "question": hueco.question, "answer": "En Facturas → Histórico.", "is_public": True, "gap_id": hueco.id})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(KBGap, hueco.id).status == "answered"
    calidad = client.get("/api/v1/sd/kb/quality", headers=auth(admin_token)).json()["data"]
    assert calidad["counts"]["gaps"] == 0 and calidad["counts"]["corrections"] == 1


def test_con_revision_solo_corrige_quien_puede_publicar(client, pm_token, db):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "service_desk", "SD_KB_REQUIRE_REVIEW", True, None)
    db.commit()
    settings_service.invalidate_cache()
    r = client.post("/api/v1/sd/kb/corrections", headers=auth(pm_token), json={"question": "abc def", "answer": "xyz"})
    assert r.status_code == 403


def test_EL_HALLAZGO_el_articulo_caducado_avisa_una_vez(db):
    a = _articulo(db)
    viejo = datetime.now(timezone.utc) - timedelta(days=400)
    db.query(KBArticle).filter(KBArticle.id == a.id).update({"updated_at": viejo, "published_at": viejo})
    db.commit()
    assert kb_calidad.pasada(db, "1")["stale"] == 1
    assert kb_calidad.pasada(db, "1")["stale"] == 0
    avisos = db.query(Notification).filter(Notification.user_id == "admin-test-id",
                                           Notification.resource_id == a.id).count()
    assert avisos == 1


@pytest.fixture
def con_ia(monkeypatch):
    monkeypatch.setattr("app.services.ai_provider_service.get_default_provider", lambda db, **k: object())
    preguntas = []

    def _veredicto(db, a, b, org):
        preguntas.append((a.number, b.number))
        return {"contradicts": True, "explanation": "Uno dice puerto 443 y el otro 8443."}
    monkeypatch.setattr(kb_calidad, "preguntar_contradiccion", _veredicto)
    return preguntas


def test_EL_HALLAZGO_detecta_contradicciones_y_no_repite_el_par(db, con_ia):
    _articulo(db, embedding=json.dumps([1.0, 0.0, 0.1]))
    _articulo(db, titulo="VPN: puerto", cuerpo="Usa el puerto 8443.", numero="KB-0903",
              embedding=json.dumps([0.98, 0.05, 0.1]))
    _articulo(db, titulo="Vacaciones", cuerpo="Pídelas en Ausencias.", numero="KB-0904",
              embedding=json.dumps([0.0, 1.0, 0.0]))
    r = kb_calidad.pasada(db, "1")["contradictions"]
    assert r == {"checked": 1, "found": 1}, "solo el par parecido va a la IA"
    assert kb_calidad.pasada(db, "1")["contradictions"]["checked"] == 0, "el mismo par no se vuelve a preguntar"
    f = db.query(KBFinding).filter(KBFinding.kind == "contradiction").one()
    assert f.status == "open" and "8443" in f.detail


def test_sin_proveedor_de_ia_no_se_buscan_contradicciones(db, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider_service.get_default_provider", lambda db, **k: None)
    assert kb_calidad.pasada(db, "1")["contradictions"]["skipped"] == "sin proveedor de IA"


def test_EL_HALLAZGO_sin_modelo_encuentra_otra_forma_del_verbo_y_sin_tildes(db):
    """Medido en la copia: «¿Cómo restablezco mi contraseña?» no citaba «Como restablecer tu contrasena»."""
    _articulo(db, titulo="Como restablecer tu contrasena", cuerpo="Pulsa en olvide mi contrasena.", numero="KB-0911")
    db.info["organization_id"] = "1"
    from app.services.service_desk.kb_sugerencias import sugerir
    [hallado] = sugerir(db, "¿Cómo restablezco mi contraseña?", solo_publico=False)
    assert hallado["number"] == "KB-0911" and hallado["score"] == 1.0, "las dos palabras casan"
