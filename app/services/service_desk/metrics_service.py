from datetime import datetime, timezone as tz


def priority_matrix(urgency: str, impact: str) -> str:
    """Calculate ITIL priority from urgency x impact."""
    matrix = {
        ("critical", "enterprise"): "p1_critical",
        ("critical", "department"): "p1_critical",
        ("critical", "user"): "p2_high",
        ("high", "enterprise"): "p1_critical",
        ("high", "department"): "p2_high",
        ("high", "user"): "p2_high",
        ("medium", "enterprise"): "p2_high",
        ("medium", "department"): "p3_medium",
        ("medium", "user"): "p3_medium",
        ("low", "enterprise"): "p3_medium",
        ("low", "department"): "p4_low",
        ("low", "user"): "p4_low",
    }
    return matrix.get((urgency, impact), "p3_medium")


def priority_matrix_payload(payload: dict) -> dict:
    urgency = payload.get("urgency", "medium")
    impact = payload.get("impact", "user")
    priority = priority_matrix(urgency, impact)
    return {
        "urgency": urgency,
        "impact": impact,
        "recommended_priority": priority,
    }


def compute_itil_metrics(tickets, now=None) -> dict:
    """Compute MTTR and FCR metrics for a ticket set."""
    if now is None:
        now = datetime.now(tz.utc)

    def _safe_dt(value):
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=tz.utc)

    resolved = [t for t in tickets if t.resolved_at and t.created_at]
    mttr_minutes = 0
    if resolved:
        total = sum((_safe_dt(t.resolved_at) - _safe_dt(t.created_at)).total_seconds() / 60 for t in resolved)
        mttr_minutes = round(total / len(resolved), 1)

    fcr_count = sum(
        1
        for t in resolved
        if len([c for c in (t.comments or []) if not getattr(c, "is_client", False)]) <= 2
    )
    fcr_pct = round(fcr_count / len(resolved) * 100, 1) if resolved else 0

    return {
        "mttr_minutes": mttr_minutes,
        "mttr_hours": round(mttr_minutes / 60, 1),
        "fcr_percent": fcr_pct,
        "total_resolved": len(resolved),
    }
