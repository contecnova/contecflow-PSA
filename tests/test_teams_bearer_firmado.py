"""El bearer de Teams se verifica por firma, no sólo por audiencia.

Auditoría 2026-09. El receptor de comandos de Microsoft Teams decodificaba el
cuerpo del JWT **sin verificar nada** y comparaba `aud`/`appid` con
`TEAMS_BOT_APP_ID`. La propia auditoría lo dejó anotado con todas las letras —
«es una comprobación de destinatario, no de emisor: frena un token de otro bot,
no uno fabricado»— y esa nota describía un agujero real:

    el id de aplicación de un bot **no es un secreto**, así que cualquiera que
    lo supiera podía escribir un JWT a mano, sin firmar, y el receptor lo
    aceptaba y ejecutaba el comando.

Este fichero lo fija por el lado que importa: **un token sin firma válida se
rechaza**, y se rechaza aunque la audiencia sea la correcta, que es exactamente
el caso que antes pasaba.
"""
import base64
import json
import time

import pytest

from app.core.config import settings


def _jwt_sin_firmar(payload: dict) -> str:
    """Un JWT con cabecera y cuerpo válidos y una firma inventada.

    Es el token que el receptor aceptaba: bien formado, con la audiencia
    correcta, y sin ninguna firma que lo respalde.
    """
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    cabecera = b64({"alg": "RS256", "typ": "JWT", "kid": "inventado"})
    cuerpo = b64(payload)
    return f"{cabecera}.{cuerpo}.firma-inventada"


@pytest.fixture()
def bot_configurado(monkeypatch):
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_ID", "el-bot-de-pruebas", raising=False)
    return "el-bot-de-pruebas"


def test_EL_HALLAZGO_un_token_sin_firmar_con_la_audiencia_correcta_se_rechaza(
    client, db, bot_configurado
):
    """El caso exacto que antes pasaba.

    Audiencia correcta, emisor correcto, sin caducar — y sin firma. Antes esto
    ejecutaba el comando; ahora devuelve 403.
    """
    token = _jwt_sin_firmar({
        "aud": bot_configurado,
        "iss": settings.TEAMS_BOT_ISSUER,
        "exp": int(time.time()) + 3600,
        "serviceurl": "https://smba.trafficmanager.net/emea/",
    })

    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "quien sea"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 403, (
        "un JWT sin firma válida se aceptaba con sólo acertar el id de "
        "aplicación del bot, que no es un secreto"
    )


def test_tambien_se_rechaza_el_de_otro_bot(client, db, bot_configurado):
    """Lo que la versión anterior sí frenaba tiene que seguir frenándose."""
    token = _jwt_sin_firmar({
        "aud": "otro-bot-distinto",
        "iss": settings.TEAMS_BOT_ISSUER,
        "exp": int(time.time()) + 3600,
    })
    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_sin_cabecera_de_autorizacion_es_401(client, db, bot_configurado):
    """Falta la credencial: 401. Credencial inválida: 403. No es lo mismo."""
    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "x"}},
    )
    assert res.status_code == 401


def test_sin_bot_configurado_el_receptor_no_acepta_nada(client, db, monkeypatch):
    """503 y no 200 silencioso.

    Aceptar comandos sin poder verificar quién los manda sería peor que no
    tener el bot. La excepción es `TESTING=1`, que es como corre la suite, así
    que aquí hay que quitarla para ver el comportamiento real.
    """
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_ID", "", raising=False)
    monkeypatch.setenv("TESTING", "0")
    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "x"}},
    )
    assert res.status_code == 503
    assert "not configured" in (res.json().get("detail") or "").lower()


def test_el_mensaje_de_error_no_dice_por_donde_va(client, db, bot_configurado):
    """Un solo mensaje para todos los modos de fallo.

    Distinguir «firma inválida» de «audiencia equivocada» en la respuesta le
    dice a quien lo intenta qué parte ya tiene bien. El detalle va al registro,
    que es donde sirve.
    """
    caducado = _jwt_sin_firmar({
        "aud": bot_configurado, "iss": settings.TEAMS_BOT_ISSUER,
        "exp": int(time.time()) - 10,
    })
    ajeno = _jwt_sin_firmar({
        "aud": "otro", "iss": settings.TEAMS_BOT_ISSUER,
        "exp": int(time.time()) + 3600,
    })
    mensajes = set()
    for token in (caducado, ajeno):
        r = client.post(
            "/api/v1/integrations-hub/teams/commands",
            json={"text": "ayuda", "from": {"name": "x"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        mensajes.add(r.json().get("detail"))
    assert len(mensajes) == 1, f"el mensaje distingue los casos: {mensajes}"


def test_la_url_de_metadatos_es_configurable():
    """No puede estar a fuego: las nubes soberanas publican en otro dominio.

    Con la URL fija, el bot no se podría desplegar en government cloud ni en la
    de China. Es la misma razón por la que el emisor también es un ajuste.
    """
    assert settings.TEAMS_BOT_OPENID_METADATA_URL.startswith("https://")
    assert settings.TEAMS_BOT_ISSUER.startswith("https://")
