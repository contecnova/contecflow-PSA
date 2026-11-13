"""GET/PATCH /settings/general sin fugas ni escrituras globales.

Auditoria 2026-11: cualquier usuario con sesion leia todas las filas de
`app_settings` en claro (tokens de DocuSign/Adobe, anillo de claves JWT), y un
administrador de organizacion que cambiaba un ajuste sin fila propia
cambiaba el GLOBAL, el de todas las organizaciones.
"""
from __future__ import annotations

from tests.conftest import auth, fila_global

URL = "/api/v1/settings/general"


def _sembrar(db):
    from app.models.settings import AppSetting
    with fila_global(db):
        db.add(AppSetting(key="esign.docusign_access_token", value="tok-SECRETO", organization_id=None))
        db.add(AppSetting(key="security.jwt_keyring", value='{"keys": "enc"}', organization_id=None))
        db.add(AppSetting(key="idle_timeout_minutes", value="30", organization_id=None))
        db.commit()


def test_un_empleado_solo_ve_los_ajustes_generales_y_ningun_secreto(client, dev_token, db):
    _sembrar(db)
    filas = client.get(URL, headers=auth(dev_token)).json()["items"]
    claves = {f["key"] for f in filas}
    assert "idle_timeout_minutes" in claves, "el tiempo de inactividad lo necesitan todos"
    assert not any("." in k for k in claves), claves
    assert "tok-SECRETO" not in str(filas)


def test_el_administrador_ve_el_estado_interno_pero_enmascarado(client, superadmin_token, admin_token, db):
    _sembrar(db)
    filas = {f["key"]: f["value"] for f in client.get(URL, headers=auth(superadmin_token)).json()["items"]}
    assert filas["esign.docusign_access_token"] == "••••••••"
    assert filas["security.jwt_keyring"] == "••••••••"
    assert filas["idle_timeout_minutes"] == "30"
    # Revision multitenant 2026-11b: el estado interno GLOBAL es de la
    # plataforma; el administrador de una empresa no lo ve (ni enmascarado).
    filas = {f["key"]: f["value"] for f in client.get(URL, headers=auth(admin_token)).json()["items"]}
    assert "security.jwt_keyring" not in filas and "esign.docusign_access_token" not in filas
    assert filas["idle_timeout_minutes"] == "30"


def test_un_admin_de_organizacion_no_cambia_el_ajuste_global(client, admin_token, db):
    from app.models.settings import AppSetting
    _sembrar(db)
    r = client.patch(f"{URL}/idle_timeout_minutes", headers=auth(admin_token), json={"value": "5"})
    assert r.status_code == 200, r.text
    db.expire_all()
    global_ = db.query(AppSetting).filter_by(key="idle_timeout_minutes", organization_id=None).one()
    assert global_.value == "30", "ha cambiado el ajuste de todas las organizaciones"
    propio = db.query(AppSetting).filter(AppSetting.key == "idle_timeout_minutes",
                                         AppSetting.organization_id.isnot(None)).one()
    assert propio.value == "5"


def test_por_la_api_general_no_se_escribe_estado_interno(client, admin_token, db):
    _sembrar(db)
    r = client.patch(f"{URL}/security.jwt_keyring", headers=auth(admin_token), json={"value": "x"})
    assert r.status_code == 403
