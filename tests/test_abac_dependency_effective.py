"""La cobertura ABAC es EFECTIVA, no declarativa (auditoría 2026-08, P1-5).

El resto de tests de ABAC comprueban estructura: que el mapa esté completo, que
la dependencia esté registrada. Esto comprueba el comportamiento: se define una
política `deny` real y se verifica que la petición se rechaza en una ruta que
ANTES la ignoraba por completo.

Sin este test, "hemos hecho real la cobertura" sería una afirmación sin respaldo.

Contexto: de los 110 prefijos declarados con cobertura ABAC, 45 (261 rutas en 33
ficheros) no tenían ningún endpoint que llamase a `enforce_abac()`. Una política
sobre `invoice` no se aplicaba en /api/v1/invoices — existía en la interfaz y no
hacía nada. `/api/v1/budgets` es uno de esos 45 prefijos y es el que se usa aquí.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.abac_registry import ABAC_COVERED_PREFIXES
from app.models.user import User, UserRole, UserStatus
from app.core.security import create_access_token, get_password_hash
from app.services.abac import ABACService

# Prefijo que ANTES no tenía ninguna llamada a enforce_abac. Si alguien lo saca
# del mapa, el test se salta con un motivo visible en vez de dar un falso verde.
PREFIJO_SIN_COBERTURA_PREVIA = "/api/v1/budgets"


def _role_value(user) -> str:
    """El rol puede venir como enum o como str según si la instancia se refrescó."""
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


@pytest.fixture()
def usuario_org(db):
    """Usuario de la organización de test con rol admin.

    Admin (de tenant), no employee: varias rutas bajo los prefijos de prueba
    tienen su propia guarda RBAC que ya deniega a un employee, y entonces el 403
    vendría del RBAC y no de ABAC — el test no probaría nada. Admin pasa el RBAC,
    así que un 403 sólo puede venir de la política ABAC. No es superadmin, que
    está exento de ABAC por diseño.
    """
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()),
        username=f"abacu{suffix}",
        email=f"abacu{suffix}@example.test",
        full_name="ABAC User",
        role=UserRole.admin,
        status=UserStatus.active,
        is_active=True,
        is_superadmin=False,
        organization_id="1",
        hashed_password=get_password_hash("Kp3!wQzt7_ab"),
        weekly_capacity_hours=40.0,
        currency="EUR",
    )
    db.add(user)
    db.commit()
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, extra={'role': user.role})}"}


def _una_ruta_get_bajo(prefijo: str) -> str | None:
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods:
            continue
        if path == prefijo or path.startswith(prefijo + "/"):
            if "{" in path:
                continue  # evita rutas con parámetros para no depender de datos
            return path
    return None


def test_prefijo_de_prueba_sigue_declarado():
    assert PREFIJO_SIN_COBERTURA_PREVIA in ABAC_COVERED_PREFIXES, (
        f"{PREFIJO_SIN_COBERTURA_PREVIA} ya no está en ABAC_COVERED_PREFIXES; "
        "elige otro prefijo para este test en vez de borrarlo."
    )


def test_sin_politicas_la_peticion_pasa(client, usuario_org):
    """Fail-open: sin políticas activas, ABAC no restringe. Es el estado por defecto."""
    ruta = _una_ruta_get_bajo(PREFIJO_SIN_COBERTURA_PREVIA)
    if ruta is None:
        pytest.skip(f"no hay ruta GET sin parámetros bajo {PREFIJO_SIN_COBERTURA_PREVIA}")
    res = client.get(ruta, headers=_auth(usuario_org))
    assert res.status_code != 403, (
        f"sin políticas ABAC no debe denegarse nada; {ruta} devolvió 403"
    )


def test_una_politica_deny_ahora_SI_se_aplica(client, db, usuario_org):
    """El test que demuestra que la cobertura dejó de ser aspiracional.

    Antes de este cambio la petición pasaba con 200 aunque existiera una política
    `deny` para el resource_type: ninguna ruta bajo /api/v1/budgets llamaba a
    enforce_abac, así que la política no se consultaba nunca.
    """
    ruta = _una_ruta_get_bajo(PREFIJO_SIN_COBERTURA_PREVIA)
    if ruta is None:
        pytest.skip(f"no hay ruta GET sin parámetros bajo {PREFIJO_SIN_COBERTURA_PREVIA}")

    resource_type, _action = ABAC_COVERED_PREFIXES[PREFIJO_SIN_COBERTURA_PREVIA]

    svc = ABACService(db=db, org_id="1")

    # Las reglas ABAC se evalúan contra el almacén de atributos (UserAttribute),
    # NO contra las columnas del modelo User: `evaluate_rules` hace
    # `user_attributes.get(rule["attribute"])`. Una regla sobre "role" no matchea
    # nunca porque el rol no vive ahí. Hay que asignar el atributo primero.
    svc.assign_user_attribute(
        user_id=usuario_org.id,
        attribute_key="region",
        attribute_value="emea",
        assigned_by=usuario_org.id,
        reason="fixture de auditoría",
    )

    svc.create_policy(
        policy_name="Deny presupuestos a EMEA (test de auditoría)",
        rules=[{"attribute": "region", "operator": "equals", "value": "emea"}],
        effect="deny",
        resource_types=[resource_type],
        applicable_roles=[_role_value(usuario_org)],
        priority=99,
    )

    res = client.get(ruta, headers=_auth(usuario_org))
    assert res.status_code == 403, (
        f"con una política deny activa para '{resource_type}', {ruta} debía devolver "
        f"403 y devolvió {res.status_code}. La cobertura ABAC no es efectiva."
    )


def test_el_superadmin_no_queda_atrapado_por_la_politica(client, db, usuario_org):
    """La dependencia no debe encerrar al superadmin: enforce_abac lo exime."""
    ruta = _una_ruta_get_bajo(PREFIJO_SIN_COBERTURA_PREVIA)
    if ruta is None:
        pytest.skip(f"no hay ruta GET sin parámetros bajo {PREFIJO_SIN_COBERTURA_PREVIA}")

    resource_type, _ = ABAC_COVERED_PREFIXES[PREFIJO_SIN_COBERTURA_PREVIA]
    svc = ABACService(db=db, org_id="1")

    root = User(
        id=str(uuid.uuid4()),
        username=f"root{uuid.uuid4().hex[:6]}",
        email=f"root{uuid.uuid4().hex[:6]}@example.test",
        full_name="Root",
        role=UserRole.admin,
        status=UserStatus.active,
        is_active=True,
        is_superadmin=True,
        organization_id="1",
        hashed_password=get_password_hash("Kp3!wQzt7_ab"),
        weekly_capacity_hours=40.0,
        currency="EUR",
    )
    db.add(root)
    db.commit()

    svc.assign_user_attribute(
        user_id=root.id,
        attribute_key="region",
        attribute_value="emea",
        assigned_by=root.id,
        reason="fixture de auditoría",
    )
    svc.create_policy(
        policy_name="Deny total a EMEA (test)",
        rules=[{"attribute": "region", "operator": "equals", "value": "emea"}],
        effect="deny",
        resource_types=[resource_type],
        priority=99,
    )

    res = client.get(ruta, headers=_auth(root))
    assert res.status_code != 403, "el superadmin no debe quedar bloqueado por ABAC"


def test_ruta_publica_sigue_accesible_sin_token(client):
    """La dependencia cuelga de TODO el router v1, incluidas rutas públicas.

    Resuelve el usuario de forma tolerante a propósito: si exigiese autenticación
    rompería login, webhooks y health. Este test fija ese contrato.
    """
    res = client.post("/api/v1/auth/login", json={"username": "no-existe", "password": "x"})
    # Lo que importa es que NO sea un 401/403 producido por la dependencia ABAC
    # antes de llegar al endpoint: el login debe poder ejecutarse y decidir él.
    assert res.status_code in (400, 401, 422), (
        f"la dependencia ABAC no debe interferir con el login; status={res.status_code}"
    )
