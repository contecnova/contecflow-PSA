"""Ningún sitio de `app/` lee un atributo de modelo que no existe.

Auditoría 2026-08. El guardián hermano del de los enumerados
(`test_miembros_de_enum_existen.py`), y salió de dos defectos que aquél no podía
ver: `SLAPolicy.response_hours` —son cuatro columnas, una por prioridad— y
`Ticket.requester_phone`, que no existe.

## Lo que encontró

**43 candidatos en 27 pares (clase, atributo)** sobre 391 clases mapeadas.
Verificados uno a uno, y ninguno era un falso positivo del detector: todos son
nombres equivocados o columnas que faltan. Los grupos:

**Nombres equivocados** (la columna existe con otro nombre) — 34 sitios.
`Ticket.assignee_id` ×11 en cuatro ficheros, cuando la columna es
`assigned_to_user_id` y `assignee_id` es la de `Task`; más
`assigned_agent_id`, `assigned_to_id`, `assignee`;
`ClientHealthSnapshot.created_at` (es `snapshot_at`);
`CMDBRelation.source_ci_id`/`target_ci_id`/`relation_type` (son `from_item_id`,
`to_item_id`, `rel_type`); `TicketLink.source_ticket_id`/`target_ticket_id`/
`created_by_user_id` (son `source_id`, `target_id`, `created_by`);
`Contract.amount` (es `total_amount`); `Deliverable.due_date` (es
`planned_date`); `Expense.date` (es `expense_date`);
`KBArticle.is_published` (es `is_public`); `Task.created_by_user_id` (es
`created_by`); `Alert.message` (tiene `title` y `description`);
`TicketComment.is_internal` (tiene `is_public`, que es lo mismo al revés).

**Conceptos que el esquema modela de otra forma** — 4 sitios.
`Task.sprint_id`: una tarea se enlaza a un sprint por la tabla `sprint_tasks`.
`Task.actual_hours`: las horas reales son la suma de las imputaciones.
`Ticket.category`: la clasificación de un ticket es `service_item_id`.
`Imputation.work_type`: no existe y no se inventa.

**Columnas que hacían falta de verdad** — 3, añadidas en la revisión 094:
`deliverables.billing_pct`, `opportunities.external_id`,
`revenue_recognition_rules.is_active`.

**Y uno que no se toca:** `MajorIncident.tickets`. Entre esas dos entidades no
hay ni columna ni tabla de unión, así que la relación no existe. Inventarla es
una decisión de diseño —¿un ticket pertenece a una sola incidencia mayor?— y no
se cuela en una tanda de otra cosa.

## Lo que rompía cada uno, que es lo que importa

Diez funciones completas, y tres de ellas escondidas detrás de un `hasattr`
**correcto** sobre una columna ausente, que es el peor caso porque parece una
defensa y es un apagado:

* `cmdb_service`: el `else` del `hasattr` **se saltaba el filtro de organización
  entero** y dejaba un aviso en el log que parecía informar de una limitación
  temporal;
* `salesforce_service.find_opportunity_by_external_id` devolvía **siempre
  None**, así que la sincronización **duplicaba todas las oportunidades en cada
  pasada**;
* la comprobación de cumplimiento «P1 sin incidencia mayor» reportaba **todos**
  los P1, siempre.

Y las otras siete reventaban: aplicar una plantilla de proyecto, importar
imputaciones desde CSV, la detección automática de problemas, el cálculo
automático de reconocimiento de ingresos, la estimación de horas por tareas
similares, las tareas de un sprint, la correlación de alertas por CI raíz, el
comentario de la IA en el ticket y el enlace de tickets duplicados.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

RAIZ = Path("app")


def _clases_mapeadas() -> dict:
    import app.models  # noqa: F401 — registra todos los mapeadores
    from app.db.base import Base

    return {m.class_.__name__: m.class_ for m in Base.registry.mappers}


#: Atributos que no son del modelo y aparecen sobre una clase mapeada.
_NO_SON_COLUMNAS = {"metadata", "registry"}

#: Lo que queda a propósito, con su razón. Vacía es la meta.
CONOCIDOS = {
    # Entre `MajorIncident` y `Ticket` no hay ni columna ni tabla de unión.
    # Inventar la relación es una decisión de diseño; el sitio que la consulta
    # declara la comprobación como no evaluable en vez de dar un falso
    # positivo por cada ticket P1.
    ("MajorIncident", "tickets"),
}


def _accesos_sospechosos():
    clases = _clases_mapeadas()
    salida = []
    for ruta in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name):
                cls = clases.get(nodo.value.id)
                if cls is None or nodo.attr.startswith("_"):
                    continue
                if nodo.attr in _NO_SON_COLUMNAS or hasattr(cls, nodo.attr):
                    continue
                if (nodo.value.id, nodo.attr) in CONOCIDOS:
                    continue
                salida.append(
                    (f"{ruta.as_posix()}:{nodo.lineno}", nodo.value.id, nodo.attr))
            elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                cls = clases.get(nodo.func.id)
                if cls is None:
                    continue
                for kw in nodo.keywords:
                    if kw.arg and not hasattr(cls, kw.arg):
                        if (nodo.func.id, kw.arg) in CONOCIDOS:
                            continue
                        salida.append(
                            (f"{ruta.as_posix()}:{nodo.lineno}",
                             nodo.func.id, f"{kw.arg}=  (constructor)"))
    return salida


def test_ningun_acceso_a_un_atributo_de_modelo_que_no_existe():
    """El guardián. Comprobado que discrimina: sobre el código anterior da 42.

    Cuarenta y dos y no cuarenta y tres, que es el total de candidatos: el que
    falta es `MajorIncident.tickets`, declarado en `CONOCIDOS` con su razón. La
    diferencia está medida, no estimada — se ejecutó el test contra la versión
    anterior del repositorio en un `git worktree`.

    El lado de la clase se resuelve con `hasattr` sobre la clase mapeada de
    verdad, no por AST, así que cubre columnas, relaciones, propiedades
    híbridas, métodos y todo lo heredado. Un falso positivo es raro; si aparece
    uno legítimo, va a `CONOCIDOS` **con su razón escrita**, no se relaja la
    regla.
    """
    sospechosos = _accesos_sospechosos()
    assert not sospechosos, (
        "estos sitios leen un atributo que la clase mapeada no tiene: "
        + "; ".join(f"{d} -> {c}.{a}" for d, c, a in sospechosos))


def test_lo_que_queda_a_proposito_esta_declarado_con_su_razon():
    """`CONOCIDOS` no es una alfombra: cada entrada tiene que seguir siendo real.

    Si alguien añade la relación que falta, esta entrada sobra y el test lo
    dice — así la excepción no se queda ahí para siempre por inercia.
    """
    clases = _clases_mapeadas()
    obsoletos = [
        (clase, attr) for clase, attr in CONOCIDOS
        if clase in clases and hasattr(clases[clase], attr)
    ]
    assert not obsoletos, (
        "estas excepciones ya no hacen falta, el atributo existe: "
        + "; ".join(f"{c}.{a}" for c, a in obsoletos))


# -- Las tres columnas nuevas ------------------------------------------------

@pytest.mark.parametrize("clase,columna", [
    ("Deliverable", "billing_pct"),
    ("Opportunity", "external_id"),
    ("RevenueRecognitionRule", "is_active"),
])
def test_las_columnas_de_la_migracion_094_estan_en_el_modelo(clase, columna):
    clases = _clases_mapeadas()
    assert columna in clases[clase].__table__.columns, (
        f"{clase}.{columna} no está en el modelo: la migración 094 la añade a "
        "la base y el modelo tiene que declararla")


def test_una_plantilla_con_entregable_se_puede_aplicar(db):
    """`Deliverable(billing_pct=...)` daba `TypeError`: la plantilla no se aplicaba."""
    from app.models.resources import Deliverable
    from app.models.project import Project, ProjectType

    db.add(Project(id="p-tpl-del", name="Proyecto", code="PTD",
                   project_type=ProjectType.development))
    db.flush()
    d = Deliverable(
        id="del-1", code="DEL-001", project_id="p-tpl-del",
        name="Informe final", format="PDF", billing_pct=30.0)
    db.add(d)
    db.commit()

    assert db.query(Deliverable).first().billing_pct == 30.0


def test_una_oportunidad_importada_se_reconoce_por_su_id_externo(db):
    """Sin la columna, la búsqueda devolvía None y se duplicaba en cada pasada."""
    from app.models.pipeline import Opportunity
    from app.services import salesforce_service as svc

    db.add(Opportunity(
        id="opp-sf", code="OPP-SF", name="Oportunidad de Salesforce",
        client_name="Cliente", external_id="006ABCDEFGH"))
    db.commit()

    encontrada = svc.find_opportunity_by_external_id(db, "006ABCDEFGH")
    assert encontrada is not None, (
        "la búsqueda por id externo sigue devolviendo None: la sincronización "
        "duplicará la oportunidad en cada pasada")
    assert encontrada.id == "opp-sf"
    assert svc.find_opportunity_by_external_id(db, "no-existe") is None


def test_una_regla_de_reconocimiento_se_puede_desactivar(db):
    """`is_active` no existía y el cálculo automático reventaba al filtrarla."""
    from app.models.cab import RevenueRecognitionRule
    from app.models.project import Project, ProjectType

    db.add(Project(id="p-rev", name="Proyecto", code="PRV",
                   project_type=ProjectType.development))
    db.flush()
    regla = RevenueRecognitionRule(id="rr-1", project_id="p-rev")
    db.add(regla)
    db.commit()

    # Por defecto activa, que es lo que significa una regla que está en la tabla.
    assert regla.is_active is True

    activas = db.query(RevenueRecognitionRule).filter(
        RevenueRecognitionRule.is_active == True  # noqa: E712
    ).all()
    assert len(activas) == 1

    regla.is_active = False
    db.commit()
    assert db.query(RevenueRecognitionRule).filter(
        RevenueRecognitionRule.is_active == True  # noqa: E712
    ).count() == 0


# -- Y el de aislamiento, que es el que más importa -------------------------

def test_EL_HALLAZGO_el_listado_de_CMDB_vuelve_a_filtrar_por_organizacion(db):
    """El `hasattr` correcto sobre una columna ausente apagaba el filtro.

    Se tomaba siempre la rama `else`, que registra un aviso y **no filtra**. El
    aviso parecía informar de una limitación temporal del despliegue y lo que
    describía era la ausencia del filtro de tenant.
    """
    from app.models.cmdb import CMDBItem
    from app.services import cmdb_service as svc

    for org in ("org-ci-mia", "org-ci-ajena"):
        db.add(CMDBItem(
            id=f"ci-{org}", name=f"Servidor de {org}", ci_type="server",
            organization_id=org))
    db.commit()

    # Devuelve diccionarios serializados, no filas: se comprueba por id.
    filas = svc.list_cmdb_items(
        ci_type=None, status=None, category_id=None, q=None,
        organization_id="org-ci-mia", db=db)
    ids = {f["id"] for f in filas}
    assert ids == {"ci-org-ci-mia"}, (
        f"el listado de CMDB devuelve elementos de otras organizaciones: {ids}")

    # Y sin organizacion no filtra, que es el comportamiento declarado del
    # parametro: la guarda del endpoint es la que lo exige.
    todos = svc.list_cmdb_items(
        ci_type=None, status=None, category_id=None, q=None,
        organization_id=None, db=db)
    assert len(todos) == 2
