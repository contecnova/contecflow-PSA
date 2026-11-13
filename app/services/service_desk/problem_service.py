import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.service_desk import Problem, Ticket
from app.models.user import User
from app.schemas.service_desk import ProblemIn, ProblemUpdateIn
from app.services.service_desk.scoping import (
    scope_problem_query as _scope_problem_query,
    scope_ticket_query as _scope_ticket_query,
)
from app.services.sla_service import next_problem_number as _next_problem_number
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def cerrar_problema(db, current_user, problem_id: str) -> dict:
    """Cierra un problema. Es lo que hace el boton de borrar de la interfaz.

    Auditoria 2026-08 (hallazgo 37). `DELETE /sd/problems/{id}` **no existia**,
    asi que el boton de borrar de `ITSMKnowledgeTab` **no hacia nada** — uno de
    los dos borrados silenciosos que la auditoria dejo anotados.

    **No borra la fila**, y eso es la decision de fondo: un problema es el
    registro de una investigacion, con su analisis de causa raiz, sus incidentes
    vinculados y su posible entrada en la base de errores conocidos. Borrarlo
    dejaria huerfano todo eso. `ProblemStatus` no tiene `cancelled`, asi que el
    estado terminal es `closed`, que es el que ya usa el resto del modulo.

    Idempotente: cerrar uno ya cerrado no es un error.
    """
    from app.models.service_desk import ProblemStatus

    problema = get_scoped_problem_or_404(db, current_user, problem_id)
    ya_estaba = problema.status == ProblemStatus.closed
    if not ya_estaba:
        problema.status = ProblemStatus.closed
        from datetime import datetime, timezone

        problema.resolved_at = (
            problema.resolved_at or datetime.now(timezone.utc))
    return {
        "ok": True,
        "id": problema.id,
        "status": ProblemStatus.closed.value,
        "already_closed": ya_estaba,
    }


def list_problems_payload(db: Session, current_user: User, page: int, page_size: int) -> list[dict]:
    q = db.query(Problem).options(
        joinedload(Problem.ci),
        joinedload(Problem.owner),
        joinedload(Problem.related_tickets),
    )
    q = _scope_problem_query(q, db, current_user)
    problems = (
        q.order_by(Problem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {
            "id": p.id,
            "number": p.number,
            "title": p.title,
            "description": p.description,
            "status": p.status,
            "priority": p.priority,
            "root_cause": p.root_cause,
            "workaround": p.workaround,
            "ci_name": p.ci.name if p.ci else None,
            "owner_name": p.owner.full_name if p.owner else None,
            "related_ticket_count": len(p.related_tickets),
            "created_at": str(p.created_at)[:10],
            "resolved_at": str(p.resolved_at)[:10] if p.resolved_at else None,
        }
        for p in problems
    ]


def _validate_problem_org_constraints(db: Session, current_user: User, project_id: str = None, owner_user_id: str = None, *, update: bool = False) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if project_id:
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not project:
            if update:
                raise ErrorDeDominio(403, "No puedes mover problemas fuera de tu organización")
            raise ErrorDeDominio(403, "No puedes crear problemas para proyectos fuera de tu organización")

    if owner_user_id:
        owner = db.query(User).filter(User.id == owner_user_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise ErrorDeDominio(403, "No puedes asignar un owner fuera de tu organización")


def create_problem_record(db: Session, current_user: User, payload: ProblemIn) -> Problem:
    _validate_problem_org_constraints(
        db,
        current_user,
        project_id=payload.project_id,
        owner_user_id=payload.owner_user_id,
        update=False,
    )
    problem = Problem(number=_next_problem_number(db), **payload.model_dump())
    db.add(problem)
    return problem


def get_scoped_problem_or_404(db: Session, current_user: User, problem_id: str) -> Problem:
    problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == problem_id).first()
    if not problem:
        raise ErrorDeDominio(404)
    return problem


def apply_problem_update(db: Session, current_user: User, problem: Problem, payload: ProblemUpdateIn) -> None:
    _validate_problem_org_constraints(
        db,
        current_user,
        project_id=payload.project_id,
        owner_user_id=payload.owner_user_id,
        update=True,
    )
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(problem, k, v)
    if payload.status in ["resolved", "closed"]:
        problem.resolved_at = datetime.now(timezone.utc)


def link_ticket_to_problem_record(db: Session, current_user: User, problem_id: str, ticket_id: str) -> None:
    problem = get_scoped_problem_or_404(db, current_user, problem_id)
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404)
    ticket.problem_id = problem.id


# ── RCA with AI ───────────────────────────────────────────────────────────────

def suggest_rca_from_ai(db: Session, problem: Problem) -> dict:
    """Call the configured AI provider to suggest a root cause for *problem*.

    Gathers the descriptions of all linked tickets and asks the AI to identify
    the most likely root cause, type, and a suggested workaround.

    Returns:
        {
          "root_cause": str,
          "rca_type": str,          # hardware | software | process | human | network | unknown
          "workaround": str,
          "confidence": int,         # 0-100
          "provider_used": str,
        }

    Saves suggestions to problem.rca_ai_suggestion (JSON) and
    problem.rca_type if not already set. Does NOT commit.
    """
    import json as _json
    from app.services.ai_provider_service import call_ai

    linked_tickets = (
        db.query(Ticket)
        .filter(Ticket.problem_id == problem.id)
        .all()
    )
    ticket_summaries = "\n".join(
        f"- [{t.number}] {t.title}: {(t.description or '')[:300]}"
        for t in linked_tickets
    ) or "(no linked tickets)"

    prompt = (
        "You are an ITIL-certified problem manager performing Root Cause Analysis.\n\n"
        f"Problem title: {problem.title}\n"
        f"Problem description: {problem.description}\n\n"
        f"Linked incidents ({len(linked_tickets)}):\n{ticket_summaries}\n\n"
        "Identify the most likely root cause. Respond ONLY with valid JSON:\n"
        '{"root_cause": "...", "rca_type": "hardware|software|process|human|network|unknown", '
        '"workaround": "...", "confidence": 0-100}'
    )

    provider_used = "unknown"
    suggestion: dict = {}

    try:
        result = call_ai(
            db=db,
            messages=[{"role": "user", "content": prompt}],
            system="You are an ITIL problem manager. Respond only with valid JSON.",
            max_tokens=512,
            # Segunda auditoria 2026-11 (#33): desde el worker no hay usuario;
            # sin la organizacion no aplicaban su tope de gasto ni su proveedor.
            organization_id=getattr(problem, "organization_id", None),
        )
        provider_used = result.get("provider", "unknown")
        raw = (result.get("content") or "").strip()

        # Extract JSON from response (may be wrapped in markdown)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            suggestion = _json.loads(raw[start:end])
        else:
            suggestion = {"root_cause": raw, "rca_type": "unknown", "confidence": 40, "workaround": ""}
    except Exception as exc:
        logger.warning("suggest_rca_from_ai: AI call failed: %s", exc)
        suggestion = {
            "root_cause": "Unable to determine automatically — manual RCA required.",
            "rca_type": "unknown",
            "confidence": 0,
            "workaround": "",
        }

    suggestion["provider_used"] = provider_used

    # Persist to problem (caller must commit)
    problem.rca_ai_suggestion = _json.dumps(suggestion)
    if not problem.rca_type and suggestion.get("rca_type"):
        problem.rca_type = suggestion["rca_type"]
    if not problem.root_cause and suggestion.get("root_cause"):
        problem.root_cause = suggestion["root_cause"]
    if not problem.workaround and suggestion.get("workaround"):
        problem.workaround = suggestion["workaround"]

    return suggestion


# ── Auto-create problem from correlated tickets ───────────────────────────────

def create_problem_from_correlation(
    db: Session,
    ticket_ids: list[str],
    category: str,
    priority: str,
    auto_rca: bool = True,
) -> Problem:
    """Create a new Problem and link all provided ticket IDs to it.

    Optionally triggers AI-based RCA suggestion immediately.
    Does NOT commit — caller must commit.
    """
    import json as _json
    from app.services.sla_service import next_problem_number

    # Build a descriptive title from the most common words in ticket titles
    tickets = db.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
    if not tickets:
        raise ErrorDeDominio(400, "No tickets found for correlation")

    # Use the first ticket title as a base if we have few tickets
    base_title = tickets[0].title if tickets else "Recurring incidents"
    title = f"[Auto-detected] {category or base_title} — {len(tickets)} linked incidents"

    description = (
        f"Problem auto-detected from {len(tickets)} correlated incidents "
        f"in category '{category}' with priority '{priority}'.\n\n"
        + "\n".join(f"- [{t.number}] {t.title}" for t in tickets)
    )

    # La deteccion corre en el worker, sin organizacion en la sesion: el
    # problema es de la organizacion de sus tickets.
    org_id = tickets[0].organization_id
    problem = Problem(
        organization_id=org_id,
        number=next_problem_number(db, org_id),
        title=title,
        description=description,
        priority=priority,
        status="open",
        auto_detected=True,
        affected_services_json=_json.dumps(
            list({t.ci_id for t in tickets if t.ci_id})
        ),
    )
    db.add(problem)
    db.flush()  # get problem.id before linking

    # Link all tickets
    for ticket in tickets:
        ticket.problem_id = problem.id

    # Optionally trigger AI RCA
    if auto_rca:
        try:
            suggest_rca_from_ai(db, problem)
        except Exception as exc:
            logger.warning("Auto-RCA failed during problem creation: %s", exc)

    logger.info(
        "Auto-created Problem %s from %d correlated tickets (category=%s)",
        problem.number,
        len(tickets),
        category,
    )
    return problem


# ── Problem → Change (RFC) flow ───────────────────────────────────────────────

def create_change_from_problem(
    db: Session,
    current_user: User,
    problem_id: str,
    change_type: str = "normal",
    planned_start: str | None = None,
    planned_end: str | None = None,
    custom_title: str | None = None,
    custom_description: str | None = None,
) -> dict:
    """Create an ITSMChangeRequest linked to a Problem to address its root cause.

    Prefills the RFC from the problem's root_cause, workaround, and linked CIs.
    Does NOT commit — caller must commit.

    Returns a dict with the new change's id, number, and status.
    """
    import json as _json
    from app.services.service_desk.change_service import next_change_number, build_change_request

    problem = get_scoped_problem_or_404(db, current_user, problem_id)

    linked_tickets = db.query(Ticket).filter(Ticket.problem_id == problem.id).all()
    affected_cis: list[str] = []
    try:
        if problem.affected_services_json:
            affected_cis = _json.loads(problem.affected_services_json)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("create_change_from_problem: fallo best-effort ignorado", exc_info=True)

    title = custom_title or f"[RFC] Resolver causa raíz: {problem.title[:200]}"
    description = custom_description or (
        f"RFC generado automáticamente a partir del Problema {problem.number}.\n\n"
        f"**Causa raíz:** {problem.root_cause or 'Pendiente de análisis'}\n\n"
        f"**Workaround actual:** {problem.workaround or 'Ninguno'}\n\n"
        f"**Incidentes relacionados:** {', '.join(t.number for t in linked_tickets) or 'Ninguno'}\n\n"
        f"**Descripción del problema:** {problem.description or ''}"
    )

    # Map problem priority to change risk
    _risk_map = {
        "p1_critical": "critical",
        "p2_high": "high",
        "p3_medium": "medium",
        "p4_low": "low",
    }
    risk = _risk_map.get(str(problem.priority), "medium")

    payload = {
        "title": title,
        "description": description,
        "change_type": change_type,
        "risk": risk,
        "priority": str(problem.priority) if problem.priority else "p3_medium",
        "business_justification": f"Eliminar causa raíz del Problema {problem.number}",
        "impact_description": f"CIs afectados: {', '.join(affected_cis) or 'Por determinar'}",
        "related_problem_id": problem.id,
        "rollback_plan": problem.workaround or "Ver workaround del problema asociado",
    }
    if planned_start:
        payload["planned_start"] = planned_start
    if planned_end:
        payload["planned_end"] = planned_end

    number = next_change_number(db)
    change = build_change_request(payload, requester_id=current_user.id, number=number)
    db.add(change)
    db.flush()

    logger.info(
        "Change %s created from Problem %s by %s",
        change.number,
        problem.number,
        current_user.id,
    )
    return {"id": change.id, "number": change.number, "status": change.status}
