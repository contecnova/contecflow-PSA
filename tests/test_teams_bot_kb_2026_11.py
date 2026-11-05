"""Bot de Teams: contesta con la base de conocimiento y envía la respuesta al Bot Connector (revisión 2026-11).

Sin Azure: la firma del token ya la cubre test_teams_bearer_firmado.py; aquí el
verificador devuelve los claims y las llamadas salientes (token y actividad) se
capturan con un doble de httpx para comprobar su forma exacta.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.service_desk.kb_calidad import KBGap
from app.models.user import User
from app.services import teams_bot
from tests.test_kb_calidad_2026_11 import _articulo

URL = "/api/v1/integrations-hub/teams/commands"
SERVICIO = "https://smba.trafficmanager.net/emea/"


class _Resp:
    def __init__(self, datos=None):
        self._d = datos or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._d


@pytest.fixture
def teams(monkeypatch, db):
    import app.api.v1.endpoints.integrations_hub as hub
    claims = {"serviceurl": SERVICIO}
    monkeypatch.setattr(hub, "_verificar_token_de_teams", lambda request: claims)
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_ID", "app-bot", raising=False)
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_PASSWORD", "secreto", raising=False)
    teams_bot._token.update(valor=None, caduca=0)
    llamadas = []

    def _post(url, **k):
        llamadas.append((url, k))
        return _Resp({"access_token": "tok-123", "expires_in": 3600}) if "oauth2" in url else _Resp()
    monkeypatch.setattr(teams_bot.httpx, "post", _post)
    preguntas = []

    def _ia(db, messages, system=None, **k):
        preguntas.append({"system": system, **k})
        return "Instala el cliente VPN y usa el puerto 443 [KB-0901]."
    monkeypatch.setattr("app.services.ai_provider_service.call_ai", _ia)
    usuario = db.query(User).filter(User.username == "pm_test").one()
    return {"claims": claims, "llamadas": llamadas, "ia": preguntas, "usuario": usuario}


def _actividad(usuario, texto, service_url=SERVICIO):
    return {"type": "message", "id": "act-1", "text": texto, "serviceUrl": service_url,
            "from": {"id": "29:usr", "name": usuario.full_name}, "recipient": {"id": "28:bot", "name": "Contecflow"},
            "conversation": {"id": "a:conv-9"}}


def test_EL_HALLAZGO_contesta_con_la_base_y_envia_la_respuesta_al_conector(client, db, teams):
    _articulo(db)
    r = client.post(URL, json=_actividad(teams["usuario"], "¿Cómo configuro la VPN de la oficina?"))
    assert r.status_code == 200
    texto = r.json()["text"]
    assert "puerto 443" in texto and "Fuentes:\n- [KB-0901] Configurar la VPN de la oficina" in texto
    assert "[KB-0901]" in teams["ia"][0]["system"] and teams["ia"][0]["organization_id"] == teams["usuario"].organization_id
    (url_token, k_token), (url_act, k_act) = teams["llamadas"]
    assert url_token == settings.TEAMS_BOT_TOKEN_URL
    assert k_token["data"] == {"grant_type": "client_credentials", "client_id": "app-bot",
                               "client_secret": "secreto", "scope": settings.TEAMS_BOT_TOKEN_SCOPE}
    assert url_act == "https://smba.trafficmanager.net/emea/v3/conversations/a:conv-9/activities/act-1"
    assert k_act["headers"] == {"Authorization": "Bearer tok-123"}
    enviado = k_act["json"]
    assert enviado["replyToId"] == "act-1" and enviado["text"] == texto
    assert enviado["from"]["id"] == "28:bot" and enviado["recipient"]["id"] == "29:usr"


def test_sin_nada_en_la_base_lo_dice_y_apunta_la_pregunta(client, db, teams):
    r = client.post(URL, json=_actividad(teams["usuario"], "¿Cuál es el horario del comedor de Marte?"))
    assert "No encuentro nada" in r.json()["text"] and teams["ia"] == []
    assert db.query(KBGap).filter(KBGap.source == "teams").count() == 1


def test_un_service_url_distinto_del_token_no_recibe_nada(client, db, teams):
    _articulo(db)
    client.post(URL, json=_actividad(teams["usuario"], "VPN de la oficina", "https://otro.botframework.com/"))
    assert [u for u, _ in teams["llamadas"]] == []


def test_un_dominio_no_permitido_no_recibe_nada_aunque_coincida_con_el_token(client, db, teams):
    _articulo(db)
    teams["claims"]["serviceurl"] = "https://atacante.example/"
    client.post(URL, json=_actividad(teams["usuario"], "VPN de la oficina", "https://atacante.example/"))
    assert teams["llamadas"] == []


def test_los_comandos_siguen_siendo_comandos_y_un_desconocido_no_llega_a_la_base(client, db, teams):
    r = client.post(URL, json=_actividad(teams["usuario"], "ayuda"))
    assert teams["ia"] == [] and r.json()["text"]
    anonimo = _actividad(teams["usuario"], "VPN de la oficina")
    anonimo["from"]["name"] = "Nadie Conocido"
    _articulo(db)
    client.post(URL, json=anonimo)
    assert teams["ia"] == []


def test_se_puede_apagar(client, db, teams):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "ai", "TEAMS_KB_ANSWERS_ENABLED", False, teams["usuario"].organization_id)
    db.commit()
    settings_service.invalidate_cache()
    _articulo(db)
    client.post(URL, json=_actividad(teams["usuario"], "VPN de la oficina"))
    settings_service.invalidate_cache()
    assert teams["ia"] == []
