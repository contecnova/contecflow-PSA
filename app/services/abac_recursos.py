"""Los atributos del recurso concreto, para que ABAC pueda decidir con ellos.

Auditoría 2026-09. Toda la API pasea un `resource_id` hasta el motor de
políticas —`enforce_abac(db, user, "task", task.id, action="update")`, en 233
endpoints— y **el motor no lo miraba**: `ABACService.evaluate_access` lo recibía,
lo guardaba en el detalle de auditoría y decidía sólo con el rol, el
`resource_type` y los atributos del usuario. `is_policy_applicable` ni siquiera
lo aceptaba.

Consecuencia: **ABAC por recurso concreto no existía**. Una política sólo podía
decir «los de este rol no tocan tareas», nunca «no tocan las tareas del proyecto
X». Y la diferencia no es académica: se descubrió porque un test que iba a
demostrar un salto de ABAC en la actualización masiva de tareas demostró lo
contrario — la comprobación «por tarea» y la del router daban **siempre el mismo
veredicto**, así que una de las dos sobraba.

Este módulo es la mitad que faltaba: dado un `(resource_type, resource_id)`,
devuelve los atributos de esa fila para que una regla pueda nombrarlos.

## La superficie está declarada, y eso es a propósito

`TIPOS` es un mapa explícito de tipo de recurso a modelo. **No** se descubre
automáticamente recorriendo el registro de SQLAlchemy, aunque se podría: esto es
una función de seguridad, y en seguridad la superficie se declara. Añadir un
tipo es una línea, y esa línea es la decisión de exponer ese modelo a las
políticas.

## Qué columnas se exponen, y cuáles no

Las escalares de la fila, con el prefijo `recurso.` para que no puedan chocar
con un atributo de usuario. Se excluyen las que huelen a secreto —cualquier
nombre con `password`, `token`, `secret`, `key`, `hash`— porque una política ABAC
es un objeto que un administrador de cliente edita desde la interfaz, y el valor
de una regla acaba en el registro de auditoría. Filtrarlas aquí es más barato
que confiar en que nadie escriba esa regla.

## Si el recurso no se puede resolver

Se devuelve `{}` y quien evalúa lo registra. Una regla que nombra
`recurso.algo` con el recurso sin resolver **no encaja**, ni para permitir ni
para denegar. Es coherente con que `enforce_abac` sea fail-open por diseño —lo
dice su propia cabecera— y con no convertir un id que no existe en una
denegación silenciosa de todo.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("contecflow.abac.recursos")

#: Prefijo de los atributos del recurso en el espacio de nombres de las reglas.
PREFIJO = "recurso."

#: Trozos de nombre de columna que nunca se exponen a una política.
_NUNCA = ("password", "token", "secret", "key", "hash", "salt", "credential")


def _modelos() -> Dict[str, Any]:
    """El mapa de tipo de recurso a clase mapeada.

    Se construye perezosamente porque importar los modelos en la cabecera de
    este módulo crearía un ciclo: `app.services.abac` ya los importa.

    Los tipos son los que la API pasa hoy con un `resource_id` concreto,
    medidos sobre las llamadas a `enforce_abac`. Añadir uno es una línea.
    """
    from app.models.clients import Client
    from app.models.documents import Document
    from app.models.epics import Epic
    from app.models.expenses import Expense
    from app.models.project import Project
    from app.models.sprints import Sprint
    from app.models.task import Task
    from app.models.user import User

    return {
        "task": Task,
        "project": Project,
        "user": User,
        "document": Document,
        "expense": Expense,
        "client": Client,
        "epic": Epic,
        "sprint": Sprint,
    }


def tipos_soportados() -> list[str]:
    """Los tipos de recurso que una política puede nombrar con `recurso.*`."""
    return sorted(_modelos())


def atributos_del_recurso(
    db: Session, resource_type: Optional[str], resource_id: Optional[str]
) -> Dict[str, Any]:
    """Los atributos de esa fila, con el prefijo `recurso.`.

    Devuelve `{}` cuando no hay tipo, no hay id, el tipo no está declarado en
    `TIPOS` o la fila no existe. Ninguno de esos casos es un error: son «no se
    puede decidir con el recurso», y quien evalúa lo trata como tal.
    """
    if not resource_type or not resource_id:
        return {}

    modelo = _modelos().get(resource_type)
    if modelo is None:
        return {}

    try:
        fila = db.query(modelo).filter(modelo.id == resource_id).first()
    except Exception:
        logger.warning(
            "no se pudo cargar el recurso %s/%s para evaluar ABAC",
            resource_type, resource_id, exc_info=True)
        return {}

    if fila is None:
        return {}

    fuera: Dict[str, Any] = {}
    for columna in modelo.__table__.columns:
        nombre = columna.name
        if any(t in nombre.lower() for t in _NUNCA):
            continue
        valor = getattr(fila, nombre, None)
        # Sólo escalares: una regla compara con un literal de JSON, así que un
        # `datetime` o un `Enum` se pasan como texto y una relación no se pasa.
        if valor is None or isinstance(valor, (str, int, float, bool)):
            fuera[PREFIJO + nombre] = valor
        else:
            fuera[PREFIJO + nombre] = str(getattr(valor, "value", valor))
    return fuera
