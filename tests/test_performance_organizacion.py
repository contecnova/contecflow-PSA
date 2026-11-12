"""El módulo de evaluaciones creaba sus filas SIN organización, y desaparecían.

Auditoría 2026-08 (P3-22). Al poner una guarda explícita de organización en
`endpoints/performance.py` los tests se pusieron en rojo, y la causa no era la
guarda: era que **ninguna de las nueve creaciones de este módulo guardaba
`organization_id`**. Esa es la columna por la que filtra `TenantSession`
(`organization_id == org`), así que una fila con NULL **no la ve nadie** salvo un
superadmin.

Medido con la sesión real de la aplicación, antes del arreglo:

    ciclo creado por el endpoint -> organization_id = None
    GET /performance/cycles para su organización -> 0 ciclos
    el mismo listado para un superadmin -> 1 ciclo

Es decir: **se creaba el ciclo y desaparecía**. Editar o borrar una pregunta daba
404. Un plan de desarrollo y sus objetivos, lo mismo. El módulo entero estaba
muerto en un despliegue con tenant, y no había error en ningún log — sólo listas
vacías, que es exactamente lo que no se investiga.

Estos tests activan el filtro de tenant a mano sobre la sesión de pruebas,
porque el escuchador se registra sobre `SessionLocal` y la suite usa otra
factoría. Sin activarlo no se reproduce nada: el defecto sólo existe cuando el
filtro actúa, que es en producción.

Para las filas ya guardadas está `alembic/versions/092_performance_backfill_organization.py`,
que las hereda de su padre —pregunta del ciclo, objetivo del plan— y las de
`review_cycles` y `development_plans` del usuario que las creó.
"""
from __future__ import annotations

import pytest
from app.core.errores import ErrorDeDominio

ORG = "org-desempeno"
OTRA = "org-ajena"


class _Usuario:
    def __init__(self, organization_id, uid="u-perf"):
        self.id = uid
        self.organization_id = organization_id
        self.is_superadmin = False
        self.role = "admin"


@pytest.fixture()
def sesion_con_filtro(db):
    """La sesión de pruebas con el filtro de tenant enganchado.

    Es lo que hace que estos tests prueben algo: el defecto sólo se manifiesta
    cuando `organization_id == org` se aplica de verdad.
    """
    from sqlalchemy import event as sa_event

    from app.db.session import _enforce_tenant_isolation

    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    db.info["is_superadmin"] = False
    db.info["organization_id"] = ORG
    try:
        yield db
    finally:
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)


# ── Ciclos y preguntas ──────────────────────────────────────────────────────

def test_EL_HALLAZGO_un_ciclo_recien_creado_lo_ve_su_organizacion(db, sesion_con_filtro):
    """Antes del arreglo esto devolvía cero: el ciclo se creaba y desaparecía."""
    from app.services import performance_service as svc

    ciclo = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Ciclo 2026")
    assert ciclo.organization_id == ORG

    items, total = svc.list_cycles(db)
    assert total == 1, "la organización no ve su propio ciclo recién creado"
    assert items[0].id == ciclo.id


def test_las_preguntas_sembradas_heredan_la_organizacion_del_ciclo(db, sesion_con_filtro):
    from app.services import performance_service as svc

    ciclo = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Con preguntas",
        seed_default_questions=True)
    assert ciclo.questions, "el ciclo se sembró sin preguntas"
    assert {q.organization_id for q in ciclo.questions} == {ORG}


def test_EL_HALLAZGO_una_pregunta_se_encuentra_por_id_por_su_propia_organizacion(
    db, sesion_con_filtro
):
    """`PATCH` y `DELETE` de una pregunta daban 404 en producción."""
    from app.services import performance_service as svc

    ciclo = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Editable",
        seed_default_questions=True)
    pregunta = ciclo.questions[0]

    encontrada = svc.pregunta_propia(db, _Usuario(ORG), pregunta.id)
    assert encontrada.id == pregunta.id


def test_la_pregunta_de_otra_organizacion_da_404(db, sesion_con_filtro):
    from fastapi import HTTPException

    from app.services import performance_service as svc

    ciclo = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Mío",
        seed_default_questions=True)
    pregunta = ciclo.questions[0]

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.pregunta_propia(db, _Usuario(OTRA), pregunta.id)
    assert exc.value.status_code == 404


def test_las_preguntas_clonadas_heredan_la_del_ciclo_destino(db, sesion_con_filtro):
    """Clonar un cuestionario no puede traerse la organización del origen."""
    from app.services import performance_service as svc

    origen = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Origen",
        seed_default_questions=True)
    destino = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Destino",
        seed_default_questions=False,
        clone_questions_from_cycle_id=origen.id)

    assert destino.questions, "no se clonó ninguna pregunta"
    assert {q.organization_id for q in destino.questions} == {ORG}


def test_una_pregunta_añadida_a_mano_hereda_la_del_ciclo(db, sesion_con_filtro):
    from app.services import performance_service as svc

    ciclo = svc.create_cycle(
        db, created_by="u-perf", organization_id=ORG, name="Manual",
        seed_default_questions=False)
    q = svc.add_question(db, ciclo, {
        "key": "extra", "label": "Una más", "kind": "text_short"})
    assert q.organization_id == ORG


# ── Planes de desarrollo ────────────────────────────────────────────────────

def test_EL_HALLAZGO_un_plan_y_sus_objetivos_llevan_organizacion(db, sesion_con_filtro):
    from app.services import dev_plan_service as svc

    plan = svc.create_plan(
        db, subject_id="u-perf", created_by="u-perf", organization_id=ORG,
        title="Plan de Ana",
        goals=[{"title": "Certificarse"}, {"title": "Liderar un proyecto"}])

    assert plan.organization_id == ORG
    assert len(plan.goals) == 2
    assert {g.organization_id for g in plan.goals} == {ORG}


def test_un_objetivo_añadido_despues_hereda_la_del_plan(db, sesion_con_filtro):
    from app.services import dev_plan_service as svc

    plan = svc.create_plan(
        db, subject_id="u-perf", created_by="u-perf", organization_id=ORG,
        title="Plan")
    objetivo = svc.add_goal(db, plan, {"title": "Nuevo objetivo"})
    assert objetivo.organization_id == ORG


def test_el_objetivo_de_otra_organizacion_da_404(db, sesion_con_filtro):
    from fastapi import HTTPException

    from app.services import dev_plan_service as dev
    from app.services import performance_service as svc

    plan = dev.create_plan(
        db, subject_id="u-perf", created_by="u-perf", organization_id=ORG,
        title="Plan", goals=[{"title": "Objetivo"}])
    objetivo = plan.goals[0]

    assert svc.objetivo_propio(db, _Usuario(ORG), objetivo.id).id == objetivo.id
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.objetivo_propio(db, _Usuario(OTRA), objetivo.id)
    assert exc.value.status_code == 404


# ── Que no queda ninguna creación sin organización ──────────────────────────

def test_EL_ESTRUCTURAL_ninguna_creacion_del_modulo_omite_la_organizacion():
    """El que impide que vuelva a pasar.

    Se comprueba por AST sobre los dos servicios: cualquier construcción de uno
    de estos modelos tiene que llevar `organization_id`. Eran nueve las que no
    lo llevaban, y ningún test lo detectaba porque el efecto sólo se ve con el
    filtro de tenant activo.
    """
    import ast
    import io

    MODELOS = {
        "ReviewCycle", "ReviewQuestion", "PerformanceReview",
        "Review360Campaign", "DevelopmentPlan", "DevGoal",
    }
    sin_organizacion = []
    # `performance_service` es un paquete desde la auditoria 2026-11 (#24):
    # se recorren todos sus submodulos.
    import glob
    rutas = sorted(glob.glob("app/services/performance_service/*.py")) + [
        "app/services/dev_plan_service.py"]
    assert len(rutas) > 1
    for ruta in rutas:
        arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Name)
                    and nodo.func.id in MODELOS):
                continue
            claves = {k.arg for k in nodo.keywords if k.arg}
            if "organization_id" not in claves:
                sin_organizacion.append(f"{ruta}:{nodo.lineno} {nodo.func.id}")

    assert not sin_organizacion, (
        "hay creaciones sin organization_id, y una fila NULL no la ve su propia "
        "organización:\n  " + "\n  ".join(sin_organizacion))
