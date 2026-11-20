"""Asistente de reuniones (19-11-2026): las tres vías, análisis, traducción y GRC.

Diseño: docs/ASISTENTE_DE_REUNIONES.md. Todos los terceros van simulados: STT,
IA, traducción, Graph, Zoom, Meet y el proveedor de bots (sin red).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.user import User
from app.services import settings_service
from tests.conftest import auth

ORG = "1"


@pytest.fixture(autouse=True)
def _cache():
    settings_service.invalidate_cache()
    yield
    settings_service.invalidate_cache()


@pytest.fixture(autouse=True)
def _almacen_temporal(tmp_path, monkeypatch):
    from app.services.reuniones import almacen
    monkeypatch.setattr(almacen, "RAIZ", tmp_path / "reuniones")


@pytest.fixture
def ia(monkeypatch):
    """La IA del análisis devuelve siempre el mismo informe."""
    llamadas = []

    def falso(texto, **kw):
        llamadas.append(texto)
        return json.dumps({
            "title": "Seguimiento Alpha", "summary": "Se revisó Alpha.",
            "decisions": ["Migrar en diciembre"], "risks": ["Infraestructura"],
            "open_questions": ["¿Quién paga la licencia?"],
            "actions": [{"description": "Revisar la infraestructura", "assignee_name": "Project",
                         "due_date": "2026-12-05", "due_date_text": "el viernes"}]})
    monkeypatch.setattr("app.services.ai_modules._base.map_reduce_analysis", falso)
    return llamadas


def _u(db, uid) -> User:
    return db.query(User).filter(User.id == uid).one()


def _cfg(db, cambios, quien="admin-test-id"):
    from app.services.reuniones import config
    r = config.guardar(db, ORG, cambios, _u(db, quien))
    db.commit()
    settings_service.invalidate_cache()
    return r


def _transcripcion(db, quien="pm-test-id", texto="[00:05] Ana: Empezamos.\n[00:20] Luis: Yo reviso Alpha.", **extra):
    from app.services.reuniones import servicio
    r = servicio.crear(db, _u(db, quien), {"title": "Reunión semanal", "origin": "transcript", "transcript": texto,
                                           **extra})
    db.commit()
    return r


# ── Configuración y terceros ──────────────────────────────────────────────────

def test_el_bot_no_se_activa_sin_contrato_y_los_secretos_no_salen(db):
    """19-11-2026: activado por defecto; sin contrato se guarda pero NO se puede invitar."""
    from app.core.codigos_de_error import ErrorConCodigo
    from app.services.reuniones import config as cfg_reuniones
    from app.services.reuniones.bots import proveedor
    assert cfg_reuniones.POR_DEFECTO["bots"]["enabled"] is True
    _cfg(db, {"bots": {"enabled": True, "api_key": "k"}})
    with pytest.raises(ErrorConCodigo) as e:
        proveedor(db, ORG)
    assert e.value.codigo == "reuniones_proveedor_sin_contrato"
    db.rollback()
    r = _cfg(db, {"bots": {"enabled": True, "api_key": "clave-secreta", "contract_reference": "DPA-2026-07"},
                  "teams": {"enabled": True, "client_secret": "s3cr3t"}})
    texto = json.dumps(r)
    assert "clave-secreta" not in texto and "s3cr3t" not in texto
    assert r["bots"]["api_key_set"] and r["teams"]["client_secret_set"] is True
    assert r["bots"]["contract_accepted_by"] == "admin-test-id" and r["teams"]["client_state_set"]


def test_el_stt_externo_exige_activacion_y_contrato(db, monkeypatch):
    from app.core.codigos_de_error import ErrorConCodigo
    from app.services.reuniones import transcripcion
    monkeypatch.setattr(transcripcion, "proveedores_configurados", lambda db, org: ["openai", "azure"])
    assert transcripcion.proveedores_permitidos(db, ORG) == ["whisper_local"]
    with pytest.raises(ErrorConCodigo):
        _cfg(db, {"transcription": {"allow_external_stt": True}})
    db.rollback()
    _cfg(db, {"transcription": {"allow_external_stt": True, "external_stt_contract": "DPA-OpenAI"}})
    assert transcripcion.proveedores_permitidos(db, ORG) == ["openai", "azure", "whisper_local"]


def test_retencion_fuera_de_rango(db):
    from app.core.codigos_de_error import ErrorConCodigo
    with pytest.raises(ErrorConCodigo) as e:
        _cfg(db, {"retention": {"audio_days": 0}})
    assert e.value.codigo == "reuniones_retencion_no_valida"


# ── Visibilidad ───────────────────────────────────────────────────────────────

def test_solo_ven_la_reunion_asistentes_responsables_y_quien_puede(client, db, ia, pm_token, dev_token,
                                                                    admin_token, sub_token):
    m = _transcripcion(db)
    assert client.get(f"/api/v1/meeting-assistant/meetings/{m.id}", headers=auth(dev_token)).status_code == 404
    assert all(x["id"] != m.id for x in client.get("/api/v1/meeting-assistant/meetings",
                                                    headers=auth(dev_token)).json()["items"])
    assert client.get(f"/api/v1/meeting-assistant/meetings/{m.id}", headers=auth(pm_token)).status_code == 200
    assert client.get(f"/api/v1/meeting-assistant/meetings/{m.id}", headers=auth(admin_token)).status_code == 200
    # La ruta antigua también acota.
    assert client.get(f"/api/v1/ai-modules/meetings/{m.id}", headers=auth(dev_token)).status_code == 404
    # Un externo no entra al módulo.
    assert client.get("/api/v1/meeting-assistant/meetings", headers=auth(sub_token)).status_code == 403
    # Como asistente, sí (y no la gestiona).
    from app.services.reuniones import servicio
    servicio.añadir_participante(db, m, user_id="dev-test-id")
    db.commit()
    r = client.get(f"/api/v1/meeting-assistant/meetings/{m.id}", headers=auth(dev_token))
    assert r.status_code == 200 and r.json()["data"]["permissions"]["manage"] is False
    assert client.delete(f"/api/v1/meeting-assistant/meetings/{m.id}", headers=auth(dev_token)).status_code == 403


# ── Vía 3: grabación propia ───────────────────────────────────────────────────

def test_grabar_exige_el_aviso(db):
    from app.core.errores import ErrorDeDominio
    from app.services.reuniones import servicio
    with pytest.raises(ErrorDeDominio) as e:
        servicio.crear(db, _u(db, "pm-test-id"), {"title": "Sala", "origin": "recording"})
    assert e.value.status_code == 422 and e.value.code == "reuniones_sin_aviso"


def test_grabacion_por_trozos_transcribe_y_analiza(db, ia, monkeypatch):
    from app.services.reuniones import servicio, transcripcion
    from app.services.stt import STTResult
    monkeypatch.setattr(transcripcion, "transcribir",
                        lambda *a, **k: STTResult(text="Hablamos de Alpha", provider="whisper_local",
                                                  duration_ms=30000, language="es"))
    pm = _u(db, "pm-test-id")
    m = servicio.crear(db, pm, {"title": "Sala", "origin": "recording", "notice_confirmed": True,
                                "source": "tab", "participants": [{"name": "Cliente Uno", "email": "c1@ext.com"}]})
    assert m.status == "grabando" and m.notice_confirmed_by == pm.id and m.audio_expires_at
    r1 = servicio.subir_audio(db, pm, m, b"\x1aE\xdf\xa3uno", "audio/webm;codecs=opus", 0, 0)
    r2 = servicio.subir_audio(db, pm, m, b"\x1aE\xdf\xa3dos", "audio/webm", 1, 30000)
    assert r1["segments_added"] == 1 and r2["segments_added"] == 1
    assert [s.start_ms for s in m.segmentos] == [0, 30000]
    servicio.terminar(db, pm, m)
    db.commit()
    assert m.status == "lista" and m.summary == "Se revisó Alpha."
    assert json.loads(m.open_questions) == ["¿Quién paga la licencia?"]
    (accion,) = m.actions
    assert accion.due_date.date().isoformat() == "2026-12-05"
    assert len(m.audios) == 2 and m.original_language == "es"


def test_trozo_fuera_de_grabacion_es_409(db, ia):
    from app.core.errores import ErrorDeDominio
    from app.services.reuniones import servicio
    m = _transcripcion(db)
    with pytest.raises(ErrorDeDominio) as e:
        servicio.subir_audio(db, _u(db, "pm-test-id"), m, b"x", "audio/webm", 0, 0)
    assert e.value.code == "reuniones_no_grabando"


def test_escuchar_y_descargar_queda_auditado(db, ia, monkeypatch):
    from app.models.enterprise import AuditLog
    from app.services.reuniones import servicio, transcripcion
    from app.services.stt import STTResult
    monkeypatch.setattr(transcripcion, "transcribir", lambda *a, **k: STTResult(text="hola", provider="whisper_local"))
    pm = _u(db, "pm-test-id")
    m = servicio.crear(db, pm, {"title": "Sala", "origin": "recording", "notice_confirmed": True})
    r = servicio.subir_audio(db, pm, m, b"audio-bytes", "audio/webm", 0, 0)
    datos, tipo, _ = servicio.leer_audio(db, pm, m, r["chunk_id"], descargar=False)
    servicio.leer_audio(db, pm, m, r["chunk_id"], descargar=True)
    servicio.exportar_transcripcion(db, pm, m, "vtt")
    db.commit()
    assert datos == b"audio-bytes" and tipo == "audio/webm"
    acciones = {a.action for a in db.query(AuditLog).filter(AuditLog.resource == "ai_meeting").all()}
    assert {"LISTEN", "DOWNLOAD", "RECORDING_START"} <= acciones


# ── Consentimiento ────────────────────────────────────────────────────────────

def test_con_consentimiento_exigido_no_se_analiza_hasta_tenerlo_y_un_no_tacha(db, ia):
    from app.services.reuniones import servicio
    from app.services.reuniones.analisis import TACHADO
    _cfg(db, {"consent": {"require_consent": True}})
    m = _transcripcion(db, texto="Ana: Hola a todos.\nLuis Externo: Prefiero no salir.",
                       participants=[{"name": "Luis Externo", "email": "luis@ext.com"}])
    assert m.status == "esperando_consentimiento" and not ia
    luis = next(p for p in m.participantes if p.email == "luis@ext.com")
    ana = next(p for p in m.participantes if p.name == "Ana")
    pm = _u(db, "pm-test-id")
    servicio.consentir(db, pm, m, ana.id, True, "verbal")
    servicio.consentir(db, pm, m, luis.id, False, "verbal")
    db.commit()
    assert m.status == "lista"
    assert all(s.text == TACHADO for s in m.segmentos if s.participant_id == luis.id)
    assert "Prefiero no salir" not in ia[-1]


def test_una_persona_de_la_empresa_consiente_por_si_misma(db, ia):
    from app.core.errores import ErrorDeDominio
    from app.services.reuniones import servicio
    m = _transcripcion(db)
    p = servicio.añadir_participante(db, m, user_id="dev-test-id")
    db.commit()
    with pytest.raises(ErrorDeDominio):
        servicio.consentir(db, _u(db, "pm-test-id"), m, p.id, True, "verbal")
    servicio.consentir(db, _u(db, "dev-test-id"), m, None, True)
    assert p.consent is True and p.consent_method == "self"


# ── Traducción ────────────────────────────────────────────────────────────────

def test_cada_persona_la_lee_en_su_idioma(db, ia, monkeypatch):
    from app.services.reuniones.traduccion import traducir_reunion
    from app.services.traduccion import servicio as trad
    m = _transcripcion(db)
    m.original_language = "es"
    monkeypatch.setattr(trad, "traducir", lambda db, org, textos, destino, **k:
                        [trad.Resultado(trad.TRADUCIDO, destino, f"[{destino}] {t}", "es", "ai") for t in textos])
    t = traducir_reunion(db, m, "en", _u(db, "pm-test-id"))
    assert t["summary"] == "[en] Se revisó Alpha." and t["translation"]["status"] == "translated"
    db.commit()
    assert len(m.traducciones) == 1
    # Segunda vez, de la caché.
    monkeypatch.setattr(trad, "traducir", lambda *a, **k: pytest.fail("debía salir de la caché"))
    assert traducir_reunion(db, m, "en")["decisions"] == ["[en] Migrar en diciembre"]


def test_sin_canal_de_traduccion_se_ve_el_original_y_el_motivo(db, ia, monkeypatch):
    from app.services.reuniones.traduccion import traducir_reunion
    from app.services.traduccion import servicio as trad
    m = _transcripcion(db)
    m.original_language = "es"
    monkeypatch.setattr(trad, "traducir", lambda db, org, textos, destino, **k:
                        [trad.Resultado(trad.DESACTIVADA, destino, motivo="channel_disabled") for _ in textos])
    t = traducir_reunion(db, m, "zh")
    assert t["translation"] == {"status": "disabled", "reason": "channel_disabled"}


# ── Acciones con un clic ──────────────────────────────────────────────────────

def test_accion_a_tarea_ticket_y_acta(db, ia, monkeypatch):
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.service_desk import Ticket
    from app.models.task import Task
    from app.services import s3_service
    from app.services.reuniones import servicio
    monkeypatch.setattr(s3_service.file_storage, "upload_file", lambda **k: ("documents/x/v1/a.html", 10))
    p = Project(code="ALP", name="Alpha", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id=ORG)
    db.add(p)
    db.commit()
    m = _transcripcion(db, project_id=p.id)
    pm = _u(db, "pm-test-id")
    (a,) = m.actions
    tarea = servicio.accion_a_tarea(db, pm, m, a.id)
    ticket = servicio.accion_a_ticket(db, pm, m, a.id)
    acta = servicio.generar_acta(db, pm, m)
    db.commit()
    t = db.get(Task, tarea["task_id"])
    assert t.project_id == p.id and t.due_date.isoformat() == "2026-12-05" and t.code.startswith("TSK")
    assert db.get(Ticket, ticket["ticket_id"]).source == "meeting"
    assert m.minutes_document_id == acta["document_id"]


def test_sin_proyecto_la_tarea_pide_uno(db, ia):
    from app.core.errores import ErrorDeDominio
    from app.services.reuniones import servicio
    m = _transcripcion(db)
    m.project_id = None
    with pytest.raises(ErrorDeDominio) as e:
        servicio.accion_a_tarea(db, _u(db, "pm-test-id"), m, m.actions[0].id)
    assert e.value.code == "reuniones_sin_proyecto"


# ── Búsqueda y Nexus ──────────────────────────────────────────────────────────

def test_busqueda_y_nexus_solo_en_lo_visible(db, ia):
    from app.services.ai_chat.tool_execution.executor import _HANDLERS
    from app.services.reuniones import servicio
    m = _transcripcion(db, texto="Ana: El presupuesto de Kraken sube.")
    assert any(r["meeting_id"] == m.id for r in servicio.buscar(db, _u(db, "pm-test-id"), "kraken"))
    assert servicio.buscar(db, _u(db, "dev-test-id"), "kraken") == []
    h = _HANDLERS["search_meetings"]
    assert h({"meeting_id": m.id}, db, _u(db, "dev-test-id"), None, False) == {"error": "Reunión no encontrada"}
    assert h({"meeting_id": m.id}, db, _u(db, "pm-test-id"), None, False)["meeting"]["summary"]


# ── Retención y bloqueo legal ─────────────────────────────────────────────────

def _con_audio_caducado(db, monkeypatch):
    from app.services.reuniones import servicio, transcripcion
    from app.services.stt import STTResult
    monkeypatch.setattr(transcripcion, "transcribir", lambda *a, **k: STTResult(text="hola", provider="whisper_local"))
    pm = _u(db, "pm-test-id")
    m = servicio.crear(db, pm, {"title": "Sala", "origin": "recording", "notice_confirmed": True})
    servicio.subir_audio(db, pm, m, b"audio", "audio/webm", 0, 0)
    pasado = datetime.now(timezone.utc) - timedelta(days=1)
    for a in m.audios:
        a.expires_at = pasado
    m.transcript_expires_at = pasado
    db.commit()
    return m


def test_la_retencion_borra_audio_y_transcripcion_caducados(db, monkeypatch):
    from app.services.reuniones.trabajos import retencion
    m = _con_audio_caducado(db, monkeypatch)
    r = retencion(db, ORG)
    db.commit()
    db.refresh(m)
    assert r["audio_chunks"] == 1 and r["transcripts"] == 1
    assert not m.audios and not m.segmentos and m.transcript_purged_at is not None


def test_bajo_bloqueo_legal_no_se_purga_ni_se_borra(db, monkeypatch):
    from app.core.errores import ErrorDeDominio
    from app.models.governance import LegalHold
    from app.services.reuniones import servicio
    from app.services.reuniones.trabajos import retencion
    m = _con_audio_caducado(db, monkeypatch)
    db.add(LegalHold(organization_id=ORG, case_reference="LIT-1", reason="litigio", entity="meetings",
                     field="id", value=m.id, is_active=True, created_by="admin-test-id"))
    db.commit()
    r = retencion(db, ORG)
    assert r["audio_chunks"] == 0 and r["transcripts"] == 0 and r["held"] == 1
    with pytest.raises(ErrorDeDominio) as e:
        servicio.borrar(db, _u(db, "admin-test-id"), m)
    assert e.value.status_code == 409


# ── RGPD por persona, también como hablante ───────────────────────────────────

def test_rgpd_copia_y_supresion_de_un_hablante_externo(db, ia):
    from app.services.reuniones import rgpd
    m = _transcripcion(db, texto="Marta Ext: Mi DNI es secreto.\nAna: Vale.",
                       participants=[{"name": "Marta Ext", "email": "marta@cliente.com"}])
    copia = rgpd.copia(db, ORG, email="marta@cliente.com")
    assert copia["meetings_count"] == 1 and copia["meetings"][0]["said"][0]["text"] == "Mi DNI es secreto."
    informe = rgpd.suprimir(db, ORG, email="MARTA@cliente.com")
    db.commit()
    assert informe["segments"] == 1 and informe["meetings"] == 1
    assert all("DNI" not in s.text for s in m.segmentos)
    assert rgpd.copia(db, ORG, email="marta@cliente.com")["meetings_count"] == 0


def test_la_supresion_de_una_persona_incluye_sus_reuniones(db, ia):
    from app.services.reuniones import servicio
    from app.services.supresion_service import suprimir_persona
    m = _transcripcion(db)
    p = servicio.añadir_participante(db, m, user_id="dev-test-id")
    db.flush()
    servicio.añadir_segmentos(db, m, [{"speaker": "Dev", "text": "Lo que dije", "email": None}])
    m.segmentos[-1].participant_id = p.id
    db.commit()
    informe = suprimir_persona(db, _u(db, "dev-test-id"))
    assert informe["reuniones"]["meetings"] == 1
    assert all(s.text != "Lo que dije" for s in m.segmentos)


# ── Firmas de los avisos ──────────────────────────────────────────────────────

def test_firma_svix_del_proveedor_de_bots():
    from app.services.reuniones.bots.recall import RecallBots
    secreto = "whsec_" + base64.b64encode(b"clave-de-prueba").decode()
    cuerpo, ident, marca = b'{"event":"bot.status_change"}', "msg_1", str(int(time.time()))
    firma = base64.b64encode(hmac.new(b"clave-de-prueba", f"{ident}.{marca}.".encode() + cuerpo,
                                      hashlib.sha256).digest()).decode()
    cab = {"webhook-id": ident, "webhook-timestamp": marca, "webhook-signature": f"v1,{firma}"}
    bots = RecallBots("k")
    assert bots.verificar_firma(cab, cuerpo, secreto)
    assert not bots.verificar_firma(cab, cuerpo + b" ", secreto)
    assert not bots.verificar_firma({**cab, "webhook-timestamp": str(int(time.time()) - 3600)}, cuerpo, secreto)


def test_firma_y_validacion_de_zoom():
    from app.services.reuniones.conectores import zoom
    marca, cuerpo = str(int(time.time())), b'{"event":"recording.completed"}'
    firma = "v0=" + hmac.new(b"zs", f"v0:{marca}:".encode() + cuerpo, hashlib.sha256).hexdigest()
    assert zoom.firma_valida("zs", marca, firma, cuerpo)
    assert not zoom.firma_valida("otro", marca, firma, cuerpo)
    r = zoom.respuesta_de_validacion("zs", "abc")
    assert r["encryptedToken"] == hmac.new(b"zs", b"abc", hashlib.sha256).hexdigest()


def test_webhooks_sin_secreto_o_con_firma_mala_dan_403(client, db):
    assert client.post(f"/api/v1/webhooks/meetings/zoom/{ORG}", content=b"{}").status_code == 403
    assert client.post(f"/api/v1/webhooks/meetings/recall/{ORG}", content=b"{}").status_code == 403
    _cfg(db, {"teams": {"enabled": True, "tenant_id": "t", "client_id": "c", "client_secret": "s"}})
    r = client.post(f"/api/v1/webhooks/meetings/teams/{ORG}",
                    json={"value": [{"clientState": "no-es", "resource": "x"}]})
    assert r.status_code == 403
    v = client.post(f"/api/v1/webhooks/meetings/teams/{ORG}?validationToken=hola")
    assert v.status_code == 200 and v.text == "hola"


# ── Vía 1: plataformas (HTTP simulado) ────────────────────────────────────────

_VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n<v Ana Pérez>Abrimos la reunión.</v>\n\n" \
       "00:00:05.000 --> 00:00:09.000\n<v Luis>Yo me encargo del despliegue.</v>\n"


def _transporte(monkeypatch, rutas: dict):
    from app.services.reuniones import conectores

    def manejar(req: httpx.Request):
        for clave, respuesta in rutas.items():
            if clave in str(req.url):
                return respuesta(req) if callable(respuesta) else respuesta
        return httpx.Response(404, json={"error": str(req.url)})
    monkeypatch.setattr(conectores, "_transporte", httpx.MockTransport(manejar))


def test_vtt_a_segmentos_con_hablante_y_tiempos():
    from app.services.reuniones.transcripcion import de_vtt
    segs = de_vtt(_VTT)
    assert segs[0] == {"speaker": "Ana Pérez", "start_ms": 1000, "end_ms": 4000, "text": "Abrimos la reunión."}
    assert segs[1]["speaker"] == "Luis"


def test_teams_importa_por_url_sin_duplicar(db, ia, monkeypatch):
    from app.services.reuniones import servicio
    _cfg(db, {"teams": {"enabled": True, "tenant_id": "t", "client_id": "c", "client_secret": "s"}})
    reunion = {"id": "MSo1", "subject": "Revisión Alpha", "startDateTime": "2026-11-19T09:00:00Z",
               "endDateTime": "2026-11-19T10:00:00Z", "joinWebUrl": "https://teams.microsoft.com/l/x",
               "participants": {"organizer": {"upn": "pm@test.com"}, "attendees": [{"upn": "ext@cli.com"}]}}
    _transporte(monkeypatch, {
        "oauth2/v2.0/token": httpx.Response(200, json={"access_token": "tk"}),
        "/content": httpx.Response(200, text=_VTT),
        "/transcripts": httpx.Response(200, json={"value": [{"id": "T1"}]}),
        "onlineMeetings?$filter": httpx.Response(200, json={"value": [reunion]}),
    })
    pm = _u(db, "pm-test-id")
    m = servicio.importar(db, pm, "teams", "https://teams.microsoft.com/l/x")
    db.commit()
    assert m.origin == "teams" and m.status == "lista" and len(m.segmentos) == 2
    assert m.segmentos[0].speaker == "Ana Pérez" and m.duration_min == 60
    assert servicio.importar(db, pm, "teams", "https://teams.microsoft.com/l/x").id == m.id


def test_zoom_recording_completed_crea_la_reunion(client, db, ia, monkeypatch):
    from app.models.ai_chat import AIMeeting
    _cfg(db, {"zoom": {"enabled": True, "account_id": "a", "client_id": "c", "client_secret": "s",
                       "webhook_secret": "zs"}})
    _transporte(monkeypatch, {"zoom.us/rec/download": httpx.Response(200, text=_VTT)})
    cuerpo = json.dumps({"event": "recording.completed", "download_token": "dt", "payload": {"object": {
        "uuid": "Z-1", "topic": "Kick-off", "start_time": "2026-11-19T09:00:00Z", "duration": 30,
        "host_email": "pm@test.com", "recording_files": [
            {"file_type": "TRANSCRIPT", "download_url": "https://zoom.us/rec/download/abc"}]}}}).encode()
    marca = str(int(time.time()))
    firma = "v0=" + hmac.new(b"zs", f"v0:{marca}:".encode() + cuerpo, hashlib.sha256).hexdigest()
    r = client.post(f"/api/v1/webhooks/meetings/zoom/{ORG}", content=cuerpo,
                    headers={"x-zm-request-timestamp": marca, "x-zm-signature": firma,
                             "content-type": "application/json"})
    assert r.status_code == 200, r.text
    m = db.query(AIMeeting).filter(AIMeeting.external_id == "Z-1").one()
    assert m.origin == "zoom" and m.title == "Kick-off" and len(m.segmentos) == 2


def test_meet_lee_las_entradas_de_la_transcripcion(db, ia, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from app.services.reuniones import servicio
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    _cfg(db, {"meet": {"enabled": True, "service_account_email": "sa@p.iam.gserviceaccount.com",
                       "service_account_key": json.dumps({"client_email": "sa@p.iam", "private_key": clave})}})
    _transporte(monkeypatch, {
        "oauth2.googleapis.com/token": httpx.Response(200, json={"access_token": "tk"}),
        "/entries": httpx.Response(200, json={"transcriptEntries": [
            {"participant": "conferenceRecords/r1/participants/p1", "text": "Buenos días",
             "startTime": "2026-11-19T09:00:05Z", "endTime": "2026-11-19T09:00:07Z", "languageCode": "es-ES"}]}),
        "/transcripts": httpx.Response(200, json={"transcripts": [{"name": "conferenceRecords/r1/transcripts/t1"}]}),
        "/participants": httpx.Response(200, json={"participants": [
            {"name": "conferenceRecords/r1/participants/p1", "signedinUser": {"displayName": "Ana"}}]}),
        "conferenceRecords/r1": httpx.Response(200, json={"name": "conferenceRecords/r1",
                                                          "startTime": "2026-11-19T09:00:00Z",
                                                          "endTime": "2026-11-19T09:30:00Z"}),
    })
    m = servicio.importar(db, _u(db, "pm-test-id"), "meet", "r1")
    assert m.origin == "meet" and m.segmentos[0].speaker == "Ana" and m.segmentos[0].start_ms == 5000


# ── Vía 2: bot invitado (proveedor simulado) ──────────────────────────────────

class _BotFalso:
    nombre = "recall"

    def __init__(self):
        self.creados, self.borrados = [], []

    def crear_bot(self, url, **kw):
        self.creados.append((url, kw))
        return {"id": "bot-1", "estado": "programada"}

    def transcripcion(self, bot_id):
        return [{"speaker": "Ana", "start_ms": 0, "end_ms": 3000, "text": "Arrancamos"}]

    def borrar_medios(self, bot_id):
        self.borrados.append(bot_id)

    def salir(self, bot_id):
        pass


def test_bot_activado_por_defecto_pero_sin_contrato_no_se_invita(db):
    """19-11-2026: el bot nace activado; sin contrato de encargo no se puede invitar."""
    from app.core.codigos_de_error import ErrorConCodigo
    from app.services.reuniones import servicio
    with pytest.raises(ErrorConCodigo) as e:
        servicio.invitar_bot(db, _u(db, "pm-test-id"), {"meeting_url": "https://zoom.us/j/123"})
    assert e.value.codigo == "reuniones_proveedor_sin_contrato"


def test_bot_invitado_avisa_al_entrar_y_al_terminar_analiza(db, ia, monkeypatch):
    from app.core.errores import ErrorDeDominio
    from app.services.reuniones import bots, servicio
    from app.services.reuniones.bots import EventoDeBot
    falso = _BotFalso()
    monkeypatch.setattr(bots, "_SUSTITUTO", falso)
    _cfg(db, {"bots": {"enabled": True, "contract_reference": "DPA-1", "bot_name": "Acta"},
              "consent": {"bot_message": "Grabo esta reunión para el acta."}})
    pm = _u(db, "pm-test-id")
    with pytest.raises(ErrorDeDominio):
        servicio.invitar_bot(db, pm, {"meeting_url": "https://malicioso.example/j/1"})
    m = servicio.invitar_bot(db, pm, {"meeting_url": "https://meet.google.com/abc-defg-hij", "title": "Diario"})
    db.commit()
    assert m.status == "programada" and m.bot_id == "bot-1" and m.platform == "meet"
    assert falso.creados[0][1]["mensaje_al_entrar"] == "Grabo esta reunión para el acta."
    servicio.procesar_evento_de_bot(db, ORG, EventoDeBot("bot-1", "grabando", "in_call_recording"))
    assert m.status == "grabando"
    servicio.procesar_evento_de_bot(db, ORG, EventoDeBot("bot-1", "terminada", "done"))
    db.commit()
    assert m.status == "lista" and m.segmentos[0].text == "Arrancamos"
    servicio.borrar(db, pm, m)
    db.commit()
    assert falso.borrados == ["bot-1"]


# ── Informe de cumplimiento ───────────────────────────────────────────────────

def test_controles_del_informe_de_cumplimiento(db, monkeypatch):
    from app.services.informe_de_cumplimiento import _control
    from app.services.reuniones.cumplimiento import controles
    _con_audio_caducado(db, monkeypatch)
    ids = {c["id"]: c for c in controles(db, ORG, _control)}
    assert set(ids) == {"meetings_external_processors", "meetings_retention", "meetings_consent"}
    assert ids["meetings_retention"]["status"] == "attention"
    # 19-11-2026: el bot nace activado; sin contrato de encargo el control pide atención,
    # y con contrato pasa.
    assert ids["meetings_external_processors"]["status"] == "attention"
    _cfg(db, {"bots": {"enabled": True, "contract_reference": "DPA-1"}})
    ids = {c["id"]: c for c in controles(db, ORG, _control)}
    assert ids["meetings_external_processors"]["status"] == "pass"


def test_capacidades_del_asistente():
    from app.core.capacidades import CAPACIDADES
    assert "employee" in CAPACIDADES["reuniones.usar"].roles
    assert "subcontractor" not in CAPACIDADES["reuniones.usar"].roles
    assert CAPACIDADES["reuniones.config"].roles == ("admin",)
    assert CAPACIDADES["reuniones.ver_todas"].roles == ("admin",)


def test_bot_en_el_calendario_activado_por_defecto(db):
    """19-11-2026: sin preferencias guardadas, el bot entra en las reuniones del calendario."""
    from app.models.user import User
    from app.services.reuniones.servicio import preferencias
    u = db.query(User).filter(User.id == "admin-test-id").first()
    assert preferencias(db, u)["bot_for_my_calendar"] is True
