"""Paridad de seguridad entre el seed real y los fixtures de test (P1-26).

El hallazgo: los fixtures de `tests/conftest.py` y el seed de
`app/db/seed_parts/core.py` son dos definiciones independientes mantenidas a
mano, y divergían en lo único que importaba. En el seed real `admin` tiene
`is_superadmin=True`; en el conftest, no. Por eso 5 tests usaban `admin_token`
contra los endpoints de `/organizations` y pasaban en verde mientras el
endpoint era explotable entre tenants: validaban una persona que en producción
no existe tal como asumían.

── Lo que este fichero NO hace ───────────────────────────────────────────────
No iguala los fixtures al seed. Sería un error: poner `is_superadmin=True` al
`admin` de test desactiva TODOS los filtros de tenant (ver
app/core/deps.py::get_current_user) y enmascararía fallos de aislamiento en las
1.800 pruebas restantes. Los fixtures deben ser mínimos y controlados.

── Lo que sí hace ────────────────────────────────────────────────────────────
Fija por ambos lados las propiedades de las que depende la seguridad, de modo
que si una cambia el test lo dice en vez de dejar que la suite mienta.
"""
from __future__ import annotations

from app.db.seed_parts.core import default_seed_users


# ── El seed real ──────────────────────────────────────────────────────────────

def test_el_admin_del_seed_es_superadmin_de_plataforma():
    """Si `admin` pierde este flag, /organizations queda inaccesible para todos.

    Los seis endpoints de organizaciones exigen `require_superadmin` desde la
    remediación del P0-1. El único usuario del seed que lo cumple es `admin`.
    """
    usuarios = {u["username"]: u for u in default_seed_users()}
    assert "admin" in usuarios, "el seed debe seguir creando el usuario 'admin'"
    assert usuarios["admin"].get("is_superadmin") is True, (
        "el 'admin' del seed ha dejado de ser superadministrador de plataforma: "
        "nadie podría administrar organizaciones."
    )


def test_solo_hay_un_superadmin_en_el_seed():
    """Un superadmin de más es acceso entre tenants concedido por descuido."""
    superadmins = [u["username"] for u in default_seed_users() if u.get("is_superadmin")]
    assert superadmins == ["admin"], (
        f"se esperaba exactamente un superadministrador ('admin'), hay: {superadmins}"
    )


def test_ningun_usuario_del_seed_se_queda_sin_rol():
    for u in default_seed_users():
        assert u.get("role") is not None, f"{u['username']} no declara rol"


def test_los_usuarios_del_seed_tienen_username_unico():
    nombres = [u["username"] for u in default_seed_users()]
    assert len(nombres) == len(set(nombres)), f"usernames duplicados en el seed: {nombres}"


# ── Los fixtures de test ──────────────────────────────────────────────────────

def test_el_admin_de_test_NO_es_superadmin(db):
    """Contrato deliberado, no un descuido.

    `admin_token` representa a un administrador DE TENANT. Si alguien le pone
    `is_superadmin=True` para "arreglar" un test que da 403, desactivará los
    filtros de tenant en toda la suite y volverá a esconder los fallos de
    aislamiento. Para alcance de plataforma existe `superadmin_token`.
    """
    from app.models.user import User

    admin = db.query(User).filter(User.username == "admin").first()
    assert admin is not None
    assert not admin.is_superadmin, (
        "el 'admin' del fixture se ha vuelto superadmin: eso desactiva el filtro "
        "de tenant en toda la suite. Usa la fixture superadmin_token."
    )


def test_existe_una_fixture_de_superadmin_y_es_superadmin(db, superadmin_token):
    from app.models.user import User

    root = db.query(User).filter(User.username == "superadmin_test").first()
    assert root is not None, "la fixture superadmin_token debe crear el usuario"
    assert root.is_superadmin is True
    assert root.organization_id, "users.organization_id es NOT NULL"


def test_los_usuarios_de_los_fixtures_tienen_organizacion(db):
    """`users.organization_id` es NOT NULL en PostgreSQL.

    Un fixture sin organización pasa en SQLite y revienta en producción.
    """
    from app.models.user import User

    sin_org = [
        u.username
        for u in db.query(User).all()
        if not u.organization_id and not u.is_superadmin
    ]
    assert not sin_org, f"usuarios de fixture sin organización asignada: {sin_org}"


def test_los_roles_de_los_fixtures_cubren_los_niveles_que_usan_los_tests(db):
    """Los fixtures deben ofrecer un actor por nivel de privilegio.

    Sin un actor de cada nivel, los tests acaban reutilizando `admin_token`
    para todo — que es exactamente cómo se coló el P0-1.
    """
    from app.models.user import User, UserRole

    presentes = {
        u.role.value if hasattr(u.role, "value") else str(u.role)
        for u in db.query(User).all()
    }
    for esperado in (UserRole.admin.value, UserRole.pm.value, UserRole.employee.value, UserRole.hr.value):
        assert esperado in presentes, f"los fixtures no ofrecen ningún usuario con rol {esperado}"
