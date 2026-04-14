import json
from datetime import datetime, timezone, time as dt_time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import RoutingRule, Ticket


def _norm_enum(value):
    return value.value if hasattr(value, "value") else value


def list_routing_rules(db: Session):
    return db.query(RoutingRule).order_by(RoutingRule.priority).all()


def serialize_routing_rule(rule: RoutingRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "is_active": rule.is_active,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "actions": rule.actions,
    }


def build_routing_rule(payload: dict) -> RoutingRule:
    if not payload.get("name"):
        raise HTTPException(422, "name es obligatorio")
    return RoutingRule(
        name=payload["name"],
        is_active=payload.get("is_active", True),
        priority=payload.get("priority", 100),
        conditions=json.dumps(payload.get("conditions", {})),
        actions=json.dumps(payload.get("actions", {})),
    )


def get_routing_rule_or_404(db: Session, rule_id: str) -> RoutingRule:
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    return rule


def apply_routing_rule_update(rule: RoutingRule, payload: dict) -> None:
    for key in ("name", "is_active", "priority"):
        if key in payload:
            setattr(rule, key, payload[key])
    if "conditions" in payload:
        rule.conditions = json.dumps(payload["conditions"])
    if "actions" in payload:
        rule.actions = json.dumps(payload["actions"])


def apply_routing_rules(ticket: Ticket, db: Session) -> bool:
    """Apply active routing rules and return True when one rule matched."""
    rules = db.query(RoutingRule).filter(
        RoutingRule.is_active == True
    ).order_by(RoutingRule.priority).all()

    for rule in rules:
        conditions = json.loads(rule.conditions or "{}")
        match = True

        ticket_type = _norm_enum(ticket.ticket_type)
        ticket_priority = _norm_enum(ticket.priority)

        if "ticket_type" in conditions:
            if ticket_type != conditions["ticket_type"]:
                match = False
        if "priority" in conditions:
            prios = conditions["priority"] if isinstance(conditions["priority"], list) else [conditions["priority"]]
            if ticket_priority not in prios:
                match = False
        if "category_id" in conditions and ticket.service_item:
            if ticket.service_item.category_id != conditions["category_id"]:
                match = False
        if "requester_domain" in conditions:
            domain_cond = conditions["requester_domain"]
            allowed = domain_cond if isinstance(domain_cond, list) else [domain_cond]
            requester_email = ticket.requester_email or (ticket.requester_user.email if ticket.requester_user else None)
            domain = (requester_email.split("@", 1)[1].lower() if requester_email and "@" in requester_email else "")
            allowed_norm = [str(d).lower().strip() for d in allowed]
            if domain not in allowed_norm:
                match = False
        if "keyword_in_title" in conditions:
            kws = conditions["keyword_in_title"]
            kws = kws if isinstance(kws, list) else [kws]
            title_l = (ticket.title or "").lower()
            if not any(str(k).lower().strip() in title_l for k in kws if str(k).strip()):
                match = False
        if "time_of_day" in conditions:
            tod = conditions["time_of_day"]
            t_created = (ticket.created_at or datetime.now(timezone.utc)).time()
            if isinstance(tod, str) and "-" in tod:
                start_s, end_s = [p.strip() for p in tod.split("-", 1)]
                start_t = dt_time.fromisoformat(start_s)
                end_t = dt_time.fromisoformat(end_s)
                if not (start_t <= t_created <= end_t):
                    match = False
            elif isinstance(tod, dict):
                start_s = tod.get("start")
                end_s = tod.get("end")
                if start_s and end_s:
                    start_t = dt_time.fromisoformat(start_s)
                    end_t = dt_time.fromisoformat(end_s)
                    if not (start_t <= t_created <= end_t):
                        match = False
        if "day_of_week" in conditions:
            dow = conditions["day_of_week"]
            allowed = dow if isinstance(dow, list) else [dow]
            weekday = (ticket.created_at or datetime.now(timezone.utc)).weekday()  # Monday=0
            day_labels = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            allowed_idx = []
            for day in allowed:
                if isinstance(day, int):
                    allowed_idx.append(day)
                else:
                    day_l = str(day).lower().strip()
                    if day_l.isdigit():
                        allowed_idx.append(int(day_l))
                    elif day_l in day_labels:
                        allowed_idx.append(day_labels[day_l])
            if weekday not in allowed_idx:
                match = False
        if "client_org_id" in conditions:
            client_cond = conditions["client_org_id"]
            allowed = client_cond if isinstance(client_cond, list) else [client_cond]
            ticket_client_id = ticket.client_id or (ticket.requester_client.client_org_id if ticket.requester_client else None)
            if ticket_client_id not in allowed:
                match = False
        if "sla_policy_id" in conditions:
            sla_cond = conditions["sla_policy_id"]
            allowed = sla_cond if isinstance(sla_cond, list) else [sla_cond]
            if ticket.sla_policy_id not in allowed:
                match = False
        if "tag_contains" in conditions:
            tags = conditions["tag_contains"]
            tags = tags if isinstance(tags, list) else [tags]
            tag_text = (ticket.tags or "").lower()
            if not any(str(tag).lower().strip() in tag_text for tag in tags if str(tag).strip()):
                match = False

        if match:
            actions = json.loads(rule.actions or "{}")
            if "assign_group" in actions:
                ticket.assigned_group_id = actions["assign_group"]
            if "assign_user" in actions:
                ticket.assigned_to_user_id = actions["assign_user"]
            if "set_priority" in actions:
                ticket.priority = actions["set_priority"]
            if "set_support_level" in actions:
                ticket.support_level = actions["set_support_level"]
            return True

    return False
