"""Paginas de wiki visibles en el portal y encuestas de satisfaccion.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.client_portal import ClientSurvey
from app.models.epics import WikiPage, WikiSpace
from sqlalchemy import and_, false, or_

from app.services.client_portal_service.serializacion import survey_out


# ── Wiki ──────────────────────────────────────────────────────────────────────

def _portal_visible_wiki_filter(current_client):
    """Condición de tenencia para el wiki visible desde el portal.

    `visibility == "portal"` solo dice que la página es apta para clientes; NO dice
    de QUÉ cliente. Sin acotar además por tenencia, cualquier cliente del portal
    podía listar y leer el wiki de portal de todas las organizaciones
    (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §1).

    Un espacio wiki es o de proyecto o de organización (ver WikiSpace), así que se
    admiten los dos casos y se deniega por defecto todo lo demás.
    """
    accessible = current_client.get_project_ids()
    org_id = getattr(current_client, "organization_id", None)

    clauses = []
    if accessible:
        clauses.append(WikiSpace.project_id.in_(accessible))
    if org_id:
        # Espacio organizacional (sin proyecto) de la propia organización del cliente.
        clauses.append(and_(WikiSpace.project_id.is_(None), WikiSpace.organization_id == org_id))

    if not clauses:
        # Cliente sin proyectos ni organización: no ve nada.
        return false()
    return or_(*clauses)


def portal_wiki_pages(current_client, db: Session) -> list:

    pages = (
        db.query(WikiPage)
        .join(WikiSpace, WikiSpace.id == WikiPage.space_id)
        .filter(
            WikiPage.visibility == "portal",
            WikiPage.is_published == True,
            _portal_visible_wiki_filter(current_client),
        )
        .order_by(WikiPage.title)
        .all()
    )
    return [{"id": p.id, "title": p.title, "slug": p.slug, "space_id": p.space_id,
             "updated_at": str(p.updated_at)} for p in pages]


def portal_wiki_page_detail(page_id: str, current_client, db: Session) -> dict:

    page = (
        db.query(WikiPage)
        .join(WikiSpace, WikiSpace.id == WikiPage.space_id)
        .filter(
            WikiPage.id == page_id,
            WikiPage.visibility == "portal",
            _portal_visible_wiki_filter(current_client),
        )
        .first()
    )
    if not page:
        raise ValueError("Página no encontrada o no visible")
    return {"id": page.id, "title": page.title, "content": page.content,
            "updated_at": str(page.updated_at), "space_id": page.space_id}


# ── Surveys ───────────────────────────────────────────────────────────────────

def get_surveys(current_client, db: Session) -> list:

    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.client_id == current_client.id
    ).order_by(ClientSurvey.sent_at.desc()).all()
    return [survey_out(s) for s in surveys]


def create_survey(project_id: str, client_id: str, title: str, db: Session) -> dict:

    survey = ClientSurvey(project_id=project_id, client_id=client_id, title=title)
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return survey_out(survey)


def respond_survey(survey_id: str, payload, current_client, db: Session) -> dict:

    survey = db.query(ClientSurvey).filter(
        ClientSurvey.id == survey_id, ClientSurvey.client_id == current_client.id
    ).first()
    if not survey:
        raise ValueError("Encuesta no encontrada")
    if survey.status != "pending":
        raise ValueError("Esta encuesta ya ha sido respondida")
    for k, v in payload.model_dump().items():
        setattr(survey, k, v)
    survey.status = "completed"
    survey.completed_at = datetime.now(timezone.utc)
    db.commit()
    return survey_out(survey)
