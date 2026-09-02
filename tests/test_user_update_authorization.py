"""La edición de usuarios, y el campo reservado que se podía cambiar uno mismo.

Auditoría 2026-08 (P3-18 + defecto de autorización encontrado de paso).
`update_user_record` era complejidad 23 en cuatro fases.

## El defecto

`PATCH /users/{user_id}` usa `get_current_user`, **no** `require_admin`: una
persona puede editar su propia ficha por ahí, con el esquema **ancho**
(`UserUpdate`). Y los campos se aplicaban con un bucle genérico
(`setattr(user, field, value)` para todo lo enviado), mientras la guarda sólo
protegía `role` y `hourly_rate`.

Quedaba fuera `manager_id`. Y `manager_id` **es una entrada de autorización**: un
paso de aprobación con `approver_type == "manager"` autoriza a quien sea
`requester.manager_id` (`approval_engine/_base.py`), y la plantilla de flujo por
defecto trae ese paso como el primero, llamado «Direct Manager».

Es decir, un empleado podía hacer `PATCH /users/{su_propio_id}` con
`{"manager_id": "..."}` y **elegir quién aprueba sus propias solicitudes**.

Por esa vía se saltaban además las tres validaciones del endpoint dedicado
`PATCH /users/{id}/manager` → `set_manager_record()`, que sí comprueba que el
manager existe, que es de la misma organización y que no se forma un ciclo en la
jerarquía. También quedaba libre `status`.

Es el patrón que atraviesa la auditoría: el control cuidadoso existe, y hay una
segunda vía que lo salta entera.

## El arreglo

Quien no es administrador sólo puede cambiar de su propia ficha los campos que la
propia aplicación declara autoeditables: los de `UserSelfUpdate`, el esquema del
endpoint `/users/me`. Se derivan de ahí y no de una lista escrita a mano — una
lista paralela se separaría al primer campo nuevo, y el que se olvidara quedaría
abierto sin que nada fallara.
"""
from __future__ import annotations

from tests.conftest import auth


# ── El defecto, cerrado ───────────────────────────────────────────────────────

def test_un_empleado_no_puede_elegir_su_propio_manager(client, dev_token, db):
    """El defecto, aislado. Antes del arreglo esto devolvía 200 y cambiaba el
    manager, y con él quién puede aprobar las solicitudes de esa persona."""
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                       json={"manager_id": "pm-test-id"})
    assert res.status_code == 403, res.text
    assert "administrador" in res.json()["detail"]

    from app.models.user import User
    assert db.query(User).filter(User.id == "dev-test-id").first().manager_id != "pm-test-id"


def test_un_empleado_no_puede_cambiar_su_propio_estado(client, dev_token, db):
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                       json={"status": "inactive"})
    assert res.status_code == 403


def test_un_empleado_sigue_sin_poder_cambiar_su_rol_ni_su_tarifa(client, dev_token, db):
    """Lo que la guarda antigua ya protegía, y sigue protegido."""
    for campo, valor in (("role", "admin"), ("hourly_rate", 999.0)):
        res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                           json={campo: valor})
        assert res.status_code == 403, f"{campo}: {res.text}"


def test_el_error_nombra_los_campos_reservados(client, dev_token, db):
    """Para que la persona sepa qué le han rechazado y no adivine."""
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                       json={"manager_id": "pm-test-id", "department": "Ventas"})
    assert res.status_code == 403
    detalle = res.json()["detail"]
    assert "manager_id" in detalle and "department" in detalle


def test_enviar_un_campo_reservado_a_nulo_tampoco_vale(client, dev_token, db):
    """Más estricto que antes, y a propósito.

    La guarda antigua miraba `payload.role is not None`, así que enviar
    `{"role": null}` la pasaba. Ahora cuenta lo *enviado*, no lo enviado con
    valor: borrar tu propio manager también es cambiar quién aprueba tus
    solicitudes.
    """
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                       json={"manager_id": None})
    assert res.status_code == 403


# ── Lo que sí se puede seguir haciendo ────────────────────────────────────────

def test_un_empleado_puede_editar_sus_propios_datos_de_perfil(client, dev_token, db):
    """El arreglo no puede cerrar la autoedición legítima."""
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(dev_token),
                       json={"job_title": "Ingeniera senior", "phone": "600123456"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["job_title"] == "Ingeniera senior"


def test_un_administrador_si_puede_cambiar_el_manager(client, admin_token, db):
    """La restricción es para la autoedición, no para la administración."""
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(admin_token),
                       json={"manager_id": "pm-test-id"})
    assert res.status_code == 200, res.text

    from app.models.user import User
    db.expire_all()
    assert db.query(User).filter(User.id == "dev-test-id").first().manager_id == "pm-test-id"


def test_un_administrador_puede_cambiar_rol_y_tarifa(client, admin_token, db):
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(admin_token),
                       json={"hourly_rate": 55.0})
    assert res.status_code == 200, res.text


def test_nadie_puede_editar_la_ficha_de_otra_persona_sin_ser_admin(client, dev_token, db):
    res = client.patch("/api/v1/users/pm-test-id", headers=auth(dev_token),
                       json={"job_title": "cualquier cosa"})
    assert res.status_code == 403
    assert "permiso" in res.json()["detail"]


def test_el_correo_repetido_se_rechaza(client, admin_token, db):
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(admin_token),
                       json={"email": "pm@contecflow.com"})
    assert res.status_code == 400
    assert "registrado" in res.json()["detail"]


def test_el_correo_se_normaliza_a_minusculas(client, admin_token, db):
    res = client.patch("/api/v1/users/dev-test-id", headers=auth(admin_token),
                       json={"email": "  MAYUSCULAS@Contecflow.COM  "})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["email"] == "mayusculas@contecflow.com"


# ── La propiedad estructural que evita que las dos listas se separen ──────────

def test_los_campos_autoeditables_salen_del_esquema_de_autoedicion():
    """No hay lista paralela. Si alguien añade un campo sensible a `UserUpdate`,
    queda reservado automáticamente; y si lo añade a `UserSelfUpdate`, es porque
    ha decidido que es autoeditable."""
    from app.schemas.users import UserSelfUpdate
    from app.services.user_service import _campos_de_autoedicion

    assert _campos_de_autoedicion() == frozenset(UserSelfUpdate.model_fields)


def test_ningun_campo_de_autorizacion_es_autoeditable():
    """La comprobación que da sentido a todo lo anterior.

    Estos campos deciden accesos o dinero. Si alguno acabara en
    `UserSelfUpdate` —por prisa o por copiar y pegar— este test lo para antes de
    que llegue a producción.
    """
    from app.services.user_service import _campos_de_autoedicion

    reservados = {
        "role",             # el rol es la autorización más directa
        "hourly_rate",      # coste imputado: dinero
        "manager_id",       # autoriza aprobaciones de tipo «manager»
        "status",           # activo/inactivo
        "organization_id",  # el filtro de tenant se apoya en este campo
        "organization_ids",
        "is_superadmin",    # desactiva todos los filtros de tenant
        "department",       # se usa en pasos «any_in_department»
    }
    filtrados = reservados & _campos_de_autoedicion()
    assert not filtrados, f"campos de autorización marcados como autoeditables: {filtrados}"
