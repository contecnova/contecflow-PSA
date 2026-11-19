"""Matriz de permisos: las capacidades coinciden con las guardas reales (19-11-2026).

`app/core/capacidades.py` es la única fuente de los permisos de la pantalla.
Cada capacidad con `sonda` se comprueba contra la API con un usuario de cada
rol base: quien la tiene no recibe 403 (lo que se muestra se puede usar) y,
si la sonda es `estricta`, quien no la tiene sí lo recibe. Además: el
superadmin las tiene todas, un rol personalizado solo quita, `/auth/me` y
`/auth/roles` las publican y no hay roles inventados.
"""
from __future__ import annotations

import json

import pytest

from app.core.capacidades import CAPACIDADES, ETIQUETAS_DE_ROL, ROLES, capacidades_de
from app.core.modulos import MODULOS
from app.core.security import create_access_token
from app.models.advanced_config import CustomRole
from app.models.user import User, UserRole, UserStatus
from tests.conftest import HASH_DE_PRUEBA, auth

#: Usuarios del conftest por rol; el jefe de equipo se crea aquí.
USUARIO_DE_ROL = {
    "admin": "admin-test-id",
    "pm": "pm-test-id",
    "hr": None,  # se busca por nombre
    "employee": None,
    "subcontractor": None,
    "team_lead": "tl-capacidades",
}
NOMBRE_DE_ROL = {"hr": "hr_test", "employee": "dev_test", "subcontractor": "sub_test"}

CON_SONDA = sorted((n, c) for n, c in CAPACIDADES.items() if c.sonda)


def _id_de(db, rol: str) -> str:
    if rol == "team_lead":
        if not db.query(User).filter(User.id == "tl-capacidades").first():
            dev = db.query(User).filter(User.username == "dev_test").first()
            db.add(User(id="tl-capacidades", username="tl_capacidades", email="tl-cap@contecflow.test",
                        full_name="Jefe de equipo", role=UserRole.team_lead, status=UserStatus.active,
                        is_active=True, hashed_password=HASH_DE_PRUEBA, weekly_capacity_hours=40.0,
                        currency="EUR", organization_id=dev.organization_id))
            db.commit()
        return "tl-capacidades"
    if USUARIO_DE_ROL.get(rol):
        return USUARIO_DE_ROL[rol]
    return db.query(User).filter(User.username == NOMBRE_DE_ROL[rol]).first().id


def _token(db, rol: str) -> str:
    return create_access_token(subject=_id_de(db, rol))


# ── Catálogo ─────────────────────────────────────────────────────────────────

def test_los_roles_del_catalogo_existen():
    for nombre, cap in CAPACIDADES.items():
        assert set(cap.roles) <= set(ROLES), nombre
        assert cap.modulo is None or cap.modulo in MODULOS, nombre
    assert set(ROLES) == {r.value for r in UserRole}
    assert set(ETIQUETAS_DE_ROL) == set(ROLES)
    for etiquetas in ETIQUETAS_DE_ROL.values():
        assert set(etiquetas) == {"es", "en", "zh"}


def test_los_nombres_son_area_punto_accion():
    for nombre in CAPACIDADES:
        area, _, accion = nombre.partition(".")
        assert area and accion and nombre == nombre.lower(), nombre


# ── Coinciden con las guardas ────────────────────────────────────────────────

@pytest.mark.parametrize("rol", ROLES)
def test_las_capacidades_coinciden_con_las_guardas(client, db, rol):
    """Con la capacidad, la sonda no da 403; sin ella y sonda estricta, sí."""
    token = _token(db, rol)
    fallos = []
    for nombre, cap in CON_SONDA:
        codigo = client.request(cap.sonda.metodo, cap.sonda.ruta, headers=auth(token)).status_code
        if rol in cap.roles and codigo == 403:
            fallos.append(f"{nombre}: {rol} la tiene y {cap.sonda.ruta} da 403")
        if rol not in cap.roles and cap.sonda.estricta and codigo != 403:
            fallos.append(f"{nombre}: {rol} no la tiene y {cap.sonda.ruta} da {codigo}")
    assert not fallos, "\n".join(fallos)


# ── /auth/me, superadmin, rol personalizado ─────────────────────────────────

def test_me_trae_las_capacidades_del_rol(client, db, pm_token, sub_token):
    pm = client.get("/api/v1/auth/me", headers=auth(pm_token)).json()["capacidades"]
    assert pm == sorted(n for n, c in CAPACIDADES.items() if "pm" in c.roles)
    assert "finanzas.ver" in pm and "org.administrar" not in pm
    sub = client.get("/api/v1/auth/me", headers=auth(sub_token)).json()["capacidades"]
    assert "sd.ver" in sub and "colaboracion.ver" not in sub and "sd.completo" not in sub


def test_el_superadmin_las_tiene_todas(client, superadmin_token):
    me = client.get("/api/v1/auth/me", headers=auth(superadmin_token)).json()
    assert me["capacidades"] == sorted(CAPACIDADES)
    assert "plataforma.empresas" in me["capacidades"]
    r = client.get("/api/v1/auth/capacidades", headers=auth(superadmin_token)).json()
    assert r["capacidades"] == sorted(CAPACIDADES)
    assert {c["id"] for c in r["catalogo"]} == set(CAPACIDADES)


def test_un_admin_de_empresa_no_gestiona_la_plataforma(client, admin_token):
    me = client.get("/api/v1/auth/me", headers=auth(admin_token)).json()["capacidades"]
    assert "plataforma.empresas" not in me and "org.administrar" in me
    assert client.get("/api/v1/organizations", headers=auth(admin_token)).status_code == 403


def test_un_rol_personalizado_solo_quita(client, db, admin_token, pm_token):
    rol = CustomRole(name="PM sin alertas", organization_id="1", is_system=False, is_active=True,
                     module_access=json.dumps({"alerts": False, "projects": False}))
    db.add(rol)
    db.commit()
    r = client.patch("/api/v1/users/pm-test-id", json={"custom_role_id": rol.id}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    caps = client.get("/api/v1/auth/me", headers=auth(pm_token)).json()["capacidades"]
    assert "alertas.ver" not in caps and "proyectos.gestionar" not in caps
    assert "finanzas.ver" in caps  # sin módulo: no la toca
    # Lo que quita, la API lo cierra.
    assert client.get("/api/v1/alerts", headers=auth(pm_token)).status_code == 403
    # Nunca añade: un rol que abre todo no da lo de admin.
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    assert "org.administrar" not in capacidades_de(db, pm)


# ── Roles reales ─────────────────────────────────────────────────────────────

def test_roles_reales_con_etiquetas(client, dev_token):
    r = client.get("/api/v1/auth/roles", headers=auth(dev_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["id"] for i in items] == list(ROLES)
    assert not {"designer", "finance", "developer", "sales", "client"} & {i["id"] for i in items}
    assert all(set(i["etiquetas"]) == {"es", "en", "zh"} for i in items)
    assert [i["id"] for i in items if not i["interno"]] == ["subcontractor"]


def test_roles_y_capacidades_piden_sesion(client):
    assert client.get("/api/v1/auth/roles").status_code == 401
    assert client.get("/api/v1/auth/capacidades").status_code == 401
