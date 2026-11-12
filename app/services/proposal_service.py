"""
proposal_service.py — SOW / Proposal generation and tracking.

Flow:
  1. PM selects a ProposalTemplate (or uses ad-hoc content)
  2. render_proposal() substitutes {{vars}} with opportunity data
  3. generate_proposal() persists rendered content to opp.proposal_content
  4. mark_proposal_sent() stamps proposal_sent_at
  5. On convert, pipeline_service creates project + RevenueContract
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.pipeline import Opportunity, ProposalTemplate
from app.core import timeutil
from app.core.errores import ErrorDeDominio

# ── Template variable map ──────────────────────────────────────────────────────

CONTRACT_TYPE_LABELS = {
    "fixed_price":   "Precio fijo",
    "time_material": "Tiempo y materiales",
    "retainer":      "Retainer mensual",
    "hourly_bag":    "Bolsa de horas",
}

# ASC 606 method mapping for RevenueContract creation on convert
CONTRACT_TYPE_TO_ASC_METHOD = {
    "fixed_price":   "milestone",
    "time_material": "over_time",
    "retainer":      "straight_line",
    "hourly_bag":    "consumption",
}

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")

DEFAULT_TEMPLATE_CONTENT = """\
# Propuesta de servicios — {{opportunity_name}}

**Cliente:** {{client_name}}
**Responsable:** {{owner_name}}
**Fecha:** {{today}}

---

## Alcance

{{description}}

## Condiciones económicas

| Concepto | Detalle |
|---|---|
| Valor estimado | {{expected_revenue}} |
| Horas estimadas | {{expected_hours}} |
| Inicio previsto | {{start_date}} |
| Duración | {{duration_weeks}} semanas |

## Términos y condiciones

El presente documento constituye una propuesta comercial no vinculante.
Las condiciones definitivas se recogerán en el contrato de prestación de servicios.

---

*Generado por ContecFlow PSA*
"""


def _build_vars(opp: Opportunity) -> dict:
    """Build the variable substitution map from an Opportunity."""
    from sqlalchemy.orm import object_session
    from app.services.formato_regional import formatear_importe, simbolo_de_moneda
    simbolo = simbolo_de_moneda(object_session(opp), getattr(opp, "organization_id", None),
                                moneda=getattr(opp, "currency", None))

    def fmt_currency(v):
        return formatear_importe(v, simbolo)

    return {
        "client_name":       opp.client_name or "—",
        "opportunity_name":  opp.name or "—",
        "expected_revenue":  fmt_currency(opp.expected_revenue),
        "expected_hours":    f"{opp.expected_hours:,.0f} h" if opp.expected_hours else "—",
        "start_date":        str(opp.expected_start_date) if opp.expected_start_date else "—",
        "duration_weeks":    str(opp.expected_duration_weeks) if opp.expected_duration_weeks else "—",
        "owner_name":        opp.owner.full_name if opp.owner else "—",
        "description":       opp.description or "",
        "today":             str(timeutil.today()),
        "contract_type":     CONTRACT_TYPE_LABELS.get(opp.contract_type or "", "—"),
        "hourly_rate":       f"{opp.hourly_rate} {simbolo}/h" if opp.hourly_rate else "—",
    }


def render_proposal(template_content: str, opp: Opportunity, extra_vars: Optional[dict] = None) -> str:
    """
    Substitute {{variable}} placeholders in template_content.
    Unknown variables are left as-is.
    """
    vars_map = _build_vars(opp)
    if extra_vars:
        vars_map.update(extra_vars)

    def replacer(match):
        key = match.group(1)
        return str(vars_map.get(key, match.group(0)))

    return _VAR_RE.sub(replacer, template_content)


# ── Template CRUD ──────────────────────────────────────────────────────────────

def list_templates(db: Session) -> list:
    return (
        db.query(ProposalTemplate)
        .filter(ProposalTemplate.is_active == True)
        .order_by(ProposalTemplate.created_at.desc())
        .all()
    )


def get_template(db: Session, template_id: str) -> ProposalTemplate:
    t = db.query(ProposalTemplate).filter(ProposalTemplate.id == template_id).first()
    if not t:
        raise ErrorDeDominio(404, "Plantilla no encontrada")
    return t


def create_template(db: Session, organization_id: str, user_id: str, data: dict) -> ProposalTemplate:
    if not data.get("name"):
        raise ErrorDeDominio(422, "El campo 'name' es obligatorio para crear una plantilla de propuesta")
    if not organization_id:
        raise ErrorDeDominio(422, "El usuario no tiene organización asignada")
    t = ProposalTemplate(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        created_by=user_id,
        **{k: v for k, v in data.items() if k in {"name", "description", "contract_type", "content"}},
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_template(db: Session, template_id: str, data: dict) -> ProposalTemplate:
    t = get_template(db, template_id)
    allowed = {"name", "description", "contract_type", "content", "is_active"}
    for k, v in data.items():
        if k in allowed:
            setattr(t, k, v)
    db.commit()
    return t


def delete_template(db: Session, template_id: str) -> None:
    t = get_template(db, template_id)
    t.is_active = False
    db.commit()


# ── Proposal generation ────────────────────────────────────────────────────────

def generate_proposal(
    db: Session,
    opp_id: str,
    template_id: Optional[str],
    user_id: str,
    extra_vars: Optional[dict] = None,
) -> Opportunity:
    """
    Render the proposal for an opportunity and persist it.
    If template_id is None, uses DEFAULT_TEMPLATE_CONTENT.
    """
    opp = db.query(Opportunity).filter(Opportunity.id == opp_id, Opportunity.is_active == True).first()
    if not opp:
        raise ErrorDeDominio(404, "Oportunidad no encontrada")

    if template_id:
        tmpl = get_template(db, template_id)
        content = tmpl.content or DEFAULT_TEMPLATE_CONTENT
        opp.proposal_template_id = template_id
    else:
        content = DEFAULT_TEMPLATE_CONTENT

    # Make sure the relationship is loaded for variable substitution
    if opp.owner_id and opp.owner is None:
        from app.models.user import User
        opp.owner = db.query(User).filter(User.id == opp.owner_id).first()

    opp.proposal_content      = render_proposal(content, opp, extra_vars)
    opp.proposal_generated_at = datetime.now(timezone.utc)
    opp.proposal_sent_at      = None   # reset if regenerated
    db.commit()
    return opp


def mark_proposal_sent(db: Session, opp_id: str) -> Opportunity:
    opp = db.query(Opportunity).filter(Opportunity.id == opp_id, Opportunity.is_active == True).first()
    if not opp:
        raise ErrorDeDominio(404, "Oportunidad no encontrada")
    if not opp.proposal_content:
        raise ErrorDeDominio(400, "Genera la propuesta antes de marcarla como enviada")
    opp.proposal_sent_at = datetime.now(timezone.utc)
    db.commit()
    return opp


# ── Serializers ────────────────────────────────────────────────────────────────

def serialize_template(t: ProposalTemplate) -> dict:
    return {
        "id":            t.id,
        "name":          t.name,
        "description":   t.description,
        "contract_type": t.contract_type,
        "content":       t.content,
        "is_active":     t.is_active,
        "created_at":    str(t.created_at)[:19] if t.created_at else None,
    }


def get_opportunity_by_id(db: Session, opp_id: str) -> Opportunity:
    """Fetch an Opportunity by id, raising 404 if not found."""
    opp = db.query(Opportunity).filter(Opportunity.id == opp_id, Opportunity.is_active == True).first()
    if not opp:
        raise ErrorDeDominio(404, "Oportunidad no encontrada")
    return opp
