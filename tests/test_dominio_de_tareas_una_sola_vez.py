"""El dominio de tareas, implementado una sola vez.

Auditoría 2026-08 (hallazgo 18). `app/services/task_service.py` y el subpaquete
`app/services/tasks/` implementaban lo mismo dos veces: cuatro funciones
duplicadas y una clase `TaskService` de 387 líneas que no llamaba nadie. Y las
copias **no eran iguales**, que es lo que pasa siempre:

* `bulk_update_tasks` había perdido la llamada a `enforce_abac`;
* `_TASK_VALID_TRANSITIONS` no permitía `todo → done` en una copia y sí en la
  otra —la que se ejecutaba—;
* la clase muerta era la versión de antes de los arreglos de tenant (#62): sus
  búsquedas por id no acotaban por `Project.organization_id`.

Este fichero comprueba las dos cosas que hacen falta: que **no hay dos copias**
y que la ruta masiva sigue haciendo lo que debe.
"""
import inspect

import pytest

from app.models.abac import ABACPolicy
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from tests.conftest import auth


def _proyecto(client, token, code):
    res = client.post(
        "/api/v1/projects",
        json={
            "name": f"Proyecto {code}",
            "code": code,
            "status": "active",
            "billing_type": "time_material",
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


def _tarea(db, project_id, code):
    tarea = Task(
        code=code,
        project_id=project_id,
        title=f"Tarea {code}",
        assignee_id="dev-test-id",
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    return tarea


def _politica_de_denegacion(db):
    """Una política `deny` activa sobre `task` para toda la organización.

    `rules=[]` evalúa a cierto —`evaluate_rules` recorre la lista y devuelve
    `True` si no queda ninguna sin cumplir— y con `applicable_roles` vacío
    aplica a cualquier rol: es la denegación más ancha que el modelo permite
    expresar.

    Hace falta una fila porque `enforce_abac` sale antes de tiempo si la
    organización no tiene ninguna política activa. Es fail-open a propósito y su
    cabecera lo dice; sin esta fila no habría nada que evaluar y el test no
    probaría nada.
    """
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    assert admin is not None
    db.add(ABACPolicy(
        id="abac-tareas-deny",
        org_id=str(admin.organization_id),
        policy_name="Denegar tareas en la auditoría 18",
        effect="deny",
        rules=[],
        resource_types=["task"],
        applicable_roles=[],
        subject_users=[],
        priority=90,
        is_active=True,
    ))
    db.commit()


# ═══ 1. No hay dos copias ════════════════════════════════════════════════════

PAREJAS = [
    ("bulk_update_tasks", "app.services.tasks.bulk"),
    ("validate_task_transition", "app.services.tasks.core"),
    ("apply_status_side_effects", "app.services.tasks.core"),
    ("_TASK_VALID_TRANSITIONS", "app.services.tasks.core"),
    ("cascade_reschedule", "app.services.tasks.scheduling"),
]


@pytest.mark.parametrize("nombre,modulo", PAREJAS)
def test_task_service_reexporta_y_no_copia(nombre, modulo):
    """Lo de `task_service` y lo del subpaquete tienen que ser **el mismo objeto**.

    `is` y no `==`: dos funciones con el mismo cuerpo son iguales para cualquier
    comparación razonable y siguen siendo dos sitios donde arreglar el mismo
    defecto. Sólo la identidad demuestra que no se ha vuelto a copiar.
    """
    import importlib

    from app.services import task_service

    origen = importlib.import_module(modulo)
    assert getattr(task_service, nombre) is getattr(origen, nombre), (
        f"`task_service.{nombre}` ha vuelto a ser una copia local de la de "
        f"`{modulo}`. Las dos divergen en cuanto alguien arregla una sola."
    )


def test_la_clase_taskservice_no_ha_vuelto():
    """387 líneas de dominio de tareas sin un solo sitio de llamada.

    Era la versión de antes de los arreglos de tenant y de ABAC: sus búsquedas
    por id no acotaban por organización. Si reaparece, vuelve el problema.
    """
    from app.services import tasks
    from app.services.tasks import core

    assert not hasattr(core, "TaskService")
    assert not hasattr(tasks, "TaskService")
    assert "TaskService" not in getattr(tasks, "__all__", [])


def test_la_transicion_viva_se_conserva():
    """`todo → done` estaba permitida en la copia viva y prohibida en la otra.

    Se unificó en la viva a propósito: marcar hecha una tarea pequeña sin pasar
    por `in_progress` es el gesto normal de un tablero, y cambiar eso en
    producción es una decisión de producto, no un arreglo de auditoría.
    """
    from app.services.task_service import _TASK_VALID_TRANSITIONS

    assert TaskStatus.done in _TASK_VALID_TRANSITIONS[TaskStatus.todo]
    assert _TASK_VALID_TRANSITIONS[TaskStatus.cancelled] == set(), "cancelled es terminal"
    assert TaskStatus.in_review not in _TASK_VALID_TRANSITIONS[TaskStatus.todo]


def test_la_ruta_masiva_evalua_abac():
    """La comprobación por tarea tiene que seguir en el código que se ejecuta.

    Se comprueba sobre el fuente y no por comportamiento, y la razón merece
    quedar escrita: **no se puede observar desde fuera**. Con una política
    `deny` activa, la dependencia ABAC de los routers ya devuelve 403 antes de
    llegar al manejador, porque `evaluate_access` **no mira el `resource_id`** y
    por tanto da el mismo veredicto con id y sin él. La comprobación de dentro
    no puede denegar nada que el router haya dejado pasar.

    Es decir: lo que la copia había perdido era código de autorización latente,
    no una brecha. Se exige igual —una comprobación que debería estar es un
    defecto aunque hoy la tape otra capa—, pero se exige por lo que es, y por
    eso este test mira el fuente en vez de fingir un escenario que no existe.
    """
    from app.services.task_service import bulk_update_tasks

    fuente = inspect.getsource(bulk_update_tasks)
    assert "enforce_abac(" in fuente
    assert "abac_denied" in fuente
    # El `continue` va DESPUÉS del skipped y ANTES de los efectos de estado.
    assert fuente.index("abac_denied") < fuente.index("apply_status_side_effects")


# ═══ 2. La ruta masiva sigue funcionando ═════════════════════════════════════

def test_bulk_update_funciona_sin_politicas(client, admin_token, db):
    """El control. Sin él, un endpoint que denegase siempre pasaría los tests."""
    pid = _proyecto(client, admin_token, "TAREAS-01")
    tarea = _tarea(db, pid, "TSK-TAREAS-01")

    res = client.post(
        "/api/v1/tasks/bulk-update",
        headers=auth(admin_token),
        json={"task_ids": [tarea.id], "status": "in_progress"},
    )
    assert res.status_code == 200, res.text
    datos = res.json()["data"]
    assert datos["updated"] == 1
    assert datos["skipped"] == []

    db.expire_all()
    assert db.query(Task).filter(Task.id == tarea.id).first().status == TaskStatus.in_progress


def test_una_denegacion_abac_para_la_ruta_masiva(client, admin_token, db):
    """Con política `deny`, no se escribe. Lo para el router, y da igual quién:

    lo que este test fija es que **la escritura no ocurre**, que es la propiedad
    que le importa a un cliente. Qué capa la para es un detalle de implementación
    y está documentado en `test_la_ruta_masiva_evalua_abac`.
    """
    pid = _proyecto(client, admin_token, "TAREAS-02")
    tarea = _tarea(db, pid, "TSK-TAREAS-02")
    _politica_de_denegacion(db)

    res = client.post(
        "/api/v1/tasks/bulk-update",
        headers=auth(admin_token),
        json={"task_ids": [tarea.id], "status": "in_progress"},
    )
    assert res.status_code == 403, res.text

    db.expire_all()
    sin_tocar = db.query(Task).filter(Task.id == tarea.id).first()
    assert sin_tocar.status == TaskStatus.todo
    assert sin_tocar.started_at is None


def test_el_motor_abac_ignora_el_resource_id(db):
    """Fija el defecto que la deduplicación dejó a la vista, para que no se olvide.

    `ABACService.evaluate_access` recibe `resource_id`, lo guarda en el detalle
    de auditoría y **no lo usa para decidir**. Dos tareas distintas dan el mismo
    veredicto, así que **ABAC por recurso concreto no está implementado**, por
    mucho que la API pasee el id por seis capas hasta el motor.

    Este test pasa porque hoy es así, no porque esté bien. Arreglarlo exige
    resolver atributos del recurso —diseño de producto— y cuando se haga, este
    test tiene que fallar y cambiarse a mano. Eso es exactamente lo que se
    quiere: que la decisión sea deliberada y no un descubrimiento.
    """
    from app.services.abac import ABACService

    admin = db.query(User).filter(User.id == "admin-test-id").first()
    _politica_de_denegacion(db)
    svc = ABACService(db=db, org_id=str(admin.organization_id))

    a, _, _ = svc.evaluate_access(
        user_id=str(admin.id), user_roles=["admin"],
        resource_type="task", resource_id="tarea-cualquiera-A")
    b, _, _ = svc.evaluate_access(
        user_id=str(admin.id), user_roles=["admin"],
        resource_type="task", resource_id="tarea-cualquiera-B")

    assert a is b is False, (
        "el veredicto ha dejado de ser independiente del `resource_id`: si es "
        "porque se ha implementado ABAC por recurso, actualiza este test y la "
        "nota de `app/core/abac_dependency.py`"
    )
