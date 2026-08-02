"""Integration Marketplace service.

Manages the connector catalog and per-organisation integration instances.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.encryption import encrypt_value
from app.models.marketplace import IntegrationConnector
from app.models.marketplace import IntegrationInstance

logger = logging.getLogger(__name__)

CONNECTOR_CATALOG = [
    {"name": "Salesforce CRM", "slug": "salesforce", "category": "crm",
     "description": "Bidirectional sync of opportunities, contacts and accounts.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/salesforce.svg"},
    {"name": "HubSpot CRM", "slug": "hubspot", "category": "crm",
     "description": "Sync deals, contacts and pipeline stages with HubSpot.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/hubspot.svg"},
    {"name": "SAP S/4HANA", "slug": "sap_s4", "category": "erp",
     "description": "Financial integration: cost centres, WBS elements, actual costs.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/sap.svg"},
    {"name": "Oracle NetSuite", "slug": "netsuite", "category": "erp",
     "description": "Sync projects, time entries and invoices with NetSuite.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/netsuite.svg"},
    {"name": "Workday HCM", "slug": "workday", "category": "hris",
     "description": "Employee roster, org chart, and time-off sync.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/workday.svg"},
    {"name": "BambooHR", "slug": "bamboohr", "category": "hris",
     "description": "Sync employees, departments and leave balances.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/bamboohr.svg"},
    {"name": "Greenhouse ATS", "slug": "greenhouse", "category": "hris",
     "description": "Import new hires and open positions for resource planning.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.contecflow.app/connectors/greenhouse.svg"},
    {"name": "Jira Software", "slug": "jira", "category": "devops",
     "description": "Bidirectional issue sync, sprint import and webhook events.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/jira.svg"},
    {"name": "GitHub", "slug": "github", "category": "devops",
     "description": "PR status, commit activity and deployment events.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/github.svg"},
    {"name": "GitLab", "slug": "gitlab", "category": "devops",
     "description": "CI/CD pipelines, merge requests and issue tracking.",
     "auth_scheme": "oauth2", "is_certified": False,
     "logo_url": "https://cdn.contecflow.app/connectors/gitlab.svg"},
    {"name": "Slack", "slug": "slack", "category": "comms",
     "description": "Task creation, time logging and rich Block Kit notifications.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/slack.svg"},
    {"name": "Microsoft Teams", "slug": "teams", "category": "comms",
     "description": "Adaptive card notifications and bot commands.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/teams.svg"},
    {"name": "Xero", "slug": "xero", "category": "finance",
     "description": "Invoice sync, expense reimbursements and payment status.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/xero.svg"},
    {"name": "QuickBooks Online", "slug": "quickbooks", "category": "finance",
     "description": "Sync invoices, payments and project-level P&L.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/quickbooks.svg"},
    {"name": "DocuSign", "slug": "docusign", "category": "legal",
     "description": "Trigger e-signature workflows for contracts and SOWs.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/docusign.svg"},
    {"name": "Stripe", "slug": "stripe", "category": "finance",
     "description": "Payment links, milestone billing and subscription management.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/stripe.svg"},
    {"name": "Azure DevOps", "slug": "azure_devops", "category": "devops",
     "description": "Work items, pipelines and board sync with Azure DevOps.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.contecflow.app/connectors/azuredevops.svg"},
    {"name": "AWS S3", "slug": "aws_s3", "category": "storage",
     "description": "Store project documents and backups in S3 buckets.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/awss3.svg"},
    {"name": "Google Workspace", "slug": "google_workspace", "category": "comms",
     "description": "Calendar sync, Drive documents and Gmail notifications.",
     "auth_scheme": "oauth2", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/google.svg"},
    {"name": "Zendesk", "slug": "zendesk", "category": "service_desk",
     "description": "Ticket sync between Contecflow Service Desk and Zendesk.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.contecflow.app/connectors/zendesk.svg"},
    {"name": "ServiceNow", "slug": "servicenow", "category": "service_desk",
     "description": "ITSM integration: incidents, changes and CMDB items.",
     "auth_scheme": "api_key", "is_certified": False,
     "logo_url": "https://cdn.contecflow.app/connectors/servicenow.svg"},
    {"name": "Okta", "slug": "okta", "category": "iam",
     "description": "SSO, SCIM user provisioning and group sync.",
     "auth_scheme": "api_key", "is_certified": True,
     "logo_url": "https://cdn.contecflow.app/connectors/okta.svg"},
]


def _seed_connectors(db: Session) -> None:
    if db.query(IntegrationConnector).count() == 0:
        for item in CONNECTOR_CATALOG:
            db.add(IntegrationConnector(**item))
        db.commit()


def list_marketplace_connectors(
    category: Optional[str],
    certified_only: bool,
    organization_id: Optional[str],
    db: Session,
) -> list:
    _seed_connectors(db)

    q = db.query(IntegrationConnector).filter(IntegrationConnector.is_active == True)
    if category:
        q = q.filter(IntegrationConnector.category == category.lower())
    if certified_only:
        q = q.filter(IntegrationConnector.is_certified == True)
    connectors = q.order_by(IntegrationConnector.name).all()

    installed_slugs: set = set()
    if organization_id:
        instances = db.query(IntegrationInstance).filter(
            IntegrationInstance.organization_id == organization_id,
            IntegrationInstance.is_enabled == True,
        ).all()
        # N+1 eliminado (auditoría 2026-08 §7): una consulta por instancia instalada.
        connector_ids = [inst.connector_id for inst in instances if inst.connector_id]
        if connector_ids:
            installed_slugs.update(
                slug for (slug,) in db.query(IntegrationConnector.slug).filter(
                    IntegrationConnector.id.in_(connector_ids)
                ).all()
            )

    return [
        {
            "id": c.id, "name": c.name, "slug": c.slug, "category": c.category,
            "description": c.description, "logo_url": c.logo_url, "docs_url": c.docs_url,
            "auth_scheme": c.auth_scheme, "is_certified": c.is_certified,
            "is_installed": c.slug in installed_slugs,
        }
        for c in connectors
    ]


def install_integration_connector(
    connector_slug: str, name: str, config: dict,
    sync_direction: str, sync_frequency: str,
    organization_id: Optional[str], user_id: str, db: Session,
) -> dict:
    valid_directions = {"inbound", "outbound", "bidirectional"}
    valid_frequencies = {"realtime", "hourly", "daily", "manual"}
    if sync_direction not in valid_directions:
        raise HTTPException(422, f"Invalid sync_direction. Allowed: {sorted(valid_directions)}")
    if sync_frequency not in valid_frequencies:
        raise HTTPException(422, f"Invalid sync_frequency. Allowed: {sorted(valid_frequencies)}")

    _seed_connectors(db)

    connector = db.query(IntegrationConnector).filter(
        IntegrationConnector.slug == connector_slug,
        IntegrationConnector.is_active == True,
    ).first()
    if not connector:
        raise HTTPException(404, f"Connector '{connector_slug}' not found in marketplace")
    if not organization_id:
        raise HTTPException(400, "User has no associated organization")

    config_json = json.dumps(config)
    try:
        encrypted = encrypt_value(config_json)
    except Exception:
        logger.warning("Fallo cifrando config de instancia de integración; almacenando en claro como fallback", exc_info=True)
        encrypted = config_json

    instance = IntegrationInstance(
        organization_id=organization_id,
        connector_id=connector.id,
        name=name,
        encrypted_config=encrypted,
        sync_direction=sync_direction,
        sync_frequency=sync_frequency,
        is_enabled=True,
        created_by=user_id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return {
        "id": instance.id, "name": instance.name,
        "connector": connector_slug,
        "sync_direction": instance.sync_direction,
        "sync_frequency": instance.sync_frequency,
        "is_enabled": instance.is_enabled,
        "created": True,
    }


def list_integration_instances(organization_id: Optional[str], db: Session) -> list:
    if not organization_id:
        return []
    instances = db.query(IntegrationInstance).filter(
        IntegrationInstance.organization_id == organization_id,
        IntegrationInstance.is_enabled == True,
    ).all()
    result = []
    for inst in instances:
        conn = db.query(IntegrationConnector).filter(
            IntegrationConnector.id == inst.connector_id
        ).first()
        result.append({
            "id": inst.id, "name": inst.name,
            "connector_slug": conn.slug if conn else None,
            "connector_name": conn.name if conn else None,
            "connector_category": conn.category if conn else None,
            "sync_direction": inst.sync_direction,
            "sync_frequency": inst.sync_frequency,
            "is_enabled": inst.is_enabled,
            "last_sync_at": str(inst.last_sync_at) if inst.last_sync_at else None,
            "last_sync_status": inst.last_sync_status,
            "last_sync_records": inst.last_sync_records,
            "last_error": inst.last_error,
        })
    return result


def uninstall_integration_connector(
    instance_id: str, organization_id: Optional[str], db: Session,
) -> None:
    inst = db.query(IntegrationInstance).filter(
        IntegrationInstance.id == instance_id,
        IntegrationInstance.organization_id == organization_id,
        IntegrationInstance.is_enabled == True,
    ).first()
    if not inst:
        raise HTTPException(404, "Integration instance not found")
    inst.is_enabled = False
    db.commit()
