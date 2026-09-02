from datetime import date

from tests.conftest import auth

from app.models.project import ProjectMember, ProjectMemberRole
from app.models.task import Task, TaskPriority, TaskStatus


def _create_project(client, token, code):
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


def test_imputation_rejects_user_not_assigned_when_project_has_members(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-01")

    # Add a different member to enforce membership checks.
    db.add(
        ProjectMember(
            project_id=project_id,
            user_id="pm-test-id",
            role=ProjectMemberRole.lead,
        )
    )
    db.commit()

    res = client.post(
        "/api/v1/imputations",
        headers=auth(dev_token),
        json={
            "project_id": project_id,
            "date": str(date.today()),
            "hours": 2.0,
        },
    )

    assert res.status_code == 403
    assert "no estás asignado" in res.json()["detail"].lower()


def test_imputation_rejects_closed_task_status(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-02")

    task = Task(
        code="TASK-IMPG-02",
        project_id=project_id,
        title="Task cerrada",
        assignee_id="dev-test-id",
        status=TaskStatus.done,
        priority=TaskPriority.medium,
    )
    db.add(task)
    db.commit()

    res = client.post(
        "/api/v1/imputations",
        headers=auth(dev_token),
        json={
            "project_id": project_id,
            "task_id": task.id,
            "date": str(date.today()),
            "hours": 1.0,
        },
    )

    assert res.status_code == 400
    assert "tarea" in res.json()["detail"].lower()


def test_imputation_rejects_duplicate_same_user_task_date(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-03")

    task = Task(
        code="TASK-IMPG-03",
        project_id=project_id,
        title="Task duplicados",
        assignee_id="dev-test-id",
        status=TaskStatus.in_progress,
        priority=TaskPriority.medium,
    )
    db.add(task)
    db.commit()

    payload = {
        "project_id": project_id,
        "task_id": task.id,
        "date": str(date.today()),
        "hours": 1.5,
    }

    first = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert first.status_code in (200, 201), first.text

    second = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert second.status_code == 409
    assert "ya existe" in second.json()["detail"].lower()


def test_imputation_rejects_duplicate_no_task_same_project_date(client, admin_token, dev_token, db):
    """When task_id is None the unique index doesn't protect (NULL != NULL); app must block."""
    project_id = _create_project(client, admin_token, "IMPG-04")

    # Add dev user as a member so the membership check passes (no task assignee to rely on).
    db.add(
        ProjectMember(
            project_id=project_id,
            user_id="dev-test-id",
            role=ProjectMemberRole.developer,
        )
    )
    db.commit()

    payload = {
        "project_id": project_id,
        "date": str(date.today()),
        "hours": 2.0,
    }

    first = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert first.status_code in (200, 201), first.text

    second = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert second.status_code == 409
    assert "ya existe" in second.json()["detail"].lower()


# ── El ORDEN de las validaciones (auditoría 2026-08, P3-18) ───────────────────
#
# `validate_and_create_imputation` era complejidad 20 y se partió en nueve
# reglas con nombre. El orden en que se aplican decide QUÉ error ve la persona
# cuando incumple dos a la vez, así que es contrato y no casualidad — pero no
# tenía ni un test, y reordenar las llamadas del orquestador es exactamente el
# error fácil de cometer al mover este código.

def test_el_tope_diario_gana_al_duplicado(client, admin_token, dev_token, db):
    """La única prioridad que el código original ya documentaba en un comentario.

    Con una imputación de 20 h ya registrada, una segunda de 6 h sobre la MISMA
    tarea y fecha incumple dos reglas: pasa de 24 h y es duplicada. Tiene que
    responder 400 y no 409.

    Importa porque los dos errores no son igual de graves: el 409 es recuperable
    con `force_duplicate`, y si ganara, la persona podría forzarlo y colar un día
    de 26 horas.
    """
    project_id = _create_project(client, admin_token, "IMPG-ORD1")
    task = Task(
        code="TASK-IMPG-ORD1",
        project_id=project_id,
        title="Task tope diario",
        assignee_id="dev-test-id",
        status=TaskStatus.in_progress,
        priority=TaskPriority.medium,
    )
    db.add(task)
    db.commit()

    base = {"project_id": project_id, "task_id": task.id, "date": str(date.today())}
    primera = client.post("/api/v1/imputations", headers=auth(dev_token),
                          json={**base, "hours": 20.0})
    assert primera.status_code in (200, 201), primera.text

    segunda = client.post("/api/v1/imputations", headers=auth(dev_token),
                          json={**base, "hours": 6.0})
    assert segunda.status_code == 400, (
        f"esperado 400 por tope diario, salió {segunda.status_code}: {segunda.text}"
    )
    assert "24h" in segunda.json()["detail"]


def test_el_proyecto_inexistente_gana_a_todo_lo_demas(client, dev_token, db):
    """Un proyecto que no existe (o que es de otra organización) responde 404
    antes de comprobar cualquier regla de negocio.

    Y responde 404 y no 403 a propósito: un 403 confirmaría que ese proyecto
    existe en otra organización, que es la fuga que cerró la auditoría #62.
    """
    res = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": "no-existe-este-proyecto",
        "date": str(date.today()), "hours": 2.0,
    })
    assert res.status_code == 404, res.text
    assert res.json()["detail"] == "Proyecto no encontrado"


def test_el_esquema_rechaza_mas_de_24h_en_una_sola_imputacion(client, dev_token, db):
    """Una capa por delante del tope diario, y conviene saber que está ahí.

    `hours` lleva `le=24` en el esquema, así que una imputación individual de más
    de 24 h responde **422** y no llega al servicio. El tope diario de
    `_validar_tope_diario` cubre el otro caso: varias imputaciones que sumadas
    pasan de 24 h, que el esquema no puede ver porque sólo mira una.
    """
    res = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": "cualquiera", "date": str(date.today()), "hours": 99.0,
    })
    assert res.status_code == 422


def test_una_tarea_de_otro_proyecto_no_cuela(client, admin_token, dev_token, db):
    """El filtro por `project_id` al buscar la tarea. Sin él se podrían imputar
    horas a la tarea de un proyecto declarando otro."""
    proyecto_a = _create_project(client, admin_token, "IMPG-ORD2A")
    proyecto_b = _create_project(client, admin_token, "IMPG-ORD2B")
    task_a = Task(
        code="TASK-IMPG-ORD2A",
        project_id=proyecto_a,
        title="Task del proyecto A",
        assignee_id="dev-test-id",
        status=TaskStatus.in_progress,
        priority=TaskPriority.medium,
    )
    db.add(task_a)
    db.commit()

    res = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": proyecto_b, "task_id": task_a.id,
        "date": str(date.today()), "hours": 1.0,
    })
    assert res.status_code == 404
    assert "no pertenece al proyecto" in res.json()["detail"]


def test_el_orquestador_aplica_las_reglas_en_el_orden_declarado():
    """Fija el orden leyéndolo del código, no ejecutándolo.

    Los tests de arriba comprueban las prioridades que se pueden provocar por
    HTTP. Éste cubre las que no —montar un usuario sin tarifa y a la vez con el
    periodo cerrado y a la vez sin pertenencia al proyecto es un fixture
    inmanejable— comprobando la secuencia de llamadas del orquestador.

    Es un test de estructura y lo dice: no verifica que cada regla funcione, sino
    que nadie las reordene sin querer al tocar la función.
    """
    import inspect
    from app.services import imputation_service

    fuente = inspect.getsource(imputation_service.validate_and_create_imputation)
    esperado = [
        "_validar_fecha_imputable",
        "_buscar_proyecto_del_usuario",
        "_buscar_tarea_del_proyecto",
        "_assert_project_membership",
        "_validar_estado_del_proyecto",
        "_validar_tarifa_horaria",
        "_validar_tope_diario",
        "_validar_estado_de_la_tarea",
        "_id_de_imputacion_duplicada",
        "_validar_tope_semanal",
        "_crear_imputacion",
    ]
    posiciones = []
    for nombre in esperado:
        i = fuente.find(nombre)
        assert i >= 0, f"{nombre} ya no se llama desde el orquestador"
        posiciones.append(i)
    assert posiciones == sorted(posiciones), (
        "el orden de las reglas ha cambiado; esperado:\n  " + "\n  ".join(esperado)
    )
