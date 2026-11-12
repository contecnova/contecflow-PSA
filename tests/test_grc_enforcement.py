"""La matriz de permisos GRC se aplica de verdad (auditoría 2026-08, hallazgo 27).

Antes de este cambio, GRC era una pantalla de administración que leía y escribía
una tabla que ningún otro punto del sistema consultaba: `check_permission()`
llevaba escrito "Used by other API endpoints to enforce GRC" y tenía cero
invocaciones. Un administrador podía desmarcar "pm puede eliminar proyectos" y el
pm seguía pudiendo eliminarlos.

Estos tests son la diferencia entre decir que está aplicada y demostrarlo: cada
uno comprueba un comportamiento observable por HTTP, no la existencia de código.

El modelo es DENEGACIÓN ADITIVA (ver app/core/grc_enforce.py): una fila sólo
puede quitar permiso, nunca darlo. Se prueban las dos mitades — que una fila
`False` deniega, y que una fila `True` NO promueve por encima del RBAC.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.grc_catalog import action_for, discover_modules, is_exempt, module_for_path
from app.core.security import create_access_token, get_password_hash
from app.models.user import User, UserRole, UserStatus
from app.services import grc_service


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, extra={'role': user.role})}"}


def _mk_user(db, *, role=UserRole.employee, superadmin=False) -> User:
    suf = uuid.uuid4().hex[:8]
    u = User(
        id=str(uuid.uuid4()),
        username=f"grc{suf}",
        email=f"grc{suf}@example.test",
        full_name="GRC Test",
        role=role,
        status=UserStatus.active,
        is_active=True,
        is_superadmin=superadmin,
        organization_id="1",
        hashed_password=get_password_hash("Gr7!cTst9_qp"),
        weekly_capacity_hours=40.0,
        currency="EUR",
    )
    db.add(u)
    db.commit()
    return u


def _deny(db, rol: str, modulo: str, accion: str) -> None:
    grc_service.upsert_permission(db, rol, modulo, accion, allowed=False, updated_by=None)
    db.commit()


def _allow(db, rol: str, modulo: str, accion: str) -> None:
    grc_service.upsert_permission(db, rol, modulo, accion, allowed=True, updated_by=None)
    db.commit()


# ── Derivación del catálogo (sin listas escritas a mano) ──────────────────────

@pytest.mark.parametrize(
    "path,esperado",
    [
        ("/api/v1/invoices", "invoices"),
        ("/api/v1/invoices/{id}/lines", "invoices"),
        ("/api/v2/profitability/summary", "profitability"),
        ("/api/v1/auth/login", None),          # exento: flujo de autenticación
        ("/api/v1/portal/tickets", None),      # exento: principal ClientUser
        ("/api/v1/webhooks/stripe", None),     # exento: HMAC
        ("/health", None),                     # no es ruta de API
    ],
)
def test_el_modulo_se_deriva_del_path(path, esperado):
    assert module_for_path(path) == esperado


@pytest.mark.parametrize(
    "metodo,path,esperado",
    [
        ("GET", "/api/v1/projects", "ver"),
        ("POST", "/api/v1/projects", "crear"),
        ("PATCH", "/api/v1/projects/{id}", "editar"),
        ("PUT", "/api/v1/projects/{id}", "editar"),
        ("DELETE", "/api/v1/projects/{id}", "eliminar"),
        # El path matiza al método: sin esto, la acción `aprobar` de la matriz no
        # se usaría nunca y sería una casilla decorativa.
        ("POST", "/api/v1/approvals/{id}/approve", "aprobar"),
        ("GET", "/api/v1/reports/export", "exportar"),
        ("GET", "/api/v1/invoices/{id}/pdf", "exportar"),
    ],
)
def test_la_accion_se_deriva_del_metodo_y_el_path(metodo, path, esperado):
    assert action_for(metodo, path) == esperado


def test_la_cobertura_alcanza_a_todos_los_dominios_no_exentos():
    """El hallazgo 28 era que la matriz cubría 15 de 126 dominios."""
    from app.main import app

    modulos = discover_modules(app)
    assert len(modulos) > 100, (
        f"el catálogo derivado sólo encuentra {len(modulos)} módulos; se esperaban "
        "más de 100 (los 126 dominios menos los exentos)."
    )
    # Dominios financieramente sensibles que ANTES no tenían ninguna casilla.
    for critico in ("budgets", "revenue-recognition", "profitability", "accounting", "user-costs",
                    "rate-cards", "imputations", "pipeline", "gdpr", "organizations"):
        assert critico in modulos, f"{critico} sigue fuera del catálogo GRC"


def test_los_prefijos_sin_principal_user_quedan_exentos():
    for p in ("/api/v1/auth/login", "/api/v1/portal/x", "/api/v1/webhooks/y",
              "/api/v1/scim/v2/z", "/api/v1/ws/chat"):
        assert is_exempt(p), f"{p} debería estar exento de GRC"


# ── El comportamiento: la matriz deniega ──────────────────────────────────────

def test_una_casilla_en_false_produce_403(client, db):
    """El test que demuestra que la matriz dejó de ser decorativa.

    Antes de este cambio esta misma petición devolvía 200 con la casilla
    desmarcada.
    """
    user = _mk_user(db, role=UserRole.employee)
    res_antes = client.get("/api/v1/projects", headers=_auth(user))
    assert res_antes.status_code != 403, (
        "el empleado ya no podía leer proyectos antes de tocar la matriz; "
        "elige otro módulo para este test"
    )

    _deny(db, "employee", "projects", "ver")
    res = client.get("/api/v1/projects", headers=_auth(user))
    assert res.status_code == 403, (
        f"con projects/ver denegado para employee se esperaba 403, llegó "
        f"{res.status_code}. La matriz no se está aplicando."
    )
    assert "gobierno" in res.json()["detail"].lower(), (
        "el mensaje debe explicar que lo bloquea la política de gobierno, no un "
        "error genérico"
    )


def test_la_denegacion_distingue_la_accion(client, db):
    """Denegar `eliminar` no debe bloquear `ver`."""
    user = _mk_user(db, role=UserRole.employee)
    _deny(db, "employee", "projects", "eliminar")
    _allow(db, "employee", "projects", "ver")
    assert client.get("/api/v1/projects", headers=_auth(user)).status_code != 403


def test_la_denegacion_distingue_el_modulo(client, db):
    """Denegar en `budgets` no debe afectar a `projects`."""
    user = _mk_user(db, role=UserRole.employee)
    _deny(db, "employee", "budgets", "ver")
    _allow(db, "employee", "projects", "ver")
    assert client.get("/api/v1/projects", headers=_auth(user)).status_code != 403


def test_la_denegacion_distingue_el_rol(client, db):
    """Denegar a `employee` no debe afectar a `pm`."""
    pm = _mk_user(db, role=UserRole.pm)
    _deny(db, "employee", "projects", "ver")
    _allow(db, "pm", "projects", "ver")
    assert client.get("/api/v1/projects", headers=_auth(pm)).status_code != 403


# ── El modelo aditivo: una fila True NO promueve ──────────────────────────────

def test_una_casilla_en_true_no_salta_el_rbac(client, db):
    """La mitad del contrato que evita una escalada de privilegios.

    Si `allowed=True` concediera acceso, un administrador de cliente podría
    marcar una casilla y saltarse `require_admin`. La matriz restringe; no
    promueve.
    """
    empleado = _mk_user(db, role=UserRole.employee)
    # /organizations exige superadministrador desde la remediación del P0-1.
    _allow(db, "employee", "organizations", "ver")
    res = client.get("/api/v1/organizations", headers=_auth(empleado))
    assert res.status_code == 403, (
        "una casilla en True no debe conceder acceso por encima del RBAC "
        f"(llegó {res.status_code})"
    )


def test_sin_fila_el_comportamiento_no_cambia(client, db):
    """Módulo sin configurar → deciden los controles de siempre.

    Es la razón por la que sembrar 111 dominios en False habría sido un error:
    cerrar de golpe todo lo no configurado.
    """
    user = _mk_user(db, role=UserRole.employee)
    from app.models.billing_reports import RolePermission

    db.query(RolePermission).filter(
        RolePermission.role == "employee",
        RolePermission.module == "projects",
    ).delete()
    db.commit()
    assert client.get("/api/v1/projects", headers=_auth(user)).status_code != 403


# ── Salvaguardas ─────────────────────────────────────────────────────────────

def test_el_superadmin_nunca_queda_bloqueado(client, db):
    root = _mk_user(db, role=UserRole.admin, superadmin=True)
    _deny(db, "admin", "projects", "ver")
    assert client.get("/api/v1/projects", headers=_auth(root)).status_code != 403


def test_la_matriz_no_puede_cerrarse_a_si_misma(client, db):
    """Sin esta salvaguarda, desmarcar grc/ver dejaría el sistema irreparable.

    El administrador perdería la pantalla desde la que arreglarlo.
    """
    admin = _mk_user(db, role=UserRole.admin)
    _deny(db, "admin", "grc", "ver")
    res = client.get("/api/v1/grc/permissions", headers=_auth(admin))
    assert res.status_code != 403, (
        "un admin se ha quedado sin acceso a la propia matriz de GRC: "
        "el sistema no se podría reparar desde la interfaz"
    )


def test_las_rutas_publicas_siguen_accesibles(client, db):
    """La dependencia cuelga del router completo; no debe pedir autenticación."""
    _deny(db, "employee", "auth", "crear")  # aunque alguien lo intente
    res = client.post("/api/v1/auth/login", json={"username": "nadie", "password": "x"})
    assert res.status_code in (400, 401, 422), (
        f"GRC no debe interferir con el login (status={res.status_code})"
    )


def test_la_dependencia_cuelga_de_todas_las_rutas_de_api():
    """Si este registro desaparece, la matriz vuelve a ser decorativa."""
    from app.core.grc_enforce import enforce_grc_matrix
    from app.main import app

    total = cubiertas = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        if not path.startswith("/api/v") or dependant is None:
            continue
        total += 1
        if any(d.call is enforce_grc_matrix for d in dependant.dependencies):
            cubiertas += 1
    assert total > 0 and cubiertas == total, (
        f"enforce_grc_matrix cuelga de {cubiertas} de {total} rutas de /api/v*"
    )
