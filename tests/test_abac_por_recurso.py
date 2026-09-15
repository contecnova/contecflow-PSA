"""ABAC por recurso concreto: una política puede nombrar la fila que se toca.

Auditoría 2026-09. Toda la API paseaba el `resource_id` hasta el motor de
políticas —233 endpoints— y **el motor no lo miraba**: `evaluate_access` lo
recibía, lo guardaba en el detalle de auditoría y decidía sólo con el rol, el
`resource_type` y los atributos del usuario.

Cómo se descubrió merece quedar escrito, porque es la mejor parte: un test que
iba a demostrar un salto de ABAC en la actualización masiva de tareas **demostró
lo contrario**. La comprobación «por tarea» y la del router daban siempre el
mismo veredicto, y sólo podía ser por una razón — que el `resource_id` no
entraba en la decisión.

Este fichero fija las dos mitades:

  1. que ahora **sí** se puede decidir por la fila concreta, que es lo nuevo;
  2. que una política de las de antes **no cambia de veredicto**, que es lo que
     hace que esto se pueda desplegar sin revisar las políticas de cada cliente.

La segunda importa tanto como la primera. Un cambio en un motor de
autorización que altere en silencio lo que ya estaba decidido es peor que el
hueco que venía a cerrar.
"""
from datetime import date

import pytest

from app.models.abac import ABACPolicy
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services.abac import ABACService
from app.services.abac_recursos import atributos_del_recurso, tipos_soportados


@pytest.fixture()
def org(db):
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    return str(admin.organization_id)


@pytest.fixture()
def proyecto_base(db, org):
    """`tasks.project_id` es NOT NULL, así que toda tarea necesita uno."""
    p = Project(id="p-base-abac", organization_id=org, code="PBASE",
                name="Proyecto de base", project_type=ProjectType.consulting,
                status=ProjectStatus.active)
    db.add(p)
    db.commit()
    return p


def _politica(db, org, *, efecto, reglas, nombre="p", prioridad=50):
    p = ABACPolicy(
        id=f"abac-rec-{nombre}", org_id=org, policy_name=nombre,
        effect=efecto, rules=reglas, resource_types=["task"],
        applicable_roles=[], subject_users=[], priority=prioridad,
        is_active=True,
    )
    db.add(p)
    db.commit()
    return p


def _tarea(db, org, *, titulo, project_id="p-base-abac", estado=TaskStatus.todo):
    t = Task(code=f"TSK-{titulo}", organization_id=org, project_id=project_id,
             title=titulo, status=estado, priority=TaskPriority.medium)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ═══ 1. Los atributos del recurso se resuelven ═══════════════════════════════

def test_los_atributos_de_una_tarea_se_resuelven(db, org, proyecto_base):
    t = _tarea(db, org, titulo="ALFA")
    attrs = atributos_del_recurso(db, "task", t.id)

    assert attrs["recurso.title"] == "ALFA"
    assert attrs["recurso.id"] == t.id
    # Los enumerados se pasan por su valor, que es con lo que compara una regla
    # escrita en JSON.
    assert attrs["recurso.status"] == "todo"


def test_un_tipo_no_declarado_no_expone_nada(db, org, proyecto_base):
    """La superficie está declarada a propósito: es una función de seguridad."""
    t = _tarea(db, org, titulo="BETA")
    assert atributos_del_recurso(db, "tipo_que_no_existe", t.id) == {}
    assert "tipo_que_no_existe" not in tipos_soportados()
    assert "task" in tipos_soportados()


def test_una_fila_que_no_existe_no_revienta(db):
    assert atributos_del_recurso(db, "task", "no-existe") == {}
    assert atributos_del_recurso(db, "task", None) == {}
    assert atributos_del_recurso(db, None, "algo") == {}


def test_las_columnas_que_huelen_a_secreto_no_se_exponen(db, org):
    """`User` tiene `hashed_password`, y una política no tiene por qué verla.

    El valor de una regla acaba en el registro de auditoría, y las políticas las
    edita un administrador de cliente desde la interfaz. Filtrar aquí es más
    barato que confiar en que nadie escriba esa regla.
    """
    attrs = atributos_del_recurso(db, "user", "admin-test-id")
    assert attrs, "el usuario debería resolverse"
    assert not [k for k in attrs if "password" in k or "hash" in k], attrs.keys()


# ═══ 2. Lo nuevo: decidir por la fila concreta ═══════════════════════════════

def test_una_politica_puede_denegar_solo_una_tarea(db, org, proyecto_base):
    """Lo que antes era imposible: «no toques LAS TAREAS DE ESTE PROYECTO»."""
    proyecto = Project(id="p-abac", organization_id=org, code="PABAC",
                       name="Proyecto vetado", project_type=ProjectType.consulting,
                       status=ProjectStatus.active)
    db.add(proyecto)
    db.commit()

    vetada = _tarea(db, org, titulo="VETADA", project_id="p-abac")
    libre = _tarea(db, org, titulo="LIBRE")

    _politica(db, org, efecto="deny", nombre="veto-proyecto", reglas=[
        {"attribute": "recurso.project_id", "operator": "equals", "value": "p-abac"},
    ])

    svc = ABACService(db=db, org_id=org)
    denegada, _, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=vetada.id)
    permitida, matched, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=libre.id)

    assert denegada is False, "la tarea del proyecto vetado tenía que denegarse"
    # La otra no encaja con ninguna política, así que no hay `allow` que la
    # conceda: el motor es fail-open y quien decide es `enforce_abac`, que deja
    # pasar cuando nada ha matcheado. Lo que importa aquí es que **no la denegó**.
    assert matched == [], "ninguna política debería haber encajado con la otra"
    assert permitida is False  # sin allow explícito; ver la nota de arriba


def test_una_politica_puede_depender_de_la_accion(db, org, proyecto_base):
    """«Leer sí, borrar no» tampoco se podía expresar."""
    t = _tarea(db, org, titulo="ACCION")
    _politica(db, org, efecto="deny", nombre="solo-borrar", reglas=[
        {"attribute": "accion", "operator": "equals", "value": "delete"},
    ])

    svc = ABACService(db=db, org_id=org)
    borrando, m_borrar, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=t.id, action="delete")
    leyendo, m_leer, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=t.id, action="read")

    assert borrando is False and m_borrar, "la política tenía que encajar al borrar"
    assert m_leer == [], "y no al leer"


def test_una_regla_sobre_un_recurso_sin_resolver_no_encaja(db, org):
    """Ni para permitir ni para denegar, y se registra.

    Es coherente con que `enforce_abac` sea fail-open por diseño: un id que no
    existe no puede convertirse en una denegación silenciosa de todo.
    """
    _politica(db, org, efecto="deny", nombre="sin-recurso", reglas=[
        {"attribute": "recurso.project_id", "operator": "equals", "value": "p-abac"},
    ])
    svc = ABACService(db=db, org_id=org)
    _, matched, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id="no-existe")
    assert matched == []


# ═══ 3. Lo de antes no cambia, que es lo que permite desplegarlo ════════════

def test_una_politica_de_las_de_antes_no_cambia_de_veredicto(db, org, proyecto_base):
    """Sólo mira atributos de usuario: ve el mismo diccionario que veía.

    Lo único que hace el cambio es **añadir** claves al espacio de nombres de
    evaluación —`recurso.*` y `accion`—, y están prefijadas para que no puedan
    chocar con un atributo de usuario. Una política que no las nombra no puede
    notar la diferencia.
    """
    t = _tarea(db, org, titulo="VIEJA")
    # `rules=[]` encaja siempre: es la política más ancha que el modelo permite
    # expresar, y la que usaban los tests de antes.
    _politica(db, org, efecto="deny", nombre="ancha", reglas=[])

    svc = ABACService(db=db, org_id=org)
    con_id, m1, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=t.id)
    sin_id, m2, _ = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=None)

    assert con_id is False and sin_id is False
    assert m1 == m2, "el veredicto no puede depender de si hay id cuando la regla no lo nombra"


def test_el_detalle_de_auditoria_sigue_llevando_el_recurso(db, org, proyecto_base):
    """No se pierde lo que ya registraba."""
    t = _tarea(db, org, titulo="AUDIT")
    svc = ABACService(db=db, org_id=org)
    _, _, detalle = svc.evaluate_access(
        user_id="admin-test-id", user_roles=["admin"],
        resource_type="task", resource_id=t.id, action="update")
    assert detalle["resource_id"] == t.id
    assert detalle["resource_type"] == "task"
    assert detalle["action"] == "update"


def test_fecha_no_rompe_la_serializacion(db, org, proyecto_base):
    """Una columna de fecha se pasa como texto, no como objeto.

    Una regla se escribe en JSON y compara con un literal, así que el valor
    tiene que llegar en una forma comparable. Es el motivo de que los no
    escalares se conviertan con `str()`.
    """
    t = _tarea(db, org, titulo="FECHA")
    t.due_date = date(2026, 9, 15)
    db.commit()
    attrs = atributos_del_recurso(db, "task", t.id)
    assert attrs["recurso.due_date"] == "2026-09-15"
