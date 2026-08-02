"""Las columnas organization_id por las que se FILTRA tienen que rellenarse al crear.

Auditoría 2026-08 §7. El audit #7 añadió `organization_id` a 379 modelos, pero en
varios casos nadie la rellenaba mientras el código sí filtraba por ella. Eso produce
dos fallos distintos, y ambos son silenciosos:

- **Fuga:** `_scope_alert_to_org` considera visibles para TODAS las organizaciones las
  alertas con `organization_id`, `user_id` y `project_id` a NULL (fallback para datos
  previos a la migración 076). Había sitios creando alertas nuevas así.
- **Función muda:** `RoutingFeedback` y `SlackConfig` se consultan filtrando por
  `organization_id`; si nunca se rellena, la consulta no devuelve nada y la feature
  deja de funcionar sin error.

Estos tests fijan que la columna se persiste en los tres casos.
"""

from tests.conftest import auth


def _org_id(db):
    from app.models.mfa import Organization

    org = db.query(Organization).first()
    assert org is not None, "el seed de tests debe tener al menos una organización"
    return org.id


# ── Alert ─────────────────────────────────────────────────────────────────────

def test_alert_created_with_user_scope_gets_organization_id(db):
    """Una alerta con user_id debe heredar la organización del usuario."""
    from app.models.user import User
    from app.models.alert import Alert, AlertSeverity, AlertType
    from app.services.alert_service import AlertEngine

    org = _org_id(db)
    user = db.query(User).filter(User.id == "dev-test-id").first()
    user.organization_id = org
    db.commit()

    engine = AlertEngine(db)
    engine._create_alert(
        AlertType.no_imputation, AlertSeverity.info, "Alerta de prueba",
        user_id=user.id,
    )
    db.commit()

    alert = db.query(Alert).filter(Alert.title == "Alerta de prueba").first()
    assert alert is not None
    assert alert.organization_id == org, (
        "La alerta no persiste organization_id: con user_id/project_id también a NULL "
        "caería en el fallback 'visible para todas las organizaciones'."
    )


def test_alert_created_with_project_scope_gets_organization_id(db):
    """Una alerta con project_id debe heredar la organización del proyecto."""
    from app.models.alert import Alert, AlertSeverity, AlertType
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.services.alert_service import AlertEngine

    org = _org_id(db)
    proj = Project(
        id="alert-org-proj",
        organization_id=org,
        code="ALORG",
        name="Proyecto para alerta",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        created_by="admin-test-id",
    )
    db.add(proj)
    db.commit()

    AlertEngine(db)._create_alert(
        AlertType.budget_exceeded, AlertSeverity.warning, "Alerta de proyecto",
        project_id=proj.id,
    )
    db.commit()

    alert = db.query(Alert).filter(Alert.title == "Alerta de proyecto").first()
    assert alert is not None
    assert alert.organization_id == org


# ── SlackConfig ───────────────────────────────────────────────────────────────

def test_slack_config_persists_organization_and_does_not_overwrite_other_org(client, admin_token, db):
    """Configurar Slack en una organización no debe pisar la de otra."""
    from app.models.mfa import SlackConfig
    from app.models.user import User

    org = _org_id(db)
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    admin.organization_id = org
    db.commit()

    # Config preexistente de OTRA organización, misma plataforma
    other = SlackConfig(
        platform="slack",
        organization_id="otra-org-distinta",
        webhook_url="https://hooks.slack.test/OTRA-ORG",
        default_channel="#otra",
    )
    db.add(other)
    db.commit()
    other_id = other.id

    res = client.post(
        "/api/v1/slack/config",
        json={
            "platform": "slack",
            "workspace_name": "Mi Workspace",
            "webhook_url": "https://hooks.slack.test/MI-ORG",
            "default_channel": "#mio",
        },
        headers=auth(admin_token),
    )
    assert res.status_code in (200, 201), res.text

    # La config ajena sigue intacta
    db.expire_all()
    untouched = db.query(SlackConfig).filter(SlackConfig.id == other_id).first()
    assert untouched is not None
    assert untouched.webhook_url == "https://hooks.slack.test/OTRA-ORG", (
        "Se ha sobrescrito la configuración de Slack de otra organización"
    )

    # Y la nueva lleva su organización
    mine = db.query(SlackConfig).filter(SlackConfig.organization_id == org).first()
    assert mine is not None, "la config creada no persiste organization_id"
    assert mine.webhook_url == "https://hooks.slack.test/MI-ORG"


# ── RoutingFeedback ───────────────────────────────────────────────────────────

def test_routing_feedback_persists_organization_id(db):
    """El feedback de routing debe heredar la organización del ticket.

    Las métricas por agente filtran por RoutingFeedback.organization_id; sin
    rellenarla, no encuentran ninguna fila y quedan vacías sin dar error.
    """
    from app.models.service_desk import RoutingFeedback, Ticket, TicketStatus, TicketType
    from app.services.service_desk.ml_routing_service import record_routing_event

    org = _org_id(db)
    ticket = Ticket(
        organization_id=org,
        number="TCK-ORG-1",
        title="Ticket con organización",
        description="Para comprobar el feedback de routing",
        ticket_type=TicketType.incident,
        status=TicketStatus.resolved,
        assigned_to_user_id="admin-test-id",
    )
    db.add(ticket)
    db.commit()

    record_routing_event(db, ticket)
    db.commit()

    row = db.query(RoutingFeedback).filter(RoutingFeedback.ticket_id == ticket.id).first()
    assert row is not None, "no se ha registrado el feedback de routing"
    assert row.organization_id == org, (
        "RoutingFeedback no persiste organization_id, así que el filtro por "
        "organización de las métricas por agente nunca encuentra filas."
    )
