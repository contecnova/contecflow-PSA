from fastapi import BackgroundTasks
from app.db.session import SessionLocal
from app.models.semantic_engine import SemAssignment
from app.services.semantic_classifier import SemanticAssigner


def enqueue_profile_refresh(background_tasks: BackgroundTasks, user_id: str) -> None:

    def _run():
        db = SessionLocal()
        try:
            SemanticAssigner(db).refresh_user_profile(user_id)
        except Exception:
            pass
        finally:
            db.close()

    background_tasks.add_task(_run)


def enqueue_reassign_feedback(background_tasks: BackgroundTasks, item_id: str, item_type: str) -> None:

    def _run():
        db = SessionLocal()
        try:
            assignment = (
                db.query(SemAssignment)
                .filter(
                    SemAssignment.item_id == item_id,
                    SemAssignment.item_type == item_type,
                )
                .order_by(SemAssignment.created_at.desc())
                .first()
            )
            if assignment and assignment.was_accepted is None:
                assignment.was_accepted = False
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(_run)


def enqueue_routing_outcome(background_tasks: BackgroundTasks, ticket_id: str) -> None:
    """Record ML routing outcome (resolution time + CSAT) when a ticket is resolved/closed."""

    def _run():
        from app.models.service_desk import Ticket
        from app.services.service_desk.ml_routing_service import record_routing_outcome

        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if ticket:
                record_routing_outcome(db, ticket)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(_run)
