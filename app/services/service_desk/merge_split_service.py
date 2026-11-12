from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket, TicketComment, TicketLink, TicketMerge, TicketStatus
from app.services.sla_service import log_history, next_ticket_number
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def get_ticket_or_404(db: Session, ticket_id: str, detail: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404, detail)
    return ticket


def ensure_distinct_tickets(primary: Ticket, duplicate: Ticket) -> None:
    if primary.id == duplicate.id:
        raise ErrorDeDominio(400, "No se puede fusionar un ticket consigo mismo")


def apply_duplicate_closure(primary: Ticket, duplicate: Ticket) -> None:
    duplicate.status = TicketStatus.closed
    duplicate.resolution = f"Ticket duplicado. Fusionado en {primary.number}."
    duplicate.closed_at = datetime.now(timezone.utc)


def transfer_ticket_comments(db: Session, source_ticket_id: str, target_ticket_id: str) -> None:
    db.query(TicketComment).filter(TicketComment.ticket_id == source_ticket_id).update(
        {"ticket_id": target_ticket_id}, synchronize_session=False
    )


def build_merge_log(primary_id: str, merged_id: str, reason: str, merged_by_user: str) -> TicketMerge:
    return TicketMerge(
        primary_id=primary_id,
        merged_id=merged_id,
        reason=reason,
        merged_by_user=merged_by_user,
    )


def merge_ticket_record(db: Session, ticket_id: str, merged_ticket_id: str, reason: str, merged_by_user: str):
    primary = get_ticket_or_404(db, ticket_id, "Ticket primario no encontrado")
    duplicate = get_ticket_or_404(db, merged_ticket_id, "Ticket a fusionar no encontrado")
    ensure_distinct_tickets(primary, duplicate)

    apply_duplicate_closure(primary, duplicate)
    transfer_ticket_comments(db, duplicate.id, primary.id)
    merge_log = build_merge_log(primary.id, duplicate.id, reason, merged_by_user)

    return primary, duplicate, merge_log


def derive_split_title(parent: Ticket, payload_title: str) -> str:
    return payload_title or f"{parent.title} (split)"


def derive_split_description(parent: Ticket, payload_description: str) -> str:
    return payload_description or parent.description


def derive_split_priority(parent: Ticket, payload_priority: str):
    return payload_priority or (parent.priority.value if hasattr(parent.priority, "value") else parent.priority)


def derive_split_type(parent: Ticket, payload_type: str):
    return payload_type or (parent.ticket_type.value if hasattr(parent.ticket_type, "value") else parent.ticket_type)


def build_child_ticket(parent: Ticket, child_number: str, child_type, child_title: str, child_description: str, child_priority, payload, created_by_user_id: str) -> Ticket:
    return Ticket(
        number=child_number,
        ticket_type=child_type,
        title=child_title,
        description=child_description,
        priority=child_priority,
        urgency=payload.urgency or parent.urgency,
        impact=payload.impact or parent.impact,
        support_level=payload.support_level or parent.support_level,
        status=TicketStatus.new,
        requester_user_id=parent.requester_user_id,
        requester_client_id=parent.requester_client_id,
        requester_name=parent.requester_name,
        requester_email=parent.requester_email,
        project_id=parent.project_id,
        client_id=parent.client_id,
        contract_id=parent.contract_id,
        ci_id=parent.ci_id,
        service_item_id=parent.service_item_id,
        sla_policy_id=parent.sla_policy_id,
        tags=payload.tags if payload.tags is not None else parent.tags,
        source=parent.source,
        parent_ticket_id=parent.id,
        created_by_user_id=created_by_user_id,
    )


def build_child_link(parent_id: str, child_id: str, created_by: str) -> TicketLink:
    return TicketLink(
        source_id=parent_id,
        target_id=child_id,
        link_type="child_of",
        created_by=created_by,
    )


def copy_latest_comments_to_child(db: Session, parent_id: str, child_id: str, count: int) -> None:
    if count <= 0:
        return
    comments = db.query(TicketComment).filter(
        TicketComment.ticket_id == parent_id
    ).order_by(TicketComment.created_at.desc()).limit(count).all()
    for comment in reversed(comments):
        db.add(TicketComment(
            ticket_id=child_id,
            body=comment.body,
            is_public=comment.is_public,
            is_solution=False,
            author_user_id=comment.author_user_id,
            author_client_id=comment.author_client_id,
            author_name=comment.author_name,
        ))


def split_ticket_record(
    db: Session,
    ticket_id: str,
    payload,
    next_ticket_number_for_type,
    created_by_user_id: str,
):
    parent = get_ticket_or_404(db, ticket_id, "Ticket origen no encontrado")

    child_title = derive_split_title(parent, payload.title)
    child_description = derive_split_description(parent, payload.description)
    child_priority = derive_split_priority(parent, payload.priority)
    child_type = derive_split_type(parent, payload.ticket_type)
    child_number = next_ticket_number_for_type(child_type)

    child = build_child_ticket(
        parent=parent,
        child_number=child_number,
        child_type=child_type,
        child_title=child_title,
        child_description=child_description,
        child_priority=child_priority,
        payload=payload,
        created_by_user_id=created_by_user_id,
    )
    db.add(child)
    db.flush()

    link = build_child_link(parent.id, child.id, created_by_user_id)
    db.add(link)
    copy_latest_comments_to_child(db, parent.id, child.id, payload.copy_latest_comments)

    return parent, child


def list_ticket_merges(db: Session, ticket_id: str):
    return (
        db.query(TicketMerge)
        .options(
            joinedload(TicketMerge.merged_ticket),
            joinedload(TicketMerge.merged_by),
        )
        .filter(TicketMerge.primary_id == ticket_id)
        .all()
    )


def serialize_ticket_merge(merge: TicketMerge) -> dict:
    return {
        "id": merge.id,
        "merged_ticket_number": merge.merged_ticket.number if merge.merged_ticket else None,
        "reason": merge.reason,
        "merged_by": merge.merged_by.full_name if merge.merged_by else None,
        "merged_at": merge.merged_at.isoformat() if merge.merged_at else None,
    }


def list_ticket_merges_payload(db: Session, ticket_id: str) -> list[dict]:
    merges = list_ticket_merges(db, ticket_id)
    return [serialize_ticket_merge(merge) for merge in merges]


def merge_ticket_command(
    db: Session,
    ticket_id: str,
    merged_ticket_id: str,
    reason: str,
    current_user_id: str,
) -> dict:
    primary, dup, merge_log = merge_ticket_record(db, ticket_id, merged_ticket_id, reason, current_user_id)
    db.add(merge_log)
    log_history(db, primary.id, "merged_ticket", None, dup.number, current_user_id)
    return {"ok": True, "primary": primary.number, "merged": dup.number}


def split_ticket_command(
    db: Session,
    ticket_id: str,
    payload,
    current_user_id: str,
) -> dict:
    parent, child = split_ticket_record(
        db=db,
        ticket_id=ticket_id,
        payload=payload,
        next_ticket_number_for_type=lambda t: next_ticket_number(t, db),
        created_by_user_id=current_user_id,
    )
    log_history(db, parent.id, "split_ticket", None, child.number, current_user_id)
    log_history(db, child.id, "created_from_split", None, parent.number, current_user_id)
    return {"parent": parent, "child": child}
