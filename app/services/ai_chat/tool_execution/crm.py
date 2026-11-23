"""Herramientas de CRM/pipeline y clientes."""
from __future__ import annotations

from sqlalchemy import or_

from app.services.ai_chat.tool_execution.textos import mensaje as _msg

from app.models.clients import Client
from app.models.pipeline import ETAPAS_ABIERTAS, ETAPAS_CERRADAS, Opportunity, etapa_de
from app.models.project import Project
from app.services.ai_chat.tool_execution.politica import proyectos_visibles


def _get_pipeline(tool_input, db, user, now, is_financial_role):
    # Segunda auditoría 2026-11: las guardas y el alcance de `GET /pipeline/...`.
    from app.services import politica_de_visibilidad as _vis
    from app.services.pipeline_service import scope_opportunity_query
    from app.services.cab_service.busqueda import MODULO_DE_OPORTUNIDADES
    if not _vis.ve_modulo_financiero(db, user, MODULO_DE_OPORTUNIDADES):
        return {"error": _msg(db, user, "pipeline_denegado")}
    q = scope_opportunity_query(db.query(Opportunity), db, user)
    stage = tool_input.get("stage", "")
    if stage and stage != "all":
        q = q.filter(Opportunity.stage == stage)
    else:
        q = q.filter(Opportunity.stage.notin_(ETAPAS_CERRADAS))
    opps = q.order_by(Opportunity.expected_close_date.asc().nullslast()).limit(tool_input.get("limit", 20)).all()
    # Auditoria 04b M9: el ponderado es solo de abiertas (perdidas/canceladas no suman).
    weighted_total = sum((o.expected_revenue or 0) * (o.probability or 0) / 100
                         for o in opps if etapa_de(o.stage) in ETAPAS_ABIERTAS)
    return {
        "total_opportunities": len(opps),
        "weighted_pipeline": round(weighted_total, 2),
        "opportunities": [{
            "id": o.id, "code": o.code, "name": o.name,
            "client": o.client_name, "stage": str(o.stage),
            "probability": o.probability,
            "expected_revenue": o.expected_revenue,
            "weighted_value": round((o.expected_revenue or 0) * (o.probability or 0) / 100, 2),
            "expected_close_date": str(o.expected_close_date) if o.expected_close_date else None,
        } for o in opps]
    }


def _get_clients(tool_input, db, user, now, is_financial_role):
    # M109 (auditoría 22-11-2026): el mismo alcance y el mismo recorte que
    # `GET /clients` (antes, con política sin capacidad, el asistente daba el
    # correo y el teléfono de todos los clientes y de sus contactos a cualquiera).
    from app.services.client_service import scoped_client_query
    from app.services.politica_de_visibilidad import ve_datos_de_contacto_de_clientes
    from app.services.service_desk.ticket_query_service import escapar_like
    ve_contacto = ve_datos_de_contacto_de_clientes(user)
    q = scoped_client_query(db, user)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Client.status == status)
    if tool_input.get("query"):
        term = f"%{escapar_like(str(tool_input['query']))}%"
        q = q.filter(or_(Client.name.ilike(term, escape="\\")))
    clients = q.order_by(Client.name).limit(tool_input.get("limit", 20)).all()
    result = []
    for c in clients:
        projects = db.query(Project).filter(Project.client_id == c.id,
                                            Project.id.in_(proyectos_visibles(db, user))).all()
        total_revenue = sum(p.contract_amount or 0 for p in projects)
        result.append({
            "id": c.id, "name": c.name,
            "industry": str(c.industry) if c.industry else None,
            "status": str(c.status) if c.status else None,
            "projects_count": len(projects),
            "total_contract_value": round(total_revenue, 2),
            # Empresa (centralita / email general) y su contacto principal (persona), por separado.
            "email": c.email, "phone": c.phone,
            "primary_contact": ({"name": c.contact_name, "email": c.contact_email if ve_contacto else None,
                                 "phone": c.contact_phone if ve_contacto else None, "role": c.contact_role}
                                if c.contact_name or c.contact_email else None),
        })
    return {"clients": result}


HANDLERS = {
    "get_pipeline": _get_pipeline,
    "get_clients": _get_clients,
}
