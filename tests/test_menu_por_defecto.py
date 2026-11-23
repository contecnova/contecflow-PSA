"""Menú lateral personalizable (23-11-2026): preferencia personal y menú por defecto por rol.

Ver app/services/settings_service/menu_por_defecto.py. La fusión con categorías
y pestañas nuevas y el filtro por permisos se prueban en el frontend
(`frontend/src/permisos/menuPersonal.test.ts`).
"""
import pytest

from app.core.codigos_de_error import ErrorDeDominio
from app.models.enterprise import AuditLog
from app.services.settings_service import menu_por_defecto as menu
from tests.conftest import auth

MENU_EMPLEADO = {
    "version": 1,
    "orden": ["trabajo", "proyectos"],
    "ocultas": {"trabajo": ["/overtime"]},
    "orden_pestanas": {"trabajo": ["/tasks", "/work-dashboard"]},
}


def test_normalizar_tolera_claves_desconocidas_y_duplicados():
    limpio = menu.normalizar_menu({
        "version": 1, "orden": ["trabajo", "trabajo", "ia"], "otra_cosa": 1,
        "ocultas": {"trabajo": ["/tasks", "/tasks"], "ia": []},
    })
    assert limpio == {"version": 1, "orden": ["trabajo", "ia"], "ocultas": {"trabajo": ["/tasks"]},
                      "orden_pestanas": {}}


@pytest.mark.parametrize("malo", [
    "texto", {"orden": "trabajo"}, {"orden": ["Trabajo con espacios"]},
    {"ocultas": {"trabajo": ["sin-barra"]}}, {"version": 0},
])
def test_normalizar_rechaza_formas_no_validas(malo):
    with pytest.raises(ErrorDeDominio):
        menu.normalizar_menu(malo)


def test_por_rol_rechaza_roles_inexistentes():
    with pytest.raises(ErrorDeDominio):
        menu.normalizar_por_rol({"roles": {"designer": MENU_EMPLEADO}})


def test_preferencia_personal_persiste_en_el_servidor(client, admin_token, db):
    h = auth(admin_token)
    res = client.patch("/api/v1/users/me/preferences", json={"extra": {"menu": MENU_EMPLEADO}}, headers=h)
    assert res.status_code == 200
    extra = client.get("/api/v1/users/me/preferences", headers=h).json()["data"]["extra"]
    assert extra["menu"]["orden"] == ["trabajo", "proyectos"]
    assert extra["menu"]["ocultas"] == {"trabajo": ["/overtime"]}
    # Restablecer: la clave a null se borra (vuelve el menú del rol).
    client.patch("/api/v1/users/me/preferences", json={"extra": {"menu": None}}, headers=h)
    extra = client.get("/api/v1/users/me/preferences", headers=h).json()["data"]["extra"] or {}
    assert "menu" not in extra


def test_preferencia_personal_con_forma_mala_da_422(client, admin_token, db):
    res = client.patch("/api/v1/users/me/preferences", json={"extra": {"menu": {"orden": "x"}}},
                       headers=auth(admin_token))
    assert res.status_code == 422


def test_menu_por_defecto_por_rol_y_auditado(client, admin_token, dev_token, db):
    res = client.put("/api/v1/settings/menu-default", json={"roles": {"employee": MENU_EMPLEADO}},
                     headers=auth(admin_token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["roles"]["employee"]["ocultas"] == {"trabajo": ["/overtime"]}
    assert db.query(AuditLog).filter(AuditLog.resource == "menu_por_defecto").count() >= 1

    # El empleado recibe el de su rol; el administrador (sin menú de rol) recibe null.
    mio = client.get("/api/v1/settings/menu-default/mine", headers=auth(dev_token)).json()["data"]
    assert mio is not None and mio["orden"] == ["trabajo", "proyectos"]
    assert client.get("/api/v1/settings/menu-default/mine", headers=auth(admin_token)).json()["data"] is None


def test_menu_por_defecto_solo_lo_cambia_quien_administra(client, dev_token, db):
    res = client.put("/api/v1/settings/menu-default", json={"roles": {"employee": MENU_EMPLEADO}},
                     headers=auth(dev_token))
    assert res.status_code == 403
    assert client.get("/api/v1/settings/menu-default", headers=auth(dev_token)).status_code == 403
