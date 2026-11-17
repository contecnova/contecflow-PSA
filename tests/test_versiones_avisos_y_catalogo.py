"""Versiones revisables de avisos y catalogo en los idiomas del portal (17-11-2026).

- Las versiones nacen en revision; el portal no las sirve hasta que un revisor
  las publica (sirve la traduccion automatica, marcada).
- Publicada: el portal la sirve en su idioma, sin la marca de automatica.
- Al cambiar el original quedan desactualizadas y se avisa a los revisores.
- Permisos: un PM no genera ni publica; otra empresa no ve el contenido.
"""
import pytest

from app.models.enterprise import Notification
from app.models.traduccion import PortalContentTranslation
from tests.conftest import auth
from tests.test_portal_idiomas_restos_2026_11 import (  # noqa: F401  (fixture `doble`)
    _ajuste, _anuncio, _cliente_del_portal, _entrar, doble,
)

B = "/api/v1/translation/portal-content"


def _usuario(client, db, username, org_id, role="admin"):
    """Un usuario mas (con su sesion): token de acceso."""
    from app.models.user import User, UserRole, UserStatus
    from tests.conftest import HASH_DE_PRUEBA, _TEST_PASSWORD
    u = User(id=f"{username}-id", username=username, email=f"{username}@ejemplo-pvv.com", full_name=username,
             role=UserRole(role), status=UserStatus.active, is_active=True, organization_id=org_id,
             hashed_password=HASH_DE_PRUEBA, weekly_capacity_hours=40.0, currency="EUR")
    db.add(u)
    db.commit()
    r = client.post("/api/v1/auth/login", json={"username": username, "password": _TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return u, r.cookies.get("access_token")


@pytest.fixture
def portal(client, admin_token, db, doble):  # noqa: F811
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PVV", idioma="fr")
    _ajuste(db, cliente.organization_id, "TRANSLATION_ENABLED", "true")
    _ajuste(db, cliente.organization_id, "TRANSLATION_KB_LANGUAGES", "de,fr")
    return email, clave, cliente


def _aviso_del_portal(client, lang):
    items = client.get("/api/v1/sd/announcements", params={"lang": lang}).json()["items"]
    return items


def test_generar_nace_en_revision_y_el_portal_sirve_la_automatica(client, admin_token, db, portal):
    email, clave, _ = portal
    aid = _anuncio(client, admin_token)
    r = client.post(f"{B}/announcement/{aid}/generate", headers=auth(admin_token), json={"languages": ["de"]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["failed"] == [] and [v["status"] for v in d["generated"]] == ["in_review"]
    assert d["generated"][0]["fields"]["title"] == "[de] Mantenimiento el sábado"

    # El revisor la corrige antes de publicar: el portal aun no la ve.
    r = client.patch(f"{B}/announcement/{aid}/de", headers=auth(admin_token),
                     json={"fields": {"title": "Wartung am Samstag"}})
    assert r.status_code == 200 and r.json()["data"]["status"] == "in_review"

    _entrar(client, email, clave)
    a = next(x for x in _aviso_del_portal(client, "de") if x["id"] == aid)
    assert a["title"] == "[de] Mantenimiento el sábado" and a["translated_from"]
    assert not a.get("translation_reviewed")


def test_publicada_la_sirve_el_portal_sin_marca_de_automatica(client, admin_token, db, portal):
    email, clave, _ = portal
    aid = _anuncio(client, admin_token)
    client.post(f"{B}/announcement/{aid}/generate", headers=auth(admin_token), json={"languages": ["de"]})
    client.patch(f"{B}/announcement/{aid}/de", headers=auth(admin_token),
                 json={"fields": {"title": "Wartung am Samstag", "body": "Das Portal ist nicht verfügbar."}})
    r = client.post(f"{B}/announcement/{aid}/de/review", headers=auth(admin_token), json={"publish": True})
    assert r.status_code == 200 and r.json()["data"]["status"] == "published"

    _entrar(client, email, clave)
    a = next(x for x in _aviso_del_portal(client, "de") if x["id"] == aid)
    assert a["title"] == "Wartung am Samstag" and a["body"] == "Das Portal ist nicht verfügbar."
    assert a["translation_reviewed"] is True and "translated_from" not in a
    # Otro idioma sin version publicada: la automatica, como antes.
    a = next(x for x in _aviso_del_portal(client, "fr") if x["id"] == aid)
    assert a["title"] == "[fr] Mantenimiento el sábado" and a["translated_from"]


def test_al_cambiar_el_original_queda_desactualizada_y_se_avisa(client, admin_token, pm_token, db, portal):
    from app.models.user import User
    aid = _anuncio(client, admin_token)
    client.post(f"{B}/announcement/{aid}/generate", headers=auth(admin_token), json={"languages": ["de"]})
    client.post(f"{B}/announcement/{aid}/de/review", headers=auth(admin_token), json={"publish": True})
    # Otro administrador de la empresa: el que recibe el aviso (al autor no se le avisa).
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    otro, _ = _usuario(client, db, "revisora_pvv", admin.organization_id)

    r = client.patch(f"/api/v1/sd/announcements/{aid}", headers=auth(admin_token),
                     json={"title": "Mantenimiento el domingo"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["translations_outdated"] == 1

    v = client.get(f"{B}/announcement/{aid}", headers=auth(admin_token)).json()["data"]["items"][0]
    assert v["outdated"] is True and v["status"] == "published"
    assert db.query(Notification).filter(Notification.user_id == otro.id,
                                         Notification.resource_id == aid).count() == 1
    resumen = client.get(B, headers=auth(admin_token)).json()["data"]
    fila = next(f for f in resumen["items"] if f["content_id"] == aid)
    assert fila["outdated"] == 1 and fila["counts"]["published"] == 1

    # Corregirla la pone al dia (y vuelve a revision).
    v = client.patch(f"{B}/announcement/{aid}/de", headers=auth(admin_token),
                     json={"fields": {"title": "Wartung am Sonntag"}}).json()["data"]
    assert v["outdated"] is False and v["status"] == "in_review"


def test_catalogo_servicio_publicado_dentro_de_su_categoria(client, admin_token, db, portal):
    email, clave, _ = portal
    cat = client.post("/api/v1/sd/catalog/categories", headers=auth(admin_token),
                      json={"name": "Accesos", "description": "Altas y bajas"}).json()["data"]["id"]
    srv = client.post("/api/v1/sd/catalog/services", headers=auth(admin_token), json={
        "category_id": cat, "name": "Alta de usuario", "description": "Crear la cuenta",
        "is_visible_to_clients": True}).json()["data"]["id"]
    client.post(f"{B}/catalog_service/{srv}/generate", headers=auth(admin_token), json={"languages": ["de"]})
    client.patch(f"{B}/catalog_service/{srv}/de", headers=auth(admin_token),
                 json={"fields": {"name": "Benutzer anlegen", "description": "Konto erstellen"}})
    assert client.post(f"{B}/catalog_service/{srv}/de/review", headers=auth(admin_token),
                       json={"publish": True}).status_code == 200

    _entrar(client, email, clave)
    items = client.get("/api/v1/sd/catalog", params={"public_only": True, "lang": "de"}).json()["items"]
    c = next(x for x in items if x["id"] == cat)
    assert c["name"] == "[de] Accesos" and c["translated_from"]          # sin version: automatica
    s = c["services"][0]
    assert s["name"] == "Benutzer anlegen" and s["translation_reviewed"] is True


def test_permisos_pm_no_genera_ni_publica_y_rechazar_pide_motivo(client, admin_token, pm_token, db, portal):
    aid = _anuncio(client, admin_token)
    r = client.post(f"{B}/announcement/{aid}/generate", headers=auth(pm_token), json={"languages": ["de"]})
    assert r.status_code == 403 and r.json()["detail"] == "trad_sin_permiso"
    client.post(f"{B}/announcement/{aid}/generate", headers=auth(admin_token), json={"languages": ["de"]})
    r = client.post(f"{B}/announcement/{aid}/de/review", headers=auth(pm_token), json={"publish": True})
    assert r.status_code == 403
    r = client.post(f"{B}/announcement/{aid}/de/review", headers=auth(admin_token), json={"publish": False})
    assert r.status_code == 422 and r.json()["detail"] == "trad_motivo_obligatorio"
    r = client.post(f"{B}/announcement/{aid}/de/review", headers=auth(admin_token),
                    json={"publish": False, "comment": "Falta el horario"})
    assert r.json()["data"]["status"] == "rejected"
    # Tipo desconocido: lo para la ruta.
    assert client.get(f"{B}/wiki/{aid}", headers=auth(admin_token)).status_code == 422


def test_otra_empresa_no_ve_el_contenido(client, admin_token, db, portal):
    from app.models.mfa import Organization
    aid = _anuncio(client, admin_token)
    db.add(Organization(id="org-pvv-otra", name="Otra SA", slug="otra-sa-pvv"))
    db.commit()
    _, token = _usuario(client, db, "ajeno_pvv", "org-pvv-otra")
    r = client.get(f"{B}/announcement/{aid}", headers=auth(token))
    assert r.status_code == 404
    assert db.query(PortalContentTranslation).count() == 0
