from typing import Optional

from sqlalchemy.orm import Session, object_session
from sqlalchemy.orm.exc import UnmappedInstanceError
from sqlalchemy import and_, false, or_

from app.models.clients import Client
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.service_desk import ConfigurationItem, KBArticle, Problem, SLAPolicy, Ticket
from app.models.user import User, UserRole
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def resolve_sla_policy_for_ticket(
    db: Session,
    *,
    contract_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> Optional[SLAPolicy]:
    """Resolve SLA by precedence: contract -> client -> default active policy."""
    if contract_id:
        ctr = db.query(Contract).filter(Contract.id == contract_id).first()
        if ctr and getattr(ctr, "sla_policy_id", None):
            p = db.query(SLAPolicy).filter(
                SLAPolicy.id == ctr.sla_policy_id,
                SLAPolicy.is_active == True,
            ).first()
            if p:
                return p

    if client_id:
        cli = db.query(Client).filter(Client.id == client_id).first()
        if cli and getattr(cli, "sla_policy_id", None):
            p = db.query(SLAPolicy).filter(
                SLAPolicy.id == cli.sla_policy_id,
                SLAPolicy.is_active == True,
            ).first()
            if p:
                return p

    return db.query(SLAPolicy).filter(
        SLAPolicy.is_default == True,
        SLAPolicy.is_active == True,
    ).first()


def empresa_activa(user) -> Optional[str]:
    """La empresa ACTIVA de la peticion (la del token, validada en
    `deps.get_current_user` y guardada en `db.info`), no la de la ficha.

    Auditoria 2026-11-22 (A-SD13): con pertenencia a varias empresas, los
    endpoints de IA, del agente autonomo y del catalogo usaban
    `user.organization_id` (la de la ficha) y trabajaban sobre otra empresa
    que la elegida. Un superadministrador no tiene empresa activa (`None` en
    `db.info`): se conserva la de su ficha para no convertir sus escrituras de
    configuracion en globales.
    """
    if user is None:
        return None
    if getattr(user, "is_superadmin", False):
        return getattr(user, "organization_id", None)
    try:
        sesion = object_session(user)
    except UnmappedInstanceError:
        # Un principal que no es una fila (sujeto de sistema, doble de pruebas):
        # no hay sesion de la que leer la empresa activa; vale la suya.
        sesion = None
    if sesion is not None and "organization_id" in sesion.info:
        return sesion.info.get("organization_id")
    return getattr(user, "organization_id", None)


def _org_user_ids_subquery(db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return None
    return db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()


def _org_project_ids_subquery(db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return None
    return db.query(Project.id).filter(
        Project.organization_id == current_user.organization_id
    ).scalar_subquery()


def scope_ticket_query(q, db: Session, current_user: User):
    """Los tickets que el usuario puede ver.

    Auditoria 2026-11 (medido): para un administrador o PM, un ticket solo era
    visible si su solicitante, su agente o su creador era un usuario de la
    organizacion. Un ticket del portal o del correo sin agente no tiene
    ninguno de los tres, asi que no salia en ningun listado — tampoco en la
    cola, que es donde tienen que estar los sin asignar. Ahora manda la
    organizacion del ticket; la regla por usuarios queda para las filas
    antiguas sin organizacion.

    Un empleado ve ademas los tickets cuya aprobacion le toca: sin eso no
    podia abrir el que le pedian aprobar.
    """
    if current_user.is_superadmin:
        return q
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        from app.models.service_desk import TicketApproval
        por_aprobar = db.query(TicketApproval.ticket_id).filter(
            TicketApproval.approver_user_id == current_user.id,
        ).scalar_subquery()
        return q.filter(
            or_(
                Ticket.requester_user_id == current_user.id,
                Ticket.assigned_to_user_id == current_user.id,
                # Lo que abrio en nombre de otro (el solicitante es el cliente).
                Ticket.created_by_user_id == current_user.id,
                Ticket.id.in_(por_aprobar),
            )
        )
    org = empresa_activa(current_user)
    if org:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == org
        ).scalar_subquery()
        return q.filter(
            or_(
                Ticket.organization_id == org,
                and_(
                    Ticket.organization_id.is_(None),
                    or_(
                        Ticket.requester_user_id.in_(org_user_ids),
                        Ticket.assigned_to_user_id.in_(org_user_ids),
                        Ticket.created_by_user_id.in_(org_user_ids),
                    ),
                ),
            )
        )
    # Auditoria 2026-11-22: sin empresa y sin ser superadministrador no se ve
    # nada (antes, `return q`: todos los tickets si la sesion no filtraba).
    return q.filter(false())


def get_scoped_ticket_or_404(
    db: Session, current_user: Optional[User], ticket_id: str
) -> Ticket:
    """El ticket por id, si el sujeto puede verlo. 404 si no.

    Auditoria 2026-08 (hallazgo 22). Esta funcion estaba **copiada literalmente
    tres veces** —en `ticket_update_service`, `comment_service` y
    `ticket_ops_service`—, con la unica diferencia de que dos de las copias
    lanzaban el 404 sin texto. Vive aqui porque aqui vive
    `scope_ticket_query`, que es de lo que depende.

    El ambito no es solo la organizacion: `scope_ticket_query` restringe ademas
    a un empleado o subcontratado a los tickets que pidio o tiene asignados, asi
    que filtrar por `organization_id` a secas seria MAS PERMISIVO que esto y
    dejaria la lectura de uno suelto por detras del listado.
    """
    ticket = (
        scope_ticket_query(db.query(Ticket), db, current_user)
        .filter(Ticket.id == ticket_id)
        .first()
    )
    if not ticket:
        raise error(404, "no_encontrado", detail="Ticket no encontrado", que="ticket")
    return ticket


def scope_problem_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    org_project_ids = _org_project_ids_subquery(db, current_user)
    if org_user_ids is None or org_project_ids is None:
        return q.filter(False)
    return q.filter(
        or_(
            Problem.owner_user_id.in_(org_user_ids),
            Problem.project_id.in_(org_project_ids),
            Problem.ci_id.in_(
                db.query(ConfigurationItem.id).filter(
                    ConfigurationItem.project_id.in_(org_project_ids)
                ).scalar_subquery()
            ),
        )
    )


def scope_ci_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    org_project_ids = _org_project_ids_subquery(db, current_user)
    if org_user_ids is None or org_project_ids is None:
        return q.filter(False)
    # Auditoria 2026-11: se acotaba solo por responsable o proyecto, asi que un
    # CI sin ninguno de los dos —todos los descubiertos— no lo veia nadie.
    # Manda la organizacion del CI; responsable y proyecto quedan para filas
    # viejas sin ella.
    return q.filter(
        or_(
            ConfigurationItem.organization_id == current_user.organization_id,
            and_(
                ConfigurationItem.organization_id.is_(None),
                or_(
                    ConfigurationItem.owner_user_id.in_(org_user_ids),
                    ConfigurationItem.project_id.in_(org_project_ids),
                ),
            ),
        )
    )


def scope_kb_query(q, db: Session, current_user: User):
    """Articulos de la organizacion del usuario.

    Auditoria 2026-11: se acotaba por el autor, asi que un articulo sin autor
    (importado, o creado por el sistema) no lo veia nadie. Manda la
    organizacion del articulo; el autor queda para filas viejas sin ella.
    """
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    if org_user_ids is None:
        return q.filter(False)
    return q.filter(or_(
        KBArticle.organization_id == current_user.organization_id,
        and_(KBArticle.organization_id.is_(None), KBArticle.author_id.in_(org_user_ids)),
    ))
