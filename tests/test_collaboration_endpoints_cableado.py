"""Las rutas de colaboración que el refactor movió y ningún test tocaba.

Auditoría 2026-08 (P3-22, tanda 1). Al mover los 127 puntos de acceso a base de
`endpoints/collaboration/` a la capa de servicio se verificó mucho: ruff limpio,
las 2.029 rutas de la aplicación idénticas a HEAD (método y ruta, comparadas
contra un worktree), el OpenAPI de las 1.574 rutas igual salvo siete
`description`, y cero acceso directo a base comprobado por AST.

**Lo que NO estaba verificado era el cableado de cada endpoint.** Al cruzar las
rutas de colaboración con los tests salió que **20 no las menciona ninguno**, y
nueve de ésas están en ficheros que este refactor reescribió. Los tests que
escribí cubren los *servicios* —el legal hold, el TTL de las URL firmadas, la
suscripción push— y el cableado es justo lo que rompe un refactor: un argumento
en otro orden, un `await` que falta, un modelo de respuesta que ya no encaja.
Nada de eso lo caza un test de servicio.

Así que esto no comprueba lógica de negocio: comprueba que **la ruta responde y
devuelve la forma que promete**. Es barato y cubre la clase de fallo que el
trabajo de mover código introduce de verdad.
"""
from __future__ import annotations

import pytest

from tests.conftest import auth


def _datos(respuesta):
    """El `data` de una `APIResponse`, o los `items` de una `APIListResponse`."""
    cuerpo = respuesta.json()
    assert isinstance(cuerpo, dict), cuerpo
    if "items" in cuerpo:
        return cuerpo["items"]
    return cuerpo.get("data")


# ── Presencia (workspaces.py) ───────────────────────────────────────────────

def test_presencia_se_lista_y_se_actualiza(client, admin_token):
    r = client.get("/api/v1/collaboration/presence", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert isinstance(_datos(r), list)

    r = client.post(
        "/api/v1/collaboration/presence/me",
        headers=auth(admin_token),
        json={"status": "away", "custom_message": "en una reunión"},
    )
    assert r.status_code == 200, r.text
    assert _datos(r)["status"] == "away"

    # Y se ve en el listado, que es lo que prueba que se guardó de verdad.
    r = client.get("/api/v1/collaboration/presence", headers=auth(admin_token))
    estados = {p.get("status") for p in _datos(r)}
    assert "away" in estados


# ── Menciones (messages.py) ─────────────────────────────────────────────────

def test_mis_menciones_responde_una_lista(client, admin_token):
    """La consulta de menciones agrupa los mensajes en UNA consulta; antes era un
    `SELECT` por mención. Sin mensajes la lista es vacía, y eso ya prueba el
    cableado."""
    r = client.get("/api/v1/collaboration/mentions", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert _datos(r) == []


# ── Retención (compliance.py) ───────────────────────────────────────────────

def test_ajustes_de_retencion_van_y_vuelven(client, admin_token):
    r = client.get("/api/v1/collaboration/retention/settings", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    por_defecto = _datos(r)
    assert set(por_defecto) == {"default_months", "max_months"}, por_defecto

    r = client.put(
        "/api/v1/collaboration/retention/settings",
        headers=auth(admin_token),
        json={"default_months": 24, "max_months": 48},
    )
    assert r.status_code == 200, r.text
    assert _datos(r) == {"default_months": 24, "max_months": 48}

    r = client.get("/api/v1/collaboration/retention/settings", headers=auth(admin_token))
    assert _datos(r) == {"default_months": 24, "max_months": 48}


def test_los_ajustes_de_retencion_no_aceptan_cero_meses(client, admin_token):
    """El servicio acota a un mes como mínimo: cero borraría todo al instante.

    Se comprueba **por el endpoint** porque el recorte se hace en el servicio y
    lo que aquí se verifica es que el endpoint pasa por él.
    """
    r = client.put(
        "/api/v1/collaboration/retention/settings",
        headers=auth(admin_token),
        json={"default_months": 0, "max_months": -5},
    )
    assert r.status_code == 200, r.text
    assert _datos(r) == {"default_months": 1, "max_months": 1}


# ── Web Push (admin.py) ─────────────────────────────────────────────────────

def test_suscripcion_push_se_da_de_alta_y_se_borra(client, admin_token):
    cuerpo = {
        "subscription": {
            "endpoint": "https://push.example/cableado",
            "keys": {"p256dh": "clave-p256dh", "auth": "clave-auth"},
        },
        "user_agent": "pytest",
    }
    r = client.post("/api/v1/collaboration/push/subscribe",
                    headers=auth(admin_token), json=cuerpo)
    assert r.status_code == 200, r.text
    assert _datos(r)["ok"] is True
    assert _datos(r)["reasignada"] is False

    r = client.request(
        "DELETE", "/api/v1/collaboration/push/unsubscribe",
        headers=auth(admin_token),
        json={"endpoint": "https://push.example/cableado"},
    )
    assert r.status_code == 200, r.text
    assert _datos(r)["deleted"] == 1


def test_la_suscripcion_push_exige_las_claves(client, admin_token):
    r = client.post(
        "/api/v1/collaboration/push/subscribe",
        headers=auth(admin_token),
        json={"endpoint": "https://push.example/sin-claves"},
    )
    assert r.status_code == 400, r.text


def test_clave_publica_de_push_responde(client, admin_token):
    r = client.get("/api/v1/collaboration/push/public-key", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    datos = _datos(r)
    assert set(datos) >= {"configured", "public_key"}


# ── Bots e integraciones (bots.py) ──────────────────────────────────────────

def test_estado_de_rotacion_de_secretos_responde(client, admin_token):
    r = client.get(
        "/api/v1/collaboration/integrations/security/rotation-status",
        headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert isinstance(_datos(r), dict)


def test_invocar_un_bot_en_una_conversacion_ajena_da_403(client, admin_token):
    """`bots/invoke` comprueba el acceso a la conversación antes de invocar.

    Es lo único que se puede afirmar sin sembrar una conversación entera, y es la
    parte que importa: que la guarda sigue en su sitio después de mover el código.
    """
    r = client.post(
        "/api/v1/collaboration/bots/invoke",
        headers=auth(admin_token),
        json={"bot_handle": "nexus", "conversation_id": "no-existe", "args": "hola"},
    )
    assert r.status_code in (403, 404), r.text


# ── Calendario (admin.py) ───────────────────────────────────────────────────

def test_el_calendario_responde_con_su_ventana(client, admin_token):
    """Sin integraciones activas la lista es vacía, pero `window_days` tiene que
    reflejar lo pedido: es el parámetro que antes se declaraba y no se usaba."""
    r = client.get("/api/v1/collaboration/calendar/events?days=21",
                   headers=auth(admin_token))
    assert r.status_code == 200, r.text
    datos = _datos(r)
    assert datos["window_days"] == 21
    assert datos["events"] == []
    assert datos["providers"] == []


@pytest.mark.parametrize("dias", [0, 61])
def test_el_calendario_rechaza_ventanas_fuera_de_rango(client, admin_token, dias):
    r = client.get(f"/api/v1/collaboration/calendar/events?days={dias}",
                   headers=auth(admin_token))
    assert r.status_code == 422, r.text
