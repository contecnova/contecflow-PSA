"""Aislamiento cross-tenant de los endpoints que tocan `Organization`.

Contexto (auditoría 2026-08, P0-1). `Organization` es el ÚNICO de los ~391
modelos mapeados sin columna de tenant, así que es el único que `TenantSession`
no puede filtrar automáticamente. Los seis endpoints de `/organizations` estaban
guardados con `require_admin` — que es el rol de administrador *de tenant*, no de
plataforma — de modo que un admin de cualquier cliente podía listar, leer,
renombrar y desactivar la organización de otro.

Este fichero tiene dos capas, a propósito:

1. Tests de comportamiento: reproducen el ataque y exigen 403.
2. Tests de invariante: fallan cuando alguien añade una ruta nueva con `org_id`
   en el path, o un modelo nuevo sin columna de tenant. Cierran la *clase* de
   bug; los del punto 1 solo cierran las instancias conocidas.

`enforce_abac` NO sirve como guarda aquí: es fail-open por diseño (retorna sin
comprobar nada si la organización no tiene políticas activas, que es el estado
por defecto). Ver app/core/abac_enforce.py:67.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.mfa import Organization
from app.models.user import User, UserRole


# ── helpers ───────────────────────────────────────────────────────────────────

def _mk_org(db, name: str) -> Organization:
    org = Organization(
        id=str(uuid.uuid4()),
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        admin_email=f"admin@{uuid.uuid4().hex[:6]}.example",
        plan="enterprise",
        is_active=True,
    )
    db.add(org)
    db.commit()
    return org


def _mk_user(db, org_id: str, *, role=UserRole.admin, superadmin=False) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()),
        username=f"u{suffix}",
        email=f"u{suffix}@example.test",
        full_name=f"User {suffix}",
        hashed_password=get_password_hash("Zx8!qWer4_pl"),
        role=role,
        is_active=True,
        is_superadmin=superadmin,
        organization_id=org_id,
    )
    db.add(user)
    db.commit()
    return user


def _auth(user: User) -> dict:
    token = create_access_token(subject=user.id, extra={"role": user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def two_tenants(db):
    """Tenant atacante (A, con admin) y tenant víctima (B, intacto)."""
    org_a = _mk_org(db, "Tenant A")
    org_b = _mk_org(db, "Tenant B")
    admin_a = _mk_user(db, org_a.id, role=UserRole.admin)
    return org_a, org_b, admin_a


# ── 1. comportamiento: el ataque debe fallar ──────────────────────────────────

def test_tenant_admin_cannot_list_organizations(client, two_tenants):
    _, _, admin_a = two_tenants
    r = client.get("/api/v1/organizations", headers=_auth(admin_a))
    assert r.status_code == 403, (
        f"un admin de tenant no debe poder enumerar organizaciones (recibido {r.status_code})"
    )


def test_tenant_admin_cannot_read_foreign_organization(client, two_tenants):
    _, org_b, admin_a = two_tenants
    r = client.get(f"/api/v1/organizations/{org_b.id}", headers=_auth(admin_a))
    assert r.status_code == 403
    assert "VICTIMA" not in r.text and org_b.slug not in r.text


def test_tenant_admin_cannot_modify_foreign_organization(client, db, two_tenants):
    """El caso grave: PATCH permitía desactivar el tenant ajeno y apagar su MFA."""
    _, org_b, admin_a = two_tenants
    original_name, original_active = org_b.name, org_b.is_active

    r = client.patch(
        f"/api/v1/organizations/{org_b.id}",
        json={"name": "PWNED", "is_active": False, "require_mfa": False},
        headers=_auth(admin_a),
    )
    assert r.status_code == 403

    db.expire_all()
    victim = db.query(Organization).filter(Organization.id == org_b.id).first()
    assert victim.name == original_name, "la organización ajena fue renombrada"
    assert victim.is_active == original_active, "la organización ajena fue desactivada"


def test_tenant_admin_cannot_create_organizations(client, two_tenants):
    _, _, admin_a = two_tenants
    r = client.post(
        "/api/v1/organizations",
        json={"name": "Rogue", "slug": f"rogue-{uuid.uuid4().hex[:6]}"},
        headers=_auth(admin_a),
    )
    assert r.status_code == 403


def test_tenant_admin_cannot_assign_user_to_foreign_organization(client, db, two_tenants):
    org_a, org_b, admin_a = two_tenants
    victim_target = _mk_user(db, org_a.id, role=UserRole.employee)
    r = client.post(
        f"/api/v1/organizations/{org_b.id}/assign-user",
        json={"user_id": victim_target.id},
        headers=_auth(admin_a),
    )
    assert r.status_code == 403


def test_tenant_admin_cannot_remove_user_from_foreign_organization(client, db, two_tenants):
    _, org_b, admin_a = two_tenants
    member_b = _mk_user(db, org_b.id, role=UserRole.employee)
    r = client.delete(
        f"/api/v1/organizations/{org_b.id}/remove-user/{member_b.id}",
        headers=_auth(admin_a),
    )
    assert r.status_code == 403


def test_tenant_admin_cannot_write_foreign_branding(client, db, two_tenants):
    """El SELECT de OrgBranding sí está filtrado, así que una org ajena caía en
    la rama de creación — y el INSERT no lleva filtro de tenant."""
    _, org_b, admin_a = two_tenants
    r = client.put(
        f"/api/v1/orgs/{org_b.id}/branding",
        json={"app_name": "PWNED", "primary_color": "#000000"},
        headers=_auth(admin_a),
    )
    assert r.status_code == 404, f"escritura cross-tenant de branding (recibido {r.status_code})"

    from app.models.white_label import OrgBranding
    db.expire_all()
    leaked = db.query(OrgBranding).filter(OrgBranding.organization_id == org_b.id).first()
    assert leaked is None, "se creó una fila de branding en el tenant ajeno"


def test_tenant_admin_cannot_reset_foreign_branding(client, two_tenants):
    _, org_b, admin_a = two_tenants
    r = client.delete(f"/api/v1/orgs/{org_b.id}/branding", headers=_auth(admin_a))
    assert r.status_code == 404, (
        "reset de branding en org ajena debe fallar de forma explícita, no devolver "
        f"un 204 que aparenta éxito (recibido {r.status_code})"
    )


def test_superadmin_still_has_cross_tenant_access(client, db, two_tenants):
    """Contrapeso: la guarda no debe romper al superadmin, que sí es cross-tenant."""
    org_a, org_b, _ = two_tenants
    root = _mk_user(db, org_a.id, role=UserRole.admin, superadmin=True)

    assert client.get("/api/v1/organizations", headers=_auth(root)).status_code == 200
    assert client.get(f"/api/v1/organizations/{org_b.id}", headers=_auth(root)).status_code == 200


# ── 2. invariantes: cierran la clase de bug, no la instancia ───────────────────

# Modelos sin columna de tenant. TenantSession no puede filtrarlos, así que cada
# entrada necesita justificación explícita y guarda manual en sus endpoints.
MODELS_WITHOUT_TENANT_COLUMN = {
    "Organization": "ES el tenant; guardado con require_superadmin / assert_org_id_is_own",
}

_TENANT_COLUMNS = ("organization_id", "org_id", "project_id", "user_id", "actor_id")


def test_no_new_model_escapes_tenant_filtering():
    """Un modelo sin ninguna columna de tenant es invisible para TenantSession.

    Si este test falla es porque se ha añadido un modelo nuevo que ninguna
    consulta filtrará por organización. Antes de añadirlo al allowlist hay que
    decidir de forma explícita cómo se aísla.
    """
    from app.db.base import Base
    import app.models  # noqa: F401 — registra todos los mappers

    unscoped = {
        m.class_.__name__
        for m in Base.registry.mappers
        if not any(hasattr(m.class_, col) for col in _TENANT_COLUMNS)
    }
    assert unscoped == set(MODELS_WITHOUT_TENANT_COLUMN), (
        "cambió el conjunto de modelos sin columna de tenant.\n"
        f"  esperado: {sorted(MODELS_WITHOUT_TENANT_COLUMN)}\n"
        f"  actual:   {sorted(unscoped)}\n"
        "Un modelo nuevo aquí significa que TenantSession no lo filtra."
    )


# Rutas que aceptan un org_id del cliente. Cada una necesita una guarda porque
# el identificador no viene del token. Valores: guarda esperada.
#   superadmin  → require_superadmin (operación legítimamente cross-tenant)
#   own-org     → assert_org_id_is_own en el cuerpo (operación del propio tenant)
#   machine     → autenticación propia por token de máquina (SCIM, embed)
ORG_ID_ROUTE_GUARDS = {
    ("GET",    "/api/v1/organizations"): "superadmin",
    ("POST",   "/api/v1/organizations"): "superadmin",
    ("GET",    "/api/v1/organizations/{org_id}"): "superadmin",
    ("PATCH",  "/api/v1/organizations/{org_id}"): "superadmin",
    ("POST",   "/api/v1/organizations/{org_id}/assign-user"): "superadmin",
    ("DELETE", "/api/v1/organizations/{org_id}/remove-user/{user_id}"): "superadmin",
    ("GET",    "/api/v1/orgs/{org_id}/branding"): "own-org",
    ("PUT",    "/api/v1/orgs/{org_id}/branding"): "own-org",
    ("DELETE", "/api/v1/orgs/{org_id}/branding"): "own-org",
}


def _routes_taking_client_org_id():
    from app.main import app

    found = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "/scim/" in path:
            continue  # autenticado por token de máquina por-org, ver require_scim_token
        if "{org_id}" in path or path.endswith("/organizations"):
            for method in methods:
                if method in ("HEAD", "OPTIONS"):
                    continue
                found[(method, path)] = route
    return found


def test_every_route_taking_a_client_org_id_is_reviewed():
    """Inventario cerrado: una ruta nueva con `org_id` obliga a decidir su guarda.

    Este es el test que evita la reaparición del bug. Los tests de
    comportamiento de arriba solo cubren las ocho rutas que hoy conocemos.
    """
    actual = set(_routes_taking_client_org_id())
    expected = set(ORG_ID_ROUTE_GUARDS)
    assert actual == expected, (
        "cambió el inventario de rutas que aceptan un org_id del cliente.\n"
        f"  nuevas sin revisar: {sorted(actual - expected)}\n"
        f"  desaparecidas:      {sorted(expected - actual)}\n"
        "Una ruta nueva aquí necesita require_superadmin o assert_org_id_is_own."
    )


def test_superadmin_routes_actually_depend_on_require_superadmin():
    """Comprueba la guarda en el grafo de dependencias, no en el texto del fichero."""
    from app.core.deps import require_superadmin

    routes = _routes_taking_client_org_id()
    for (method, path), guard in ORG_ID_ROUTE_GUARDS.items():
        if guard != "superadmin":
            continue
        route = routes[(method, path)]
        calls = {d.call for d in route.dependant.dependencies}
        assert require_superadmin in calls, (
            f"{method} {path} opera cross-tenant pero no depende de require_superadmin "
            f"(dependencias: {sorted(getattr(c, '__name__', repr(c)) for c in calls)})"
        )
