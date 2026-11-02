"""Base de conocimiento: acceso, revision, sugerencias y desvios.

Auditoria 2026-11 (medido con un cliente sin cookies): el listado, el detalle y
el voto no pedian login y leian los articulos internos de todas las
organizaciones. A los agentes solo se les listaban los publicados (un borrador
desaparecia), el listado no traia el estado, y no habia revision ni
sugerencias en el portal.
"""
from __future__ import annotations

import pytest

from tests.conftest import auth

KB = "/api/v1/sd/kb"


def _articulo(db, numero="KB-0001", titulo="Reiniciar la VPN corporativa", **extra):
    from app.models.service_desk import KBArticle
    datos = dict(number=numero, title=titulo, body="Abre el cliente VPN y pulsa reconectar.",
                 status="published", is_public=True, organization_id="1")
    datos.update(extra)
    a = KBArticle(**datos)
    db.add(a)
    db.commit()
    return a


def test_sin_login_no_se_lee_ni_se_vota(db):
    from fastapi.testclient import TestClient
    from app.main import app

    a = _articulo(db, is_public=False)
    with TestClient(app) as anonimo:
        assert anonimo.get(f"{KB}?public_only=false").status_code == 401
        assert anonimo.get(f"{KB}/{a.id}").status_code == 401
        assert anonimo.post(f"{KB}/{a.id}/helpful").status_code == 401


def test_el_agente_ve_borradores_y_su_estado(client, admin_token, db):
    _articulo(db, "KB-0001", status="draft")
    _articulo(db, "KB-0002", titulo="Archivado", status="archived")
    items = client.get(KB, headers=auth(admin_token)).json()["items"]
    assert [(i["number"], i["status"]) for i in items] == [("KB-0001", "draft")]


@pytest.fixture()
def con_revision(db):
    from app.models.settings import AppSetting
    from app.services.settings_service import invalidate_cache
    db.add(AppSetting(key="SD_KB_REQUIRE_REVIEW", value="true", organization_id="1"))
    db.commit()
    invalidate_cache("SD_KB_REQUIRE_REVIEW")
    yield
    invalidate_cache("SD_KB_REQUIRE_REVIEW")


def test_con_revision_el_autor_envia_y_el_revisor_publica(client, admin_token, pm_token, db, con_revision):
    r = client.post(KB, headers=auth(pm_token), json={"title": "Cambiar contraseña", "body": "Pasos...", "status": "published"})
    assert r.status_code == 403, "sin ser revisor no se publica directamente"
    aid = client.post(KB, headers=auth(pm_token), json={"title": "Cambiar contraseña", "body": "Pasos..."}).json()["data"]["id"]
    assert client.post(f"{KB}/{aid}/submit", headers=auth(pm_token)).status_code == 200
    assert client.post(f"{KB}/{aid}/review", headers=auth(pm_token), json={"publish": True}).status_code == 403
    assert client.post(f"{KB}/{aid}/review", headers=auth(admin_token), json={"publish": False}).status_code == 422
    assert client.post(f"{KB}/{aid}/review", headers=auth(admin_token), json={"publish": True}).status_code == 200
    items = {i["id"]: i for i in client.get(KB, headers=auth(admin_token)).json()["items"]}
    assert items[aid]["status"] == "published"


def test_el_portal_recibe_sugerencias_publicas_y_cuenta_el_desvio(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.client_portal import ClientUser
    from app.models.service_desk import KBArticle
    from app.services.sla_service import get_client_from_token  # noqa: F401
    from app.core.config import settings
    from jose import jwt

    publico = _articulo(db, "KB-0001")
    _articulo(db, "KB-0002", titulo="VPN: claves internas del concentrador", is_public=False)
    c = ClientUser(id="cli-1", full_name="Ana", email="ana@c.com", organization_id="1", is_active=True)
    db.add(c)
    db.commit()
    token = jwt.encode({"sub": "cli-1", "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")
    with TestClient(app) as portal:
        h = {"Authorization": f"Bearer {token}"}
        r = portal.get(f"{KB}/suggest", params={"q": "no puedo conectar la VPN"}, headers=h)
        assert r.status_code == 200, r.text
        assert [s["number"] for s in r.json()["items"]] == ["KB-0001"], "el interno no sale en el portal"
        assert portal.post(f"{KB}/{publico.id}/deflected", headers=h).status_code == 200
    db.expire_all()
    assert db.get(KBArticle, publico.id).deflection_count == 1


def test_el_vector_se_guarda_y_no_se_recalcula_en_cada_sugerencia(db, monkeypatch):
    from app.services.service_desk import kb_sugerencias

    llamadas = []

    class Modelo:
        def encode(self, textos, **_):
            llamadas.append(len(textos))
            return [[1.0 if "vpn" in t.lower() else 0.0, 1.0] for t in textos]

    monkeypatch.setattr(kb_sugerencias, "_modelo", lambda: Modelo())
    _articulo(db, "KB-0001")
    _articulo(db, "KB-0002", titulo="Impresora atascada", body="Abre la bandeja.")
    kb_sugerencias.sugerir(db, "la vpn falla", solo_publico=False)
    db.commit()
    llamadas.clear()
    kb_sugerencias.sugerir(db, "la vpn falla", solo_publico=False)
    assert llamadas == [1], "solo se codifica la consulta: los articulos ya tienen su vector"
