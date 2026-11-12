"""Los once endpoints que la interfaz llamaba y no existían.

Auditoría 2026-08, hallazgo 37 — **cerrado**. `DESAJUSTES_CONOCIDOS` pasa de 62
a 11 y de 11 a **0** en `test_rutas_del_frontend.py`.

Los once no eran un grupo homogéneo, y por eso ninguno se arregló igual:

**Cuatro `GET` de detalle cuyo CRUD estaba completo salvo la lectura de uno.**
`contractsApi`, `risksApi` y `usePipeline` tienen listar, crear, actualizar y
borrar; leer uno era la única cuya ruta no estaba. No hubo nada que inventar: la
búsqueda acotada y el serializador son los que ya usan el `PATCH` y el `DELETE`
de al lado. En el de oportunidades esa búsqueda estaba **copiada literalmente
tres veces** y se extrajo a `oportunidad_propia`.

**Dos manejadores escritos y sin registrar.** `update_certification` y
`delete_certification` existían completos, con su comprobación de permisos —sólo
el dueño de la certificación, o admin/RRHH— y **sin decorador de ruta**. No eran
endpoints que faltaran: eran endpoints que nadie registró, así que la interfaz
podía crear una certificación y no editarla ni borrarla. Un barrido por AST dice
que son **los dos únicos** casos en toda `app/api/`.

**Tres borrados que no hacían nada**, y ninguno se resuelve borrando la fila:

* un **problema** es el registro de una investigación, con su análisis de causa
  raíz y sus incidentes vinculados: se cierra;
* un **cambio** es un registro de gobernanza con aprobaciones y plan de
  rollback: se cancela — y uno ya implementado responde **409**, porque
  cancelar lo que ya pasó sería reescribir la historia;
* una **integración OAuth** guarda su historial de sincronización, que sirve
  para diagnosticar: se desactiva **y se borran los tokens**, que es lo que de
  verdad hay que quitar.

**El listado de tickets de un Known Error**, cuyo modelo ya existía —la tabla de
unión `sd_known_error_tickets`— y sólo faltaba exponerlo.

**Y los dos exports de la pantalla de exportaciones.** El de imputaciones existía
con otro verbo y otra ruta (`GET /analytics/exports/imputations-csv`); el de
proyectos no existía en absoluto y hubo que añadirlo — el export de *recursos*
no sirve, exporta utilización por persona y semana. Al mirarlo apareció un
defecto de propina: `imp.task.name`, y `Task` tiene `title`, así que **el export
de imputaciones fallaba** en cuanto una imputación tenía tarea.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio

ORG = "org-h37"


class _Usuario:
    def __init__(self, organization_id=ORG, superadmin=False, role=None):
        from app.models.user import UserRole

        self.id = "u-h37"
        self.organization_id = organization_id
        self.is_superadmin = superadmin
        self.role = role or UserRole.admin


def _crear_usuario(db, uid="u-h37", org=ORG):
    """El sujeto, como fila.

    Hace falta de verdad: `scope_change_query` y `_scope_problem_query` acotan
    por **los ids de usuario de la organización**, no por `organization_id` de
    la fila, así que sin un `User` en la base el ámbito sale vacío y todo da
    404. Es la misma forma de acotar que tienen los tickets.
    """
    from app.models.user import User, UserRole, UserStatus

    if db.query(User).filter(User.id == uid).first():
        return
    db.add(User(
        id=uid, username=uid, email=f"{uid}@example.com", full_name="Sujeto",
        role=UserRole.admin, status=UserStatus.active,
        hashed_password="x", organization_id=org))
    db.flush()


# -- Los cuatro GET de detalle ---------------------------------------------

def test_las_rutas_de_detalle_estan_registradas():
    """El estructural: las cuatro que la interfaz llamaba y devolvían 404."""
    from app.main import app

    rutas = {
        (m, getattr(r, "path", ""))
        for r in app.router.routes
        for m in (getattr(r, "methods", None) or [])
    }
    esperadas = [
        ("GET", "/api/v1/contracts/{contract_id}"),
        ("GET", "/api/v1/risks/{project_id}/{risk_id}"),
        ("GET", "/api/v1/pipeline/{opp_id}"),
        ("PATCH", "/api/v1/training/certifications/{cert_id}"),
        ("DELETE", "/api/v1/training/certifications/{cert_id}"),
        ("DELETE", "/api/v1/sd/problems/{problem_id}"),
        ("DELETE", "/api/v1/sd/changes/{change_id}"),
        ("DELETE", "/api/v1/oauth-integrations/{integration_id}"),
        ("GET", "/api/v1/sd/known-errors/{known_error_id}/tickets"),
        ("GET", "/api/v1/analytics/exports/projects-csv"),
    ]
    faltan = [f"{m} {p}" for m, p in esperadas if (m, p) not in rutas]
    assert not faltan, f"estas rutas no están registradas: {faltan}"


def test_la_oportunidad_de_otro_cliente_da_404(db):
    """La guarda extraída de las tres copias: `oportunidad_propia`."""
    from app.models.pipeline import Opportunity
    from app.models.user import User, UserRole, UserStatus
    from app.services import pipeline_service as svc

    for i, org in enumerate((ORG, "org-ajena-h37")):
        db.add(User(
            id=f"dueno-{org}", username=f"dueno-{org}",
            email=f"dueno-{org}@example.com", full_name="Dueño",
            role=UserRole.pm, status=UserStatus.active,
            hashed_password="x", organization_id=org))
        db.flush()
        # `opportunities.code` es UNIQUE: el indice, no el nombre de la org.
        db.add(Opportunity(
            id=f"opp-{org}", code=f"OPP-H37-{i}", name=f"Oportunidad de {org}",
            client_name="Cliente", owner_id=f"dueno-{org}",
            organization_id=org))
    db.commit()

    mia = svc.oportunidad_propia(db, _Usuario(ORG), f"opp-{ORG}")
    assert mia.id == f"opp-{ORG}"

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.oportunidad_propia(db, _Usuario(ORG), "opp-org-ajena-h37")
    assert exc.value.status_code == 404


def test_una_oportunidad_borrada_no_se_devuelve(db):
    """El `is_active` de la guarda no es decorativo: el borrado es lógico."""
    from app.models.pipeline import Opportunity
    from app.models.user import User, UserRole, UserStatus
    from app.services import pipeline_service as svc

    db.add(User(
        id="dueno-borr", username="dueno-borr", email="borr@example.com",
        full_name="Dueño", role=UserRole.pm, status=UserStatus.active,
        hashed_password="x", organization_id=ORG))
    db.flush()
    db.add(Opportunity(
        id="opp-borrada", code="OPP-BOR", name="Ya borrada",
        client_name="Cliente", owner_id="dueno-borr",
        organization_id=ORG, is_active=False))
    db.commit()

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.oportunidad_propia(db, _Usuario(ORG), "opp-borrada")
    assert exc.value.status_code == 404


def test_EL_ESTRUCTURAL_la_guarda_de_oportunidad_es_una_sola(db):
    """Estaba copiada literal en tres funciones del servicio.

    Se comprueba que las tres la usan: si alguien vuelve a escribir la consulta
    a mano, esto no lo caza — pero el número de copias sí, y por eso se cuenta.
    """
    import ast
    import io

    fuente = io.open("app/services/pipeline_service.py", encoding="utf-8").read()
    copias = fuente.count("scope_opportunity_query(\n        db.query(Opportunity), db, current_user\n    ).filter(Opportunity.id == opp_id")
    assert copias == 0, (
        f"quedan {copias} copias de la búsqueda de oportunidad por id; usa "
        "`oportunidad_propia`")

    arbol = ast.parse(fuente)
    nombres = {
        f.name for f in arbol.body
        if isinstance(f, ast.FunctionDef)
        and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "oportunidad_propia" for n in ast.walk(f))
    }
    assert {"update_opportunity", "delete_opportunity",
            "convert_opportunity_to_project"} <= nombres, (
        f"sólo la usan {sorted(nombres)}")


# -- Los tres borrados que no borran --------------------------------------

def test_cerrar_un_problema_lo_cierra_y_es_idempotente(db):
    """El botón de borrar de `ITSMKnowledgeTab` no hacía nada."""
    from app.models.service_desk import Problem, ProblemStatus
    from app.services.service_desk import problem_service as svc

    _crear_usuario(db)
    db.add(Problem(
        id="prob-h37", number="PRB-1", title="Un problema",
        description="x", status=ProblemStatus.open, organization_id=ORG,
        owner_user_id="u-h37"))
    db.commit()

    datos = svc.cerrar_problema(db, _Usuario(ORG), "prob-h37")
    db.commit()
    assert datos["status"] == "closed"
    assert datos["already_closed"] is False

    p = db.query(Problem).filter(Problem.id == "prob-h37").first()
    assert p.status == ProblemStatus.closed
    assert p.resolved_at is not None, (
        "cerrar un problema tiene que dejar cuándo se cerró")

    # Idempotente, y sin pisar la fecha original.
    marca = p.resolved_at
    otra = svc.cerrar_problema(db, _Usuario(ORG), "prob-h37")
    db.commit()
    assert otra["already_closed"] is True
    db.refresh(p)
    assert p.resolved_at == marca


def test_el_problema_de_otro_cliente_no_se_cierra(db):
    from app.models.service_desk import Problem, ProblemStatus
    from app.services.service_desk import problem_service as svc

    _crear_usuario(db)
    _crear_usuario(db, "u-otro", "org-ajena-h37")
    db.add(Problem(
        id="prob-ajeno", number="PRB-9", title="De otro",
        description="x", status=ProblemStatus.open,
        organization_id="org-ajena-h37", owner_user_id="u-otro"))
    db.commit()

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.cerrar_problema(db, _Usuario(ORG), "prob-ajeno")
    assert exc.value.status_code == 404

    p = db.query(Problem).filter(Problem.id == "prob-ajeno").first()
    assert p.status == ProblemStatus.open, "se ha cerrado el problema de otro"


def test_cancelar_un_cambio_lo_cancela(db):
    from app.models.service_desk import ChangeStatus, ITSMChangeRequest
    from app.services.service_desk import change_service as svc

    _crear_usuario(db)
    db.add(ITSMChangeRequest(
        id="chg-h37", number="CHG-1", title="Un cambio", description="x",
        status=ChangeStatus.submitted, organization_id=ORG,
        requester_id="u-h37"))
    db.commit()

    datos = svc.cancelar_cambio(db, _Usuario(ORG), "chg-h37")
    db.commit()
    assert datos["status"] == "cancelled"

    cr = db.query(ITSMChangeRequest).filter(
        ITSMChangeRequest.id == "chg-h37").first()
    assert cr.status == ChangeStatus.cancelled


@pytest.mark.parametrize("estado", ["implemented", "closed_success",
                                    "closed_failed"])
def test_un_cambio_ya_ejecutado_no_se_cancela(db, estado):
    """409 y no 400: el conflicto es con el estado del recurso.

    Cancelar un cambio ya implementado sería reescribir lo que pasó.
    """
    from app.models.service_desk import ChangeStatus, ITSMChangeRequest
    from app.services.service_desk import change_service as svc

    _crear_usuario(db)
    db.add(ITSMChangeRequest(
        id=f"chg-{estado}", number=f"CHG-{estado[:3]}", title="Ejecutado",
        description="x", status=ChangeStatus(estado), organization_id=ORG,
        requester_id="u-h37"))
    db.commit()

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.cancelar_cambio(db, _Usuario(ORG), f"chg-{estado}")
    assert exc.value.status_code == 409
    assert estado in str(exc.value.detail)


def test_desactivar_una_integracion_borra_sus_tokens(db):
    """Dejar un token de un tercero en una fila desactivada es guardar una
    credencial que ya no se usa."""
    from app.models.cab import IntegrationConfig, IntegrationType
    from app.services import cab_service as svc

    db.add(IntegrationConfig(
        id="int-h37", integration_type=IntegrationType.github,
        name="GitHub", access_token="tok-acceso",
        refresh_token="tok-refresco", organization_id=ORG))
    db.commit()

    datos = svc.desactivar_integracion(db, "int-h37")
    assert datos["deactivated"] is True

    fila = db.query(IntegrationConfig).filter(
        IntegrationConfig.id == "int-h37").first()
    assert fila is not None, "la fila no se borra: guarda el historial de sync"
    assert fila.is_active is False
    assert fila.access_token is None
    assert fila.refresh_token is None
    assert fila.token_expires_at is None


def test_desactivar_una_integracion_que_no_existe_da_404(db):
    from app.services import cab_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.desactivar_integracion(db, "no-existe")
    assert exc.value.status_code == 404


# -- Los tickets de un Known Error ----------------------------------------

def test_los_tickets_de_un_error_conocido(db):
    from app.models.service_desk import (
        KnownErrorTicket, Problem, ProblemStatus, Ticket,
    )
    from app.services.service_desk import known_error_service as svc

    _crear_usuario(db)
    db.add(Problem(
        id="ke-h37", number="PRB-KE", title="Error conocido",
        description="x", status=ProblemStatus.known_error,
        organization_id=ORG, owner_user_id="u-h37"))
    db.add(Ticket(
        id="t-ke", number="SD-KE", ticket_type="incident",
        title="Ticket del error", description="x", organization_id=ORG))
    db.flush()
    db.add(KnownErrorTicket(
        id="ket-1", known_error_id="ke-h37", ticket_id="t-ke",
        organization_id=ORG))
    db.commit()

    items = svc.tickets_de_un_error_conocido(db, _Usuario(ORG), "ke-h37")
    assert len(items) == 1
    assert items[0]["number"] == "SD-KE"
    assert items[0]["title"] == "Ticket del error"


def test_un_error_conocido_sin_tickets_devuelve_lista_vacia(db):
    from app.models.service_desk import Problem, ProblemStatus
    from app.services.service_desk import known_error_service as svc

    _crear_usuario(db)
    db.add(Problem(
        id="ke-vacio", number="PRB-KV", title="Sin tickets",
        description="x", status=ProblemStatus.known_error,
        organization_id=ORG, owner_user_id="u-h37"))
    db.commit()

    assert svc.tickets_de_un_error_conocido(db, _Usuario(ORG), "ke-vacio") == []


def test_los_tickets_de_un_error_conocido_ajeno_dan_404(db):
    from app.models.service_desk import Problem, ProblemStatus
    from app.services.service_desk import known_error_service as svc

    _crear_usuario(db)
    _crear_usuario(db, "u-otro", "org-ajena-h37")
    db.add(Problem(
        id="ke-ajeno", number="PRB-KA", title="De otro",
        description="x", status=ProblemStatus.known_error,
        organization_id="org-ajena-h37", owner_user_id="u-otro"))
    db.commit()

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.tickets_de_un_error_conocido(db, _Usuario(ORG), "ke-ajeno")
    assert exc.value.status_code == 404
