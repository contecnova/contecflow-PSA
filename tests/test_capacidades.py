"""Matriz de permisos: las capacidades coinciden con las guardas reales (19-11-2026).

`app/core/capacidades.py` es la única fuente de los permisos de la pantalla.
Cada capacidad con `sonda` se comprueba contra la API con un usuario de cada
rol base: quien la tiene no recibe 403 (lo que se muestra se puede usar) y,
si la sonda es `estricta`, quien no la tiene sí lo recibe. Además: el
superadmin las tiene todas, un rol personalizado solo quita, `/auth/me` y
`/auth/roles` las publican y no hay roles inventados.

23-11-2026 (auditoría 01, M9): toda la API se guarda ya por capacidad. Medido
importando la app: 0 pares guardados solo por rol (antes 1 425), 1 987 con
`requiere_capacidad`; 101 capacidades nuevas sin `modulo` (99 del bloque generado
por `scripts/codemods/guardas_a_capacidades.py`, más `tareas.usar` y
`clientes.dirigir`), así que `test_el_modulo_de_la_capacidad_cubre_su_ruta` no
cambia: 0 rutas fuera. Ver `tests/test_auditoria_2026_11_22_ronda2_nucleo.py`.
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


# ── Guardas por capacidad en la API (19-11-2026) ────────────────────────────

#: Rutas con `requiere_capacidad` cuya capacidad tiene un `modulo` que NO cubre
#: la ruta. Ahí la guarda cierra más que `app.core.modulos.comprobar` (un rol
#: personalizado que cierra el módulo pierde la ruta aunque no esté bajo sus
#: prefijos). Vacío a propósito: entra solo con la decisión escrita.
MODULO_QUE_NO_CUBRE_LA_RUTA: dict[tuple[str, str], str] = {
    # Auditoría 22-11-2026 (A-MP2): los exports de BI a Office llevan ingresos,
    # costes y márgenes; antes bastaba la sesión. Se cierran con `analitica.ver`
    # a propósito, también cuando la empresa cierra el módulo de informes: es el
    # mismo dato que /reports, servido por otro prefijo.
    ("GET", "/api/v1/m365/bi/export/excel"): "BI con importes: misma audiencia que /reports (A-MP2)",
    ("GET", "/api/v1/m365/bi/export/word"): "BI con importes: misma audiencia que /reports (A-MP2)",
}


def _guardas_por_capacidad():
    from app.core.deps import RequiereCapacidad
    from app.main import app

    def _recorrer(dep):
        for d in dep.dependencies:
            if isinstance(d.call, RequiereCapacidad):
                yield d.call
            yield from _recorrer(d)

    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for metodo in sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}) or ["WS"]:
            for guarda in _recorrer(dependant):
                yield metodo, route.path, guarda.capacidad


def test_las_rutas_con_requiere_capacidad_usan_capacidades_conocidas():
    """Por código fuente: literal y del catálogo (los barridos leen el literal)."""
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1] / "app"
    llamada = re.compile(r"\brequiere_capacidad\(([^)]*)\)")
    literal = re.compile(r"""^\s*["']([\w.]+)["']\s*$""")
    malas = []
    for fichero in raiz.rglob("*.py"):
        if fichero.name == "deps.py" and fichero.parent.name == "core":
            continue  # la definición
        for arg in llamada.findall(fichero.read_text(encoding="utf-8")):
            m = literal.match(arg)
            if not m or m.group(1) not in CAPACIDADES:
                malas.append(f"{fichero.relative_to(raiz)}: requiere_capacidad({arg})")
    assert not malas, ("requiere_capacidad necesita una capacidad literal del catálogo "
                       "(app/core/capacidades.py):\n  " + "\n  ".join(malas))


def test_el_modulo_de_la_capacidad_cubre_su_ruta():
    """Una capacidad con `modulo` solo guarda rutas que ese módulo ya cierra.

    Así migrar una guarda de rol a `requiere_capacidad` no cambia quién puede:
    lo que la capacidad quita por módulo, `modulos.comprobar` ya lo cerraba.
    """
    vistas = list(_guardas_por_capacidad())
    assert vistas, "ninguna ruta usa requiere_capacidad"
    fuera = []
    for metodo, ruta, capacidad in vistas:
        assert capacidad in CAPACIDADES, (metodo, ruta, capacidad)
        modulo = CAPACIDADES[capacidad].modulo
        if modulo is None or (metodo, ruta) in MODULO_QUE_NO_CUBRE_LA_RUTA:
            continue
        if set(CAPACIDADES[capacidad].roles) <= {"admin"}:
            continue  # a un admin no se le cierra ningún módulo (`modulos.vetados`)
        if not any(ruta == p or ruta.startswith(p + "/") for p in MODULOS[modulo][0]):
            fuera.append(f"{metodo} {ruta}: {capacidad} (módulo {modulo})")
    assert not fuera, ("Capacidad con módulo en una ruta que el módulo no cubre (cerraría más que "
                       "app.core.modulos.comprobar):\n  " + "\n  ".join(fuera))


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
