"""Las ejecuciones de workflow se buscaban por id sin acotar por organización.

Auditoría 2026-08 (P3-22, tanda 2). Al mover los 14 puntos de acceso a base de
`endpoints/service_desk/workflow_designer.py` apareció una **asimetría dentro
del mismo fichero**: los endpoints de blueprint usaban `org_scoped_or_404` y los
de ejecución hacían `db.query(WorkflowRun).filter(WorkflowRun.id == run_id)` a
secas. Lo único que impedía leer, **reanudar** o **cancelar** la ejecución de
otro cliente era el filtro implícito de `TenantSession`.

Y `start_run` pasaba el `blueprint_id` al motor sin comprobar nada; el motor
también lo busca por id a secas, así que ejecutar el blueprint de otro cliente
dependía de lo mismo.

**Por qué eso no basta**, y es lo que esta auditoría ha ido comprobando:
`organization_id` es *nullable* en estos modelos —una fila sin organización es
invisible para el filtro—, el motor se invoca desde caminos de fondo cuyas
sesiones no llevan contexto, y en el chat en tiempo real la sesión estuvo sin
contexto durante toda la conexión. Una escritura no se apoya en una red de
seguridad.

Estos tests van contra el **servicio**, no contra HTTP, y eso es deliberado: la
sesión de la suite no dispara el filtro implícito (`do_orm_execute` se registra
sobre `SessionLocal` y los tests usan otra factoría), así que aquí lo único que
puede proteger es la guarda explícita. Es decir: **antes del arreglo estos tests
devolverían la fila ajena**.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

ORG_MIA = "org-wf-mia"
ORG_AJENA = "org-wf-ajena"


class _Usuario:
    """Lo mínimo que las guardas leen del sujeto."""

    def __init__(self, organization_id):
        self.id = f"u-{organization_id}"
        self.organization_id = organization_id


@pytest.fixture()
def blueprints_y_ejecuciones(db):
    """Un blueprint y una ejecución en cada organización."""
    from app.models.workflow_designer import (
        WorkflowBlueprint,
        WorkflowRun,
        WorkflowRunStatus,
    )

    creados = {}
    for org in (ORG_MIA, ORG_AJENA):
        bp = WorkflowBlueprint(
            organization_id=org, name=f"Plano de {org}",
            process_type="ticket", is_active=True,
        )
        db.add(bp)
        db.flush()
        # `blueprint_version` es NOT NULL en el modelo: una ejecucion siempre
        # apunta a la version concreta con la que arranco.
        run = WorkflowRun(
            organization_id=org, blueprint_id=bp.id, blueprint_version=1,
            status=WorkflowRunStatus.waiting,
        )
        db.add(run)
        db.flush()
        creados[org] = {"blueprint": bp, "run": run}
    db.commit()
    return creados


# ── Blueprints ──────────────────────────────────────────────────────────────

def test_el_listado_de_planos_solo_trae_los_propios(db, blueprints_y_ejecuciones):
    from app.services.service_desk import workflow_designer_service as svc

    filas = svc.list_blueprints(db, _Usuario(ORG_MIA))
    assert [b.organization_id for b in filas] == [ORG_MIA]


def test_EL_HALLAZGO_un_plano_de_otra_organizacion_da_404(db, blueprints_y_ejecuciones):
    from app.services.service_desk import workflow_designer_service as svc

    ajeno = blueprints_y_ejecuciones[ORG_AJENA]["blueprint"]
    with pytest.raises(HTTPException) as exc:
        svc.blueprint_propio(db, _Usuario(ORG_MIA), ajeno.id)
    assert exc.value.status_code == 404

    # Y el propio sí se encuentra: la guarda no rompe el camino bueno.
    mio = blueprints_y_ejecuciones[ORG_MIA]["blueprint"]
    assert svc.blueprint_propio(db, _Usuario(ORG_MIA), mio.id).id == mio.id


def test_un_plano_inexistente_da_el_mismo_404(db):
    """Un plano ajeno y uno inexistente no se distinguen: la diferencia diría
    que existe."""
    from app.services.service_desk import workflow_designer_service as svc

    with pytest.raises(HTTPException) as exc:
        svc.blueprint_propio(db, _Usuario(ORG_MIA), "no-existe")
    assert exc.value.status_code == 404


# ── Ejecuciones ─────────────────────────────────────────────────────────────

def test_el_listado_de_ejecuciones_solo_trae_las_propias(db, blueprints_y_ejecuciones):
    from app.services.service_desk import workflow_designer_service as svc

    filas = svc.list_runs(db, _Usuario(ORG_MIA))
    assert [r.organization_id for r in filas] == [ORG_MIA]


def test_EL_HALLAZGO_una_ejecucion_de_otra_organizacion_da_404(db, blueprints_y_ejecuciones):
    """Es la guarda que faltaba, y la que sostiene `resume` y `cancel`."""
    from app.services.service_desk import workflow_designer_service as svc

    ajena = blueprints_y_ejecuciones[ORG_AJENA]["run"]
    with pytest.raises(HTTPException) as exc:
        svc.run_propio(db, _Usuario(ORG_MIA), ajena.id)
    assert exc.value.status_code == 404

    mia = blueprints_y_ejecuciones[ORG_MIA]["run"]
    assert svc.run_propio(db, _Usuario(ORG_MIA), mia.id).id == mia.id


def test_la_version_de_un_plano_se_acota_por_su_plano(db, blueprints_y_ejecuciones):
    """`version_del_blueprint` no lleva filtro de organización a propósito: se
    busca por `blueprint_id` de un plano ya comprobado, así que el ámbito llega
    por la clave padre. Lo que se fija aquí es que una versión que no es de ese
    plano no aparece."""
    from app.models.workflow_designer import WorkflowBlueprintVersion
    from app.services.service_desk import workflow_designer_service as svc

    mio = blueprints_y_ejecuciones[ORG_MIA]["blueprint"]
    ajeno = blueprints_y_ejecuciones[ORG_AJENA]["blueprint"]
    db.add(WorkflowBlueprintVersion(
        organization_id=ORG_AJENA, blueprint_id=ajeno.id, version=1,
        graph_json="{}"))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.version_del_blueprint(db, mio, 1)
    assert exc.value.status_code == 404


def test_clonar_un_plano_sin_versiones_lo_dice(db, blueprints_y_ejecuciones):
    from app.services.service_desk import workflow_designer_service as svc

    mio = blueprints_y_ejecuciones[ORG_MIA]["blueprint"]
    with pytest.raises(HTTPException) as exc:
        svc.grafo_de_cabecera(mio)
    assert exc.value.status_code == 400
