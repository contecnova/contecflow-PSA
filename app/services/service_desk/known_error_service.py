from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Problem


def get_known_errors(db: Session):
    return (
        db.query(Problem)
        .options(joinedload(Problem.ci), joinedload(Problem.related_tickets))
        .filter(Problem.status == "known_error", Problem.workaround.isnot(None))
        .all()
    )


def serialize_known_error(problem: Problem) -> dict:
    return {
        "id": problem.id,
        "number": problem.number,
        "title": problem.title,
        "workaround": problem.workaround,
        "root_cause": problem.root_cause,
        "ci": problem.ci.name if problem.ci else None,
        "affected_tickets": len(problem.related_tickets),
    }
