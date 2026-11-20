"""Planes de cambio, playbooks de serie y bloqueos/cupos en el idioma de quien lee (19-11-2026).

Auditoria de textos fijos: los planes de un cambio (vuelta atras, pruebas,
comunicaciones) y el resumen del impacto se guardaban en castellano (o ingles)
fijo; los playbooks de serie del agente autonomo tenian nombre en ingles y
avisos en castellano; los bloqueos de herramientas, del cupo diario de IA y de
las politicas de gobernanza, y el rechazo por cupo de ausencias, igual. Ahora
son claves de `textos_de_salida` (bloque `textos_de_salida_itsm.py`).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.services.textos_de_salida import TEXTOS, texto
from app.services.textos_de_salida_itsm import TEXTOS_ITSM


# ── Las claves existen en es/en/zh y con los mismos datos ────────────────────

def test_el_bloque_esta_fusionado_en_textos():
    assert set(TEXTOS_ITSM) <= set(TEXTOS)


def test_todas_las_claves_en_es_en_zh():
    faltan = [k for k, v in TEXTOS_ITSM.items() if not {"es", "en", "zh"} <= set(v) or not all(v.values())]
    assert not faltan, faltan


def _huecos(plantilla: str) -> set[str]:
    # `{dato}` sí; `{{hueco}}` (lo rellena quien envia el aviso) no.
    return set(re.findall(r"(?<!\{)\{(\w+)\}(?!\})", plantilla))


def test_cada_idioma_usa_los_mismos_datos():
    distintos = {k: {i: _huecos(p) for i, p in v.items()} for k, v in TEXTOS_ITSM.items()
                 if len({frozenset(_huecos(p)) for p in v.values()}) > 1}
    assert not distintos, distintos


def test_los_pasos_de_las_tablas_tienen_su_texto():
    from app.services.service_desk.change_impact_service.comunicacion import _AVISOS_DEL_PLAN, _CHANNEL_MAP
    from app.services.service_desk.change_impact_service.planes import _PASOS_DEL_PLAN
    for fase, tipo, _m, rol, *_ in _PASOS_DEL_PLAN:
        for parte in ("desc", "esperado"):
            assert f"cambio.prueba.{fase}.{tipo}.{parte}" in TEXTOS
        assert f"cambio.rol.{rol}" in TEXTOS
    for _c, _h, publico, canal, aviso, rol, _cond in _AVISOS_DEL_PLAN:
        assert f"cambio.aviso.{aviso}.asunto" in TEXTOS and f"cambio.aviso.{aviso}.mensaje" in TEXTOS
        assert f"cambio.canal.{canal or _CHANNEL_MAP[publico]}" in TEXTOS
        assert f"cambio.rol.{rol}" in TEXTOS


def test_los_playbooks_de_serie_tienen_nombre_y_avisos():
    from app.services.service_desk.autonomous_agent_service import _BUILTIN_PLAYBOOKS
    for pb in _BUILTIN_PLAYBOOKS:
        assert f"autonomo.pb.{pb['id']}" in TEXTOS
        for paso in pb["steps"]:
            if paso["type"] in ("notify", "resolve"):
                assert paso.get("clave") in TEXTOS, (pb["id"], paso["type"])


# ── Los planes se pintan en el idioma pedido ─────────────────────────────────

def test_pintar_datos_repinta_en_otro_idioma_y_quita_las_claves():
    from app.services.service_desk.change_impact_service.textos import (
        con_textos, diferido, pintar_datos, ventana_diferida,
    )
    paso = con_textos({"step": 1}, "es", action=diferido("cambio.vuelta.1"),
                      responsible=diferido("cambio.rol.gestor"))
    assert paso["action"] == "Detener el despliegue si está en curso"
    en = pintar_datos({"rollback_steps": [paso]}, "en")["rollback_steps"][0]
    assert en == {"step": 1, "action": "Stop the deployment if it is in progress",
                  "responsible": "Change manager"}
    assert pintar_datos(paso, "zh")["responsible"] == "变更经理"
    # Un parametro por clave se pinta en el mismo idioma.
    v = ventana_diferida({"day_of_week": 1, "hour_utc": 2})
    assert pintar_datos(con_textos({}, "en", w=v), "zh")["w"] == "星期二 02:00–06:00（UTC）"
    assert pintar_datos(con_textos({}, "es", w=v), "en")["w"] == "Tuesday 02:00–06:00 UTC"
    # Lo guardado antes (sin `_textos`) sale tal cual.
    assert pintar_datos({"action": "texto viejo"}, "en") == {"action": "texto viejo"}


def test_los_huecos_del_que_envia_el_aviso_se_conservan():
    from app.services.service_desk.change_impact_service.textos import diferido, pintar
    msg = pintar(diferido("cambio.aviso.inicio_operaciones.mensaje", number="CHG-1", title="T",
                          ventana="", parada=0, riesgo=""), "en")
    assert "CHG-1" in msg and "{hora_inicio_utc}" in msg


@pytest.fixture
def cambio(db):
    from app.models.service_desk import ITSMChangeRequest
    c = ITSMChangeRequest(id="chg-idiomas", number="CHG-ID1", title="Parche del ERP", description="x",
                          status="submitted", organization_id="1", downtime_minutes=30)
    db.add(c)
    db.commit()
    return c


def test_plan_de_vuelta_atras_en_el_idioma_pedido_y_releido_en_otro(db, cambio):
    from app.services.service_desk.change_impact_service import generate_rollback_plan, plan_guardado
    plan = generate_rollback_plan(db, cambio.id, idioma="en")
    assert plan["rollback_steps"][0]["action"] == "Stop the deployment if it is in progress"
    assert "Parche del ERP" in plan["rollback_steps"][2]["action"]
    assert "_textos" not in plan["rollback_steps"][0]
    zh = plan_guardado(db, "vuelta", cambio.id, "zh")
    assert zh["rollback_steps"][0]["action"] == texto("cambio.vuelta.1", "zh")
    assert zh["rollback_steps"][5]["responsible"] == "变更经理"


def test_plan_de_pruebas_y_de_comunicaciones_en_ingles(db, cambio):
    from app.services.service_desk.change_impact_service import generate_comms_plan, generate_testing_plan
    pruebas = generate_testing_plan(db, cambio.id, idioma="en")
    primero = pruebas["steps"][0]
    assert primero["description"].startswith("Check the current status of the CIs in the CMDB")
    assert primero["responsible"] == "CMDB administrator"
    assert all("_textos" not in p for p in pruebas["steps"])
    comms = generate_comms_plan(db, cambio.id, idioma="zh")
    # El recordatorio de T-24h a operaciones sale siempre, sea cual sea el riesgo.
    aviso = next(a for a in comms["notifications"]
                 if a["timing"] == "T-24h" and a["audience"] == "IT Operations Team")
    assert aviso["subject"] == texto("cambio.aviso.t24h_operaciones.asunto", "zh", number="CHG-ID1",
                                     title="Parche del ERP")
    assert aviso["audience"] == "IT Operations Team"  # codigo: lo traduce la interfaz
    assert aviso["channel"] == "邮件 + 即时通讯（Slack/Teams）"


def test_resumen_del_impacto_en_el_idioma_pedido(db, cambio):
    from app.services.service_desk.change_impact_service import analyze_change_impact_full, plan_guardado
    informe = analyze_change_impact_full(db, cambio.id, idioma="en")
    assert informe["summary"].startswith("Change 'Parche del ERP' affects")
    assert plan_guardado(db, "impacto", cambio.id, "es")["summary"].startswith("El cambio «Parche del ERP»")


# ── Agente autonomo ──────────────────────────────────────────────────────────

def test_nombre_de_los_playbooks_de_serie_y_propios():
    from app.services.service_desk.autonomous_agent_service import _BUILTIN_PLAYBOOKS, nombre_del_playbook
    pw = next(p for p in _BUILTIN_PLAYBOOKS if p["id"] == "pw-reset")
    assert nombre_del_playbook(pw, "es") == "Restablecer contraseña"
    assert nombre_del_playbook(pw, "zh") == "自助重置密码"
    # El de la empresa sale como lo escribio, aunque coincida el id.
    assert nombre_del_playbook({"id": "x-1", "name": "Mi playbook"}, "en") == "Mi playbook"


def test_paso_de_serie_por_clave_y_propio_tal_cual():
    from app.services.service_desk.autonomous_agent_service import contenido_del_paso
    assert contenido_del_paso({"type": "notify", "clave": "autonomo.pb.slow-pc.notify", "content": "x"},
                              "en") == "Performance ticket: reply sent, pending technical review."
    assert contenido_del_paso({"type": "notify", "content": "Escrito por el admin"}, "en") == "Escrito por el admin"


def test_motivo_p1_en_el_idioma_pedido(db):
    from app.services.service_desk.autonomous_agent_service import evaluate_ticket_for_autonomy
    ticket = SimpleNamespace(priority=SimpleNamespace(value="p1_critical"), organization_id="1")
    r = evaluate_ticket_for_autonomy(db, ticket, "en")
    assert r["reason"] == "P1 tickets always require human review" and r["reason_code"] == "p1"


# ── Bloqueos y cupos que escribe el sistema ─────────────────────────────────

def test_herramienta_sin_politica_en_el_idioma_del_usuario(db):
    from app.models.user import UserPreference
    from app.services.ai_chat.tool_execution.politica import codigo_de_denegacion, denegacion
    db.add(UserPreference(user_id="admin-test-id", language="en"))
    db.commit()
    usuario = SimpleNamespace(id="admin-test-id", organization_id="1", is_superadmin=False, role=None)
    assert codigo_de_denegacion(db, usuario, "no_existe") == (
        "politica.herramienta_sin_politica", {"herramienta": "no_existe"})
    assert denegacion(db, usuario, "no_existe") == "The tool 'no_existe' has no access policy, so it will not run."


def test_bloqueo_de_gobernanza_se_reconoce_en_cualquier_idioma():
    from app.services.ai_provider_service import es_bloqueo_de_entrada
    for idioma in ("es", "en", "zh"):
        assert es_bloqueo_de_entrada(texto("gobernanza.mensaje_bloqueado", idioma, politica="P"))
    assert not es_bloqueo_de_entrada("Hola")
    assert texto("gobernanza.respuesta_bloqueada", "es") == "[Respuesta bloqueada por política de gobernanza]"


def test_cupo_diario_y_cupo_de_ausencias_en_cada_idioma():
    assert "límite diario" in texto("ia.limite_diario", "es", n=5, modulo="m")
    assert texto("ia.limite_diario", "en", n=5, modulo="m").startswith("You have reached the daily limit of 5")
    from app.services.ausencias.solicitudes import _mensaje_de_bloqueo
    assert _mensaje_de_bloqueo(None) == "No queda plaza en el cupo para esas fechas"
    # El mensaje que redacto la empresa sale tal cual.
    assert _mensaje_de_bloqueo({"si_lleno": [{"tipo": "block", "mensaje": "Agosto cerrado"}]}) == "Agosto cerrado"
