"""El Service Desk: dos endpoints de IA sin ámbito, y la columna sin rellenar.

Auditoría 2026-08 (P3-22). Tres cosas distintas, medidas por separado.

## 1. Los dos endpoints de IA buscaban el ticket por id, sin más

`/tickets/{id}/routing-candidates` y `/tickets/{id}/ai-explain` hacían
`db.query(Ticket).filter(Ticket.id == ticket_id).first()`, mientras su vecino
`ticket_detail_payload` —en el mismo módulo de servicio— usa
`scope_ticket_query`. La asimetría de siempre: dos lecturas del mismo ticket por
id, una comprobada y la otra no.

Y lo que se filtraba no era sólo el ticket: `/ai-explain` devuelve la lista de
agentes candidatos con su puntuación, es decir **los nombres y el rendimiento
del equipo de soporte de otro cliente**, colgando de `get_current_user` a secas.

## 2. La guarda estaba copiada literalmente tres veces

`get_scoped_ticket_or_404` existía por triplicado en `ticket_update_service`,
`comment_service` y `ticket_ops_service`, con la única diferencia de que dos
lanzaban el 404 sin texto. Ahora vive en `scoping.py`, junto a
`scope_ticket_query`, y las tres la reexportan. Al hacerlo cayeron **seis
imports muertos**.

## 3. `sd_tickets.organization_id` no la rellenaba nadie

Misma clase de defecto que el módulo de evaluaciones, con el alcance más grande
de todas. Medido con la clase de sesión real de la aplicación:

    ticket con organization_id = NULL  ->  usuario de su org: []   superadmin: [el ticket]

Y ninguno de los seis sitios que crean tickets pone la columna — uno lleva
además un comentario afirmando que `Ticket` no la tiene, y sí la tiene.

Las filas viejas sí tienen organización: la 076 la rellenó, pero con una lista
de nombres adivinados que decía `tickets` cuando la tabla es `sd_tickets`, así
que se la saltó; la 080 lo arregló por introspección. **Todo lo creado después
de la 080 quedó en NULL.** El escuchador `before_flush` sella las nuevas y la
migración 093 rellena las guardadas.
"""
from __future__ import annotations

import importlib.util

import pytest
from fastapi import HTTPException

ORG = "org-sd-mia"
OTRA = "org-sd-ajena"


class _Usuario:
    """Un sujeto con rol de gestión: `scope_ticket_query` acota por su organización.

    Con rol de empleado acotaría además a «los que pedí o tengo asignados», que
    es más restrictivo y taparía lo que estos tests quieren medir.
    """

    def __init__(self, organization_id, uid=None):
        self.id = uid or f"u-{organization_id}"
        self.organization_id = organization_id
        self.is_superadmin = False
        from app.models.user import UserRole
        self.role = UserRole.pm


@pytest.fixture()
def tickets_de_dos_organizaciones(db):
    """Un usuario y un ticket suyo en cada organización, más un grupo de agentes."""
    from app.models.service_desk import AgentGroup, AgentGroupMember, Ticket
    from app.models.user import User, UserRole, UserStatus

    creados = {}
    for i, org in enumerate((ORG, OTRA)):
        u = User(
            id=f"u-{org}", username=f"u-{org}", email=f"u-{org}@example.com",
            full_name=f"Agente de {org}", role=UserRole.pm,
            status=UserStatus.active, hashed_password="x", organization_id=org,
        )
        db.add(u)
        db.flush()

        # `support_level` es NOT NULL en `sd_agent_groups`.
        grupo = AgentGroup(id=f"g-{org}", name=f"Grupo de {org}",
                           support_level="L1", organization_id=org)
        db.add(grupo)
        db.flush()
        db.add(AgentGroupMember(id=f"m-{org}", group_id=grupo.id, user_id=u.id))

        t = Ticket(
            id=f"t-{org}", number=f"SD-{100 + i}", ticket_type="incident",
            title=f"Ticket de {org}", description="x",
            organization_id=org, created_by_user_id=u.id,
            requester_user_id=u.id, assigned_group_id=grupo.id,
        )
        db.add(t)
        db.flush()
        creados[org] = {"usuario": u, "ticket": t, "grupo": grupo}
    db.commit()
    return creados


# -- 1. Los dos endpoints de IA ---------------------------------------------

def test_EL_HALLAZGO_los_candidatos_de_un_ticket_ajeno_dan_404(
    db, tickets_de_dos_organizaciones
):
    from app.services.service_desk import ticket_read_service as svc

    ajeno = tickets_de_dos_organizaciones[OTRA]["ticket"]
    with pytest.raises(HTTPException) as exc:
        svc.candidatos_de_asignacion(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404

    mio = tickets_de_dos_organizaciones[ORG]["ticket"]
    datos = svc.candidatos_de_asignacion(db, _Usuario(ORG), mio.id)
    assert datos["ticket_number"] == mio.number
    assert datos["score_weights"] == svc.PESOS_DEL_SCORE_DE_ASIGNACION


def test_EL_ESCENARIO_la_consulta_de_antes_devuelve_el_ticket_ajeno(
    db, tickets_de_dos_organizaciones
):
    """Que el escenario es real, para que los dos de arriba prueben algo.

    Se reproduce la consulta **tal como estaba** en el endpoint. Si esto dejara
    de devolver el ticket ajeno seria porque el filtro implicito de
    `TenantSession` se ha activado en la suite, y entonces los tests de arriba
    pasarian igual contra el codigo defectuoso.
    """
    from app.models.service_desk import Ticket

    ajeno = tickets_de_dos_organizaciones[OTRA]["ticket"]
    fila = db.query(Ticket).filter(Ticket.id == ajeno.id).first()
    assert fila is not None and fila.organization_id == OTRA, (
        "la consulta sin ambito ya no alcanza el ticket de otro cliente; "
        "revisar si estos tests siguen midiendo lo que dicen")


def test_un_ticket_sin_grupo_da_400_y_no_404(db, tickets_de_dos_organizaciones):
    """El 400 distingue «no tiene grupo» de «no es tuyo», y eso importa."""
    from app.services.service_desk import ticket_read_service as svc

    mio = tickets_de_dos_organizaciones[ORG]["ticket"]
    mio.assigned_group_id = None
    db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.candidatos_de_asignacion(db, _Usuario(ORG), mio.id)
    assert exc.value.status_code == 400


def test_EL_HALLAZGO_la_explicacion_de_ia_de_un_ticket_ajeno_no_devuelve_nada(
    db, tickets_de_dos_organizaciones
):
    """Devolvía el ticket Y la puntuación de los agentes del otro cliente."""
    from app.services.service_desk import ticket_read_service as svc

    ajeno = tickets_de_dos_organizaciones[OTRA]["ticket"]
    datos = svc.explicacion_de_decision_de_ia(db, _Usuario(ORG), ajeno.id)
    assert datos == {"ok": False, "error": "Ticket no encontrado"}, (
        "la explicación de IA está devolviendo el ticket de otro cliente")

    mio = tickets_de_dos_organizaciones[ORG]["ticket"]
    datos = svc.explicacion_de_decision_de_ia(db, _Usuario(ORG), mio.id)
    assert datos["ticket_id"] == mio.id
    assert "auto_resolution" in datos
    # El agente del propio grupo sí sale, con su puntuación.
    assert [c["user_id"] for c in datos["assignment_candidates"]] == [f"u-{ORG}"]
    assert datos["confidence_trace"]["auto_resolution_threshold"] == (
        svc.UMBRAL_DE_AUTO_RESOLUCION)


# -- 2. La guarda, una sola vez ---------------------------------------------

def test_EL_ESTRUCTURAL_la_guarda_del_ticket_es_una_sola_funcion():
    """Estaba copiada literalmente en tres módulos.

    Se comprueba la identidad del objeto, no que el código sea parecido: si
    alguien vuelve a escribir una copia local, esto se pone en rojo.
    """
    from app.services.service_desk import (
        comment_service,
        scoping,
        ticket_ops_service,
        ticket_update_service,
    )

    canonica = scoping.get_scoped_ticket_or_404
    for modulo in (ticket_update_service, comment_service, ticket_ops_service):
        assert modulo.get_scoped_ticket_or_404 is canonica, (
            f"{modulo.__name__} tiene su propia copia de la guarda")


def test_la_guarda_da_404_con_texto(db, tickets_de_dos_organizaciones):
    """Dos de las tres copias lanzaban el 404 pelado, sin `detail`."""
    from app.services.service_desk.scoping import get_scoped_ticket_or_404

    ajeno = tickets_de_dos_organizaciones[OTRA]["ticket"]
    with pytest.raises(HTTPException) as exc:
        get_scoped_ticket_or_404(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Ticket no encontrado"


# -- 3. La columna que nadie rellenaba --------------------------------------

def test_EL_HALLAZGO_un_ticket_sin_organizacion_no_lo_ve_su_propia_organizacion(db):
    """El escenario de antes del sellado, medido y no contado.

    El filtro se engancha a mano porque la suite usa otra factoría de sesiones y
    no lo dispara en ningún test. Sin engancharlo, este test pasaría igual
    contra el código defectuoso.
    """
    from sqlalchemy import event as sa_event

    from app.db.session import _enforce_tenant_isolation
    from app.models.service_desk import Ticket

    db.add(Ticket(id="t-sin-org", number="SD-900", ticket_type="incident",
                  title="Sin organizacion", description="x",
                  organization_id=None))
    db.add(Ticket(id="t-con-org", number="SD-901", ticket_type="incident",
                  title="Con organizacion", description="x",
                  organization_id=ORG))
    db.commit()

    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    db.info["is_superadmin"] = False
    db.info["organization_id"] = ORG
    try:
        vistos = {t.id for t in db.query(Ticket).all()}
        assert "t-con-org" in vistos
        assert "t-sin-org" not in vistos, (
            "un ticket con organización NULL ya es visible: el filtro ha "
            "cambiado y este test deja de medir lo que dice")
    finally:
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)


def test_el_sellado_del_flush_pone_la_organizacion_en_un_ticket_nuevo(db):
    """El arreglo de raíz: ningún sitio de creación tiene que acordarse."""
    from sqlalchemy import event as sa_event

    from app.db.session import _sellar_organizacion
    from app.models.service_desk import Ticket

    def escuchador(sesion, contexto_de_flush, instancias):
        _sellar_organizacion(sesion)

    sa_event.listen(db, "before_flush", escuchador)
    db.info["organization_id"] = ORG
    try:
        t = Ticket(id="t-sellado", number="SD-902", ticket_type="incident",
                   title="Sellado", description="x")
        db.add(t)
        db.flush()
        assert t.organization_id == ORG
    finally:
        sa_event.remove(db, "before_flush", escuchador)
        db.info.pop("organization_id", None)


def _ejecutar_migracion_093(db):
    """Corre el `upgrade()` de la 093 contra el enlace de esta sesión.

    La migración usa `op` para una sola cosa, `op.get_bind()`, así que se
    sustituye por un doble. Así se ejecuta el SQL de verdad sin montar el
    entorno completo de alembic.
    """
    ruta = "alembic/versions/093_tickets_backfill_organization.py"
    spec = importlib.util.spec_from_file_location("mig093_test", ruta)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    # `db.connection()` da la conexion de la transaccion de esta sesion;
    # `get_bind()` daria el Engine, que no tiene `execute()`.
    enlace = db.connection()

    class _OpDoble:
        @staticmethod
        def get_bind():
            return enlace

    mig.op = _OpDoble
    mig.upgrade()
    db.commit()
    db.expire_all()
    return mig


def test_la_migracion_093_hereda_la_organizacion_del_creador_y_del_padre(db):
    """Las seis referencias, su orden de preferencia, y lo que NO toca."""
    from app.models.clients import Client
    from app.models.project import Project, ProjectType
    from app.models.service_desk import Ticket, TicketComment
    from app.models.user import User, UserRole, UserStatus

    db.add(User(id="mu-a", username="mua", email="mua@x.com", full_name="A",
                role=UserRole.employee, status=UserStatus.active,
                hashed_password="x", organization_id="MIG-A"))
    db.add(Project(id="mp-c", name="Proyecto C", code="MPC",
                   project_type=ProjectType.development,
                   organization_id="MIG-C"))
    db.add(Client(id="mc-d", name="Cliente D", organization_id="MIG-D"))
    db.flush()

    casos = [
        ("mt-creador", {"created_by_user_id": "mu-a"}, "MIG-A"),
        ("mt-proyecto", {"project_id": "mp-c"}, "MIG-C"),
        ("mt-cliente", {"client_id": "mc-d"}, "MIG-D"),
        ("mt-huerfano", {}, None),
        # La precedencia: el creador manda sobre el proyecto.
        ("mt-orden", {"created_by_user_id": "mu-a", "project_id": "mp-c"}, "MIG-A"),
    ]
    for i, (tid, campos, _esperado) in enumerate(casos):
        db.add(Ticket(id=tid, number=f"SD-{800 + i}", ticket_type="incident",
                      title=tid, description="x", organization_id=None, **campos))
    # Uno que ya tiene organización: la migración no debe tocarlo.
    db.add(Ticket(id="mt-yatiene", number="SD-899", ticket_type="incident",
                  title="ya tiene", description="x", organization_id="MIG-Z",
                  created_by_user_id="mu-a"))
    db.flush()
    db.add(TicketComment(id="mcm-1", ticket_id="mt-proyecto", body="hola",
                         organization_id=None))
    db.commit()

    _ejecutar_migracion_093(db)

    for tid, _campos, esperado in casos:
        real = db.query(Ticket).filter(Ticket.id == tid).first().organization_id
        assert real == esperado, f"{tid}: esperado {esperado}, real {real}"

    intacto = db.query(Ticket).filter(Ticket.id == "mt-yatiene").first()
    assert intacto.organization_id == "MIG-Z", (
        "la migración ha reescrito una organización que ya estaba puesta")

    # La hija hereda del ticket, que a su vez heredó del proyecto.
    hija = db.query(TicketComment).filter(TicketComment.id == "mcm-1").first()
    assert hija.organization_id == "MIG-C"


def test_la_migracion_093_no_reparte_al_cliente_por_defecto(db):
    """La 076 y la 080 usaban la organización por defecto como respaldo.

    En un despliegue con varios clientes eso le entrega al primero las filas de
    los demás. Un ticket sin ninguna referencia se queda en NULL: no hay de
    dónde deducirlo, e inventarlo sería peor.
    """
    from app.models.service_desk import Ticket

    db.add(Ticket(id="mt-solo", number="SD-880", ticket_type="incident",
                  title="sin referencias", description="x",
                  organization_id=None))
    db.commit()

    _ejecutar_migracion_093(db)

    fila = db.query(Ticket).filter(Ticket.id == "mt-solo").first()
    assert fila.organization_id is None
