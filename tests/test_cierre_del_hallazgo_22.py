"""Lo que salió al cerrar los últimos trece puntos del hallazgo 22.

Auditoría 2026-08. Los trece eran, en su mayoría, movimientos sin defecto: el
filtro por organización ya estaba y era el correcto. **Uno no.**

## La guarda que faltaba

`PATCH /automation-workflows/{wf_id}/steps/{step_id}/retries` buscaba el paso
así:

    db.query(WorkflowStep).filter(
        WorkflowStep.id == step_id,
        WorkflowStep.workflow_id == wf_id,
    ).first()

Los dos identificadores vienen de la ruta y **no había ninguna comprobación de
a quién pertenece el workflow**. En producción el filtro implícito de
`TenantSession` lo evitaba —`WorkflowStep` tiene `organization_id`— pero era la
única capa, y esto **escribe**: cambia la política de reintentos del paso de
otro cliente.

## Y dos cosas que conviene que queden fijadas

**El `["__none__"]` del asignador semántico no es decorativo.** Una organización
sin usuarios activos tiene que dar **cero candidatos**, y una lista vacía
significaría «sin restricción», que es justo lo contrario. Es la clase de
detalle que se pierde al mover código, así que tiene test.

**Y el condicional de `bi_etl` que *parece* el defectuoso y no lo es.** Cuatro
veces en esta auditoría apareció `if org_id: q = q.filter(...)`, que sin
organización devuelve las filas de todos. El de `bi_etl` tiene rama `else` que
filtra por `IS NULL` —el valor global del despliegue—, así que los dos caminos
acotan. Queda con test para que nadie lo «arregle» rompiéndolo.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio

ORG = "org-cierre-mia"
OTRA = "org-cierre-ajena"


class _Usuario:
    def __init__(self, organization_id, superadmin=False):
        self.id = f"u-{organization_id}"
        self.organization_id = organization_id
        self.is_superadmin = superadmin


# -- La guarda que faltaba: el paso de workflow ------------------------------

@pytest.fixture()
def pasos_de_workflow(db):
    """Un workflow con un paso en cada organización."""
    from app.models.billing_reports import AutomationWorkflow, WorkflowStep

    creados = {}
    for org in (ORG, OTRA):
        # `trigger_type` es NOT NULL en `automation_workflows`, y `config`
        # lo es en `workflow_steps`.
        wf = AutomationWorkflow(
            id=f"wf-{org}", name=f"Workflow de {org}",
            trigger_type="manual", organization_id=org)
        db.add(wf)
        db.flush()
        paso = WorkflowStep(
            id=f"step-{org}", workflow_id=wf.id,
            step_type="notify", config="{}", organization_id=org)
        db.add(paso)
        db.flush()
        creados[org] = {"workflow": wf, "paso": paso}
    db.commit()
    return creados


def test_EL_HALLAZGO_no_se_configura_el_paso_de_workflow_de_otro_cliente(
    db, pasos_de_workflow
):
    """Es una escritura: cambia la política de reintentos de otro cliente."""
    from app.services import bookings_service as svc

    ajeno = pasos_de_workflow[OTRA]
    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.paso_de_workflow_propio(
            db, _Usuario(ORG), ajeno["workflow"].id, ajeno["paso"].id)
    assert exc.value.status_code == 404

    mio = pasos_de_workflow[ORG]
    paso = svc.paso_de_workflow_propio(
        db, _Usuario(ORG), mio["workflow"].id, mio["paso"].id)
    assert paso.id == mio["paso"].id


def test_EL_ESCENARIO_la_consulta_de_antes_alcanzaba_el_paso_ajeno(
    db, pasos_de_workflow
):
    """Que el escenario es real, medido y no contado."""
    from app.models.billing_reports import WorkflowStep

    ajeno = pasos_de_workflow[OTRA]
    fila = (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.id == ajeno["paso"].id,
            WorkflowStep.workflow_id == ajeno["workflow"].id,
        )
        .first()
    )
    assert fila is not None and fila.organization_id == OTRA, (
        "la consulta sin ámbito ya no alcanza el paso de otro cliente; "
        "revisar si este test sigue midiendo lo que dice")


def test_el_paso_de_un_workflow_que_no_es_suyo_tampoco_vale(db, pasos_de_workflow):
    """Cruzando los ids: el workflow propio con el paso ajeno."""
    from app.services import bookings_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.paso_de_workflow_propio(
            db, _Usuario(ORG),
            pasos_de_workflow[ORG]["workflow"].id,
            pasos_de_workflow[OTRA]["paso"].id)
    assert exc.value.status_code == 404


def test_un_superadmin_si_alcanza_cualquiera(db, pasos_de_workflow):
    from app.services import bookings_service as svc

    ajeno = pasos_de_workflow[OTRA]
    paso = svc.paso_de_workflow_propio(
        db, _Usuario(None, superadmin=True),
        ajeno["workflow"].id, ajeno["paso"].id)
    assert paso.id == ajeno["paso"].id


# -- El asignador semántico: el `["__none__"]` que no es decorativo ---------

def test_una_organizacion_sin_usuarios_activos_da_cero_candidatos(db):
    """Una lista vacía significaría «sin restricción», que es lo contrario."""
    from app.services import semantic_engine_service as svc

    ids = svc.ids_de_usuarios_del_ambito(db, _Usuario("org-vacia"))
    assert ids == ["__none__"], (
        f"devuelve {ids!r}: una lista vacía haría que el asignador mirase a "
        "TODOS los usuarios, que es justo lo contrario de lo que se pide")


def test_un_superadmin_no_tiene_restriccion(db):
    from app.services import semantic_engine_service as svc

    assert svc.ids_de_usuarios_del_ambito(
        db, _Usuario(None, superadmin=True)) is None


def test_solo_se_asignan_usuarios_activos_de_la_organizacion(db):
    from app.models.user import User, UserRole, UserStatus
    from app.services import semantic_engine_service as svc

    for org, activo in ((ORG, True), (ORG, False), (OTRA, True)):
        sufijo = f"{org}-{activo}"
        db.add(User(
            id=f"u-sem-{sufijo}", username=f"u-sem-{sufijo}",
            email=f"{sufijo}@example.com", full_name="Agente",
            role=UserRole.employee, status=UserStatus.active,
            hashed_password="x", organization_id=org, is_active=activo))
    db.commit()

    ids = svc.ids_de_usuarios_del_ambito(db, _Usuario(ORG))
    assert ids == [f"u-sem-{ORG}-True"], (
        f"devuelve {ids!r}: tiene que traer sólo los activos de esa "
        "organización")


# -- El condicional de bi_etl que parece el defectuoso y no lo es ----------

def test_el_ajuste_global_y_el_propio_no_se_mezclan(db):
    """Los dos caminos acotan. Que nadie lo «arregle» rompiéndolo."""
    from app.models.settings import AppSetting
    from app.services import bi_etl_service as svc

    CLAVE = "bi.etl.connectors_state.test"
    db.add(AppSetting(key=CLAVE, value='{"quien": "global"}',
                      organization_id=None))
    db.add(AppSetting(key=CLAVE, value='{"quien": "mia"}',
                      organization_id=ORG))
    db.add(AppSetting(key=CLAVE, value='{"quien": "ajena"}',
                      organization_id=OTRA))
    db.commit()

    assert svc.leer_json(db, CLAVE, ORG) == {"quien": "mia"}
    assert svc.leer_json(db, CLAVE, OTRA) == {"quien": "ajena"}
    # Sin organización se lee el global, **no** la primera fila que haya.
    assert svc.leer_json(db, CLAVE, None) == {"quien": "global"}


def test_un_json_ilegible_devuelve_el_valor_por_defecto(db):
    """Un estado corrupto no debe tumbar el panel; antes era invisible."""
    from app.models.settings import AppSetting
    from app.services import bi_etl_service as svc

    CLAVE = "bi.etl.roto"
    db.add(AppSetting(key=CLAVE, value="{esto no es json",
                      organization_id=ORG))
    db.commit()

    assert svc.leer_json(db, CLAVE, ORG, default={"vacio": True}) == {
        "vacio": True}


def test_una_clave_que_no_existe_devuelve_el_valor_por_defecto(db):
    from app.services import bi_etl_service as svc

    assert svc.leer_json(db, "bi.etl.no.existe", ORG, default=[]) == []


# -- La política de MFA de la organización ---------------------------------

def test_la_politica_de_mfa_se_lee_de_la_organizacion_del_usuario(db):
    from app.models.mfa import Organization
    from app.services import auth_service as svc

    db.add(Organization(id=ORG, name="Con MFA", slug="con-mfa",
                        require_mfa=True))
    db.add(Organization(id=OTRA, name="Sin MFA", slug="sin-mfa",
                        require_mfa=False))
    db.commit()

    assert svc.organizacion_exige_mfa(db, _Usuario(ORG)) is True
    assert svc.organizacion_exige_mfa(db, _Usuario(OTRA)) is False
    # Un usuario sin organización no puede quedar obligado por la de nadie.
    assert svc.organizacion_exige_mfa(db, _Usuario(None)) is False


def test_una_organizacion_que_no_existe_no_exige_mfa(db):
    """Fail-open aquí es lo correcto y conviene que esté escrito.

    Si el id no resuelve no hay política que aplicar, y bloquear el login de un
    usuario por una fila que falta convertiría un dato inconsistente en una
    caída de acceso.
    """
    from app.services import auth_service as svc

    assert svc.organizacion_exige_mfa(db, _Usuario("org-que-no-existe")) is False


def test_guardar_el_secreto_de_mfa_no_lo_deja_activado(db):
    """El segundo factor no cuenta hasta que el usuario verifica un código."""
    from app.models.user import User, UserRole, UserStatus
    from app.services import auth_service as svc

    u = User(
        id="u-mfa", username="u-mfa", email="mfa@example.com",
        full_name="Con MFA", role=UserRole.employee,
        status=UserStatus.active, hashed_password="x", organization_id=ORG)
    db.add(u)
    db.commit()

    svc.guardar_secreto_de_mfa(db, u, "cifrado-abc")
    db.commit()

    assert u.mfa_secret == "cifrado-abc"
    assert u.mfa_enabled is False


# -- La organización existe: la comprobación anti-enumeración -------------

def test_la_comprobacion_de_existencia_no_filtra_por_organizacion(db):
    """Es para evitar enumeración de ids, y por eso mira a cualquiera.

    Quien la usa comprueba **antes** que el `org_id` recibido es el propio; esta
    función sólo responde si la fila existe. Separar las dos preguntas es lo que
    permite devolver 404 en los dos casos.
    """
    from app.core.tenancy import organizacion_existe
    from app.models.mfa import Organization

    db.add(Organization(id=ORG, name="Existe", slug="existe"))
    db.commit()

    assert organizacion_existe(db, ORG) is True
    assert organizacion_existe(db, "org-inventada") is False
    assert organizacion_existe(db, None) is False
    assert organizacion_existe(db, "") is False
