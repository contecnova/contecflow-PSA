"""Ningún sitio lee ni escribe un atributo de instancia que la clase no tiene.

Auditoría 2026-08. El tercero de la familia, y el que cerró el frente que los
otros dos dejaron señalado.

`audit_enum_members.py` mira `Enumerado.valor`. `audit_model_attrs.py` mira
`Modelo.columna`. Ninguno de los dos puede ver `fila.columna`, y ahí apareció el
primer caso: al arreglar `KBArticle.is_published` había un `art.content` dos
líneas más abajo —el cuerpo del artículo es `art.body`— y eso hacía que la
sugerencia de artículos se decidiera **sólo por el título**.

## Cómo se infiere el tipo sin inferir tipos

Cuatro formas cubren el código real de este repositorio: el bucle sobre una
consulta, la comprehensión sobre una consulta, la asignación desde una consulta
que devuelve una fila (`.first()`, `.one()`…) y el parámetro anotado. **Y un
nombre religado más de una vez se descarta**, por cualquier vía.

Lo que **no** cubre, y queda dicho: variables que vienen de una llamada a un
servicio. Ahí haría falta seguir el tipo de retorno.

## Lo que encontró: diez accesos, siete funciones roídas

| dónde | qué | qué pasaba |
|---|---|---|
| `agent_execution_service` | `execution.updated_at` | `get_agent_status` **reventaba siempre**: el estado de una ejecución de agente de IA no se podía consultar |
| `ai_planning_service` | `ticket.assignee_id = …` | **asignación silenciosa**: aceptar un triaje de IA cambiaba prioridad y tipo y **no asignaba el ticket a nadie** |
| `bookings_service` ×3 | `opp.amount` | convertir una oportunidad en proyecto reventaba — el **segundo** defecto de esa función |
| `epics_service` | `t.assigned_to_user_id` | el detalle de un epic **no se podía leer** en cuanto tenía una tarea |
| `security_observability` | `det.mttd_seconds = …` | **asignación silenciosa**: el tiempo hasta la detección se calculaba y se tiraba |
| `change_management_service` | `change.assigned_to_id` | **ningún aviso a los interesados de un cambio llegaba nunca** |
| `smart_catalog_service` | `svc.popularity_score` | tras un `hasattr` correcto: la actualización de popularidad **no actualizaba nada** y devolvía `updated: 0` sin error |

## Lo que este detector enseña y los otros dos no

**La asignación es peor que la lectura.** `fila.columna_que_no_existe` al leer
lanza `AttributeError` y alguien ve un 500. Al **escribir**, SQLAlchemy no se
queja: se queda un atributo de Python que no persiste. Dos de los diez eran
así, y los dos tiraban un cálculo a la basura sin un solo error en los
registros. Un fallo silencioso es peor que un 500.

Y **dos veces apareció un segundo defecto detrás del primero**: en
`bookings_service`, el `OpportunityStage.closed_won` inexistente abortaba la
función antes de llegar al `opp.amount`, así que el segundo sólo se vio al
arreglar el primero — y sólo porque se volvió a pasar el detector después.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUTA_DEL_SCRIPT = Path("scripts/audit_instance_attrs.py")

#: Lo que queda a propósito, con su razón. Vacía es la meta.
CONOCIDOS: set[tuple[str, str]] = set()


def _detector():
    """Carga el script de medición como módulo.

    Se usa **el mismo** código que mide, no una copia: si la regla cambia, el
    guardián cambia con ella.
    """
    if not RUTA_DEL_SCRIPT.exists():
        pytest.skip("no hay scripts/ en este árbol de trabajo")
    spec = importlib.util.spec_from_file_location(
        "_audit_instance_attrs", RUTA_DEL_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["_audit_instance_attrs"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_ningun_atributo_de_instancia_inexistente():
    """Tolerancia cero. Comprobado que discrimina: sobre el código anterior, 10.

    Si aparece un falso positivo legítimo, va a `CONOCIDOS` **con su razón
    escrita** — no se relaja la regla del detector, que ya se ajustó dos veces
    por eso mismo y está documentado en su cabecera.
    """
    filas = _detector().analizar()
    culpables = [
        f"{ruta}:{linea} ({funcion}) -> {var}.{attr}  [{var} es {modelo}]"
        for ruta, linea, funcion, var, modelo, attr in filas
        if (modelo, attr) not in CONOCIDOS
    ]
    assert not culpables, (
        "estos sitios leen o escriben un atributo que la clase no tiene. Ojo: "
        "si es una ESCRITURA, no lanza excepción — se queda un atributo de "
        "Python que no persiste, y el dato se pierde en silencio:\n  "
        + "\n  ".join(culpables))


def test_el_detector_infiere_tipos_de_verdad():
    """Que el guardián no pase por vacío.

    Si la inferencia dejara de reconocer las formas del repositorio, no
    encontraría variables que vigilar y el test de arriba pasaría sin
    comprobar nada.
    """
    import ast
    import io as _io

    modulo = _detector()
    con_tipos = 0
    for ruta in Path("app").rglob("*.py"):
        if "__pycache__" in ruta.parts:
            continue
        try:
            arbol = ast.parse(_io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue
        for funcion in ast.walk(arbol):
            if isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if modulo._tipos_locales(funcion):
                    con_tipos += 1

    assert con_tipos > 100, (
        f"el detector sólo infiere el tipo de alguna variable en {con_tipos} "
        "funciones: revisar si la inferencia sigue funcionando")


# -- Los siete arreglos, comprobados uno a uno -----------------------------

def test_el_estado_de_una_ejecucion_de_agente_se_puede_consultar(db):
    """`execution.updated_at` no existe: reventaba siempre."""
    from app.models.ai_chat import AIAgentExecution
    from app.services.ai_chat import agent_execution_service as svc

    db.add(AIAgentExecution(
        id="exe-1", user_id="u-1", instruction="haz algo", status="completed",
        result="hecho"))
    db.commit()

    datos = svc.get_agent_status(db, "exe-1", "u-1")
    assert datos["execution_id"] == "exe-1"
    # La clave se conserva; el valor sale de `completed_at`, que sí existe.
    assert "updated_at" in datos


def test_aceptar_un_triaje_de_ia_asigna_el_ticket_de_verdad(db):
    """Era una asignación silenciosa: cambiaba todo menos el asignado."""
    from app.models.service_desk import Ticket
    from app.services import ai_planning_service as svc

    db.add(Ticket(
        id="t-triaje", number="SD-700", ticket_type="incident",
        title="Con triaje", description="x"))
    db.commit()

    triaje = _TriajeFalso(agente="u-asignado")
    svc_db = db

    class _Consulta:
        def filter(self, *a, **k):
            return self

        def first(self):
            return triaje

    # Se sustituye sólo la búsqueda del triaje; la del ticket es la real.
    original = svc_db.query

    def _query(modelo, *a, **k):
        if getattr(modelo, "__name__", "") == "AITicketTriage":
            return _Consulta()
        return original(modelo, *a, **k)

    svc_db.query = _query
    try:
        svc.accept_ticket_triage("t-triaje", True, "u-actor", svc_db)
    finally:
        svc_db.query = original

    ticket = db.query(Ticket).filter(Ticket.id == "t-triaje").first()
    assert ticket.assigned_to_user_id == "u-asignado", (
        "el ticket sigue sin asignar: la escritura a `assignee_id` no "
        "persistía porque esa columna no existe en `sd_tickets`")


class _TriajeFalso:
    """El mínimo que `accept_ticket_triage` lee de un triaje."""

    def __init__(self, agente=None):
        self.suggested_priority = None
        self.suggested_category = None
        self.suggested_agent_id = agente
        self.accepted = None
        self.accepted_by = None
        self.accepted_at = None


def test_el_detalle_de_un_epic_con_tareas_se_puede_leer(db):
    """`t.assigned_to_user_id` es la columna de `Ticket`, no de `Task`."""
    from app.models.epics import Epic, EpicTask
    from app.models.project import Project, ProjectType
    from app.models.task import Task
    from app.services import epics_service as svc

    db.add(Project(id="p-epic", name="Proyecto", code="PEP",
                   project_type=ProjectType.development))
    db.flush()
    # `Epic` usa `title`, no `name`.
    db.add(Epic(id="e-1", project_id="p-epic", title="Epic con tareas"))
    db.add(Task(id="t-1", project_id="p-epic", code="T-1",
                title="Tarea del epic", assignee_id="u-9"))
    db.flush()
    db.add(EpicTask(id="et-1", epic_id="e-1", task_id="t-1"))
    db.commit()

    datos = svc.get_epic_record("e-1", db)
    assert len(datos["tasks"]) == 1
    assert datos["tasks"][0]["assigned_to_user_id"] == "u-9", (
        "la clave de la respuesta se conserva, pero el valor tiene que salir "
        "de `Task.assignee_id`")


def test_los_avisos_de_un_cambio_llegan_a_los_tres_interesados(db, monkeypatch):
    """`change.assigned_to_id` no existe: el responsable es `owner_id`."""
    from app.models.service_desk import ITSMChangeRequest
    from app.models.user import User, UserRole, UserStatus
    from app.services.service_desk import change_management_service as svc

    for uid in ("u-sol", "u-apr", "u-own"):
        db.add(User(
            id=uid, username=uid, email=f"{uid}@example.com",
            full_name=uid, role=UserRole.employee, status=UserStatus.active,
            # `users.organization_id` es NOT NULL.
            hashed_password="x", organization_id="org-avisos"))
    db.add(ITSMChangeRequest(
        id="chg-avisos", number="CHG-1", title="Con interesados",
        description="x", status="submitted",
        requester_id="u-sol", approver_id="u-apr", owner_id="u-own"))
    db.commit()

    enviados = []
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service.NotificationService, "send_email",
        staticmethod(lambda **kw: enviados.append(kw.get("to"))))

    svc._notify_change_stakeholders(db, "chg-avisos", "asunto", "<p>hola</p>")

    assert set(enviados) == {
        "u-sol@example.com", "u-apr@example.com", "u-own@example.com"}, (
        f"se ha avisado a {enviados}: tienen que ser los tres interesados")


def test_la_popularidad_de_servicios_devuelve_las_puntuaciones(db):
    """Tras un `hasattr` correcto, el bucle no se ejecutaba nunca.

    No se inventa la columna: la puntuación se calcula aquí mismo, así que
    guardarla sería un caché que hay que invalidar. Lo que se hace es
    devolverla y **decir que no se persiste**.
    """
    from app.services.service_desk import smart_catalog_service as svc

    datos = svc.update_service_popularity(db)
    assert datos["updated"] == 0
    assert datos["persisted"] is False
    assert "scores" in datos
