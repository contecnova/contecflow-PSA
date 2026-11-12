"""Integration Marketplace service.

Manages the connector catalog and per-organisation integration instances.

Auditoria 2026-08 (hallazgo 22). Este modulo era la puerta de
`/api/v1/integrations/*`, y **habia una segunda puerta al mismo sitio** en
`endpoints/service_desk/connectors_marketplace.py` (`/sd/connectors/*`), con sus
propias consultas escritas a mano. Cada una era mejor en algo distinto y ninguna
lo era en todo:

* la de integraciones **valida** `sync_direction` y `sync_frequency` contra una
  lista blanca y **cifra** la configuracion; la del Service Desk no hacia
  ninguna de las dos cosas;
* la del Service Desk lista lo instalado con un `JOIN`; la de integraciones
  hacia **una consulta por instancia** para traer su conector;
* la del Service Desk **no sembraba** el catalogo, asi que en un despliegue
  nuevo devolvia una lista vacia mientras la otra devolvia los conectores.

Y el defecto con consecuencia: una instancia creada por la puerta del Service
Desk se quedaba **sin configuracion**, porque ese endpoint no la recibia. Quien
la consume la lee asi —comprobado en `endpoints/salesforce_sync.py`—:

    config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")

...y sin `instance_url` ni `access_token` responde **503 «credentials
incomplete»**. No hay endpoint para rellenarla despues, asi que la integracion
quedaba instalada y muerta para siempre.

Ahora las dos puertas comparten la validacion, el sembrado, la visibilidad del
conector y el cifrado. Las dos conservan la forma de su respuesta: son API
publicada y no habia razon para cambiarla de paso.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session
from app.core.encryption import encrypt_value
from app.models.marketplace import IntegrationConnector
from app.models.marketplace import IntegrationInstance
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: Sentidos de sincronizacion admitidos. Estaban como literal local dentro de
#: `install_integration_connector`, y la otra puerta no los comprobaba.
SENTIDOS_DE_SINCRONIZACION = {"inbound", "outbound", "bidirectional"}

#: Frecuencias admitidas, igual que arriba.
FRECUENCIAS_DE_SINCRONIZACION = {"realtime", "hourly", "daily", "manual"}

#: El orden con el que el Service Desk destaca los conectores de su dominio.
#: Estaba en duro en el cuerpo del endpoint.
CONECTORES_DESTACADOS = [
    "jira", "servicenow", "zendesk", "slack", "teams", "pagerduty",
]

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


def validar_parametros_de_sincronizacion(
    sync_direction: str, sync_frequency: str
) -> None:
    """422 si el sentido o la frecuencia no estan en la lista blanca.

    La puerta del Service Desk no comprobaba ninguno de los dos, asi que
    aceptaba cualquier cadena y la guardaba. Quien despues lee
    `sync_frequency` para decidir cada cuanto sincronizar no sabe que hacer con
    un valor inventado.
    """
    if sync_direction not in SENTIDOS_DE_SINCRONIZACION:
        raise ErrorDeDominio(
            422,
            "Invalid sync_direction. Allowed: "
            f"{sorted(SENTIDOS_DE_SINCRONIZACION)}",
        )
    if sync_frequency not in FRECUENCIAS_DE_SINCRONIZACION:
        raise ErrorDeDominio(
            422,
            "Invalid sync_frequency. Allowed: "
            f"{sorted(FRECUENCIAS_DE_SINCRONIZACION)}",
        )


def _conectores_visibles(db: Session, organization_id: Optional[str]):
    """Los conectores activos que puede ver una organizacion.

    El catalogo que trae el producto se guarda con `organization_id = NULL`
    —`IntegrationConnector` declara `_tenant_filter_include_global`—, asi que la
    visibilidad es «los globales, mas los propios». Las dos puertas leian el
    catalogo **sin filtro alguno**: hoy no hay conectores privados y por tanto
    no habia fuga, pero el modelo permite crearlos y entonces la habria.
    """
    q = db.query(IntegrationConnector).filter(
        IntegrationConnector.is_active == True  # noqa: E712
    )
    if organization_id:
        return q.filter(
            (IntegrationConnector.organization_id == organization_id)
            | (IntegrationConnector.organization_id.is_(None))
        )
    return q.filter(IntegrationConnector.organization_id.is_(None))


def _instancias_con_conector(db: Session, organization_id: str):
    """Las instalaciones de una organizacion junto a su conector, en una consulta."""
    return (
        db.query(IntegrationInstance, IntegrationConnector)
        .join(
            IntegrationConnector,
            IntegrationConnector.id == IntegrationInstance.connector_id,
        )
        .filter(
            IntegrationInstance.organization_id == organization_id,
            IntegrationInstance.is_enabled == True,  # noqa: E712
        )
        .all()
    )


def crear_instancia(
    db: Session,
    *,
    connector: IntegrationConnector,
    organization_id: str,
    name: str,
    config: Optional[dict],
    sync_direction: str,
    sync_frequency: str,
    user_id: str,
) -> IntegrationInstance:
    """Guarda una instalacion con su configuracion CIFRADA.

    El cifrado es lo que la puerta del Service Desk no hacia — porque no
    recibia configuracion en absoluto. Si el cifrado falla se guarda en claro y
    se avisa: el comportamiento viene del codigo original y se conserva
    verbatim, pero queda escrito que es un respaldo y no la intencion.
    """
    config_json = json.dumps(config or {})
    try:
        cifrada = encrypt_value(config_json)
    except Exception:
        logger.warning(
            "Fallo cifrando config de instancia de integración; "
            "almacenando en claro como fallback",
            exc_info=True,
        )
        cifrada = config_json

    instancia = IntegrationInstance(
        organization_id=organization_id,
        connector_id=connector.id,
        name=name,
        encrypted_config=cifrada,
        sync_direction=sync_direction,
        sync_frequency=sync_frequency,
        is_enabled=True,
        created_by=user_id,
    )
    db.add(instancia)
    db.commit()
    db.refresh(instancia)
    return instancia


# ── La puerta del Service Desk ──────────────────────────────────────────────

def catalogo_para_service_desk(
    db: Session,
    user,
    *,
    category: Optional[str] = None,
    certified_only: bool = False,
) -> list[dict]:
    """El catalogo con los conectores de soporte primero.

    Ahora **siembra** el catalogo, como la otra puerta: sin eso, en un
    despliegue nuevo este endpoint devolvia una lista vacia.
    """
    _seed_connectors(db)

    org_id = getattr(user, "organization_id", None)
    q = _conectores_visibles(db, org_id)
    if category:
        q = q.filter(IntegrationConnector.category == category)
    if certified_only:
        q = q.filter(IntegrationConnector.is_certified == True)  # noqa: E712

    filas = q.all()
    filas.sort(key=lambda c: (
        CONECTORES_DESTACADOS.index(c.slug)
        if c.slug in CONECTORES_DESTACADOS else len(CONECTORES_DESTACADOS) + 1,
        (c.name or "").lower(),
    ))
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "category": c.category,
            "description": c.description,
            "docs_url": c.docs_url,
            "auth_scheme": c.auth_scheme,
            "is_certified": c.is_certified,
        }
        for c in filas
    ]


def instalados_para_service_desk(db: Session, user) -> list[dict]:
    """Lo instalado por la organizacion del sujeto, con su conector."""
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        return []
    return [
        {
            "id": inst.id,
            "name": inst.name,
            "connector": {
                "id": conn.id,
                "name": conn.name,
                "slug": conn.slug,
                "category": conn.category,
            },
            "sync_direction": inst.sync_direction,
            "sync_frequency": inst.sync_frequency,
            "is_enabled": inst.is_enabled,
            "last_sync_at": inst.last_sync_at,
            "last_sync_status": inst.last_sync_status,
        }
        for inst, conn in _instancias_con_conector(db, org_id)
    ]


def instalar_por_id(db: Session, user, datos: dict) -> IntegrationInstance:
    """Instala un conector buscandolo por su id, con las mismas comprobaciones.

    La otra puerta lo busca por `slug`; esta por `id`, que es lo que ya recibia
    su endpoint. Lo demas —lista blanca, visibilidad y cifrado— es identico.
    """
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise ErrorDeDominio(400, "organization_id no disponible")

    sentido = datos.get("sync_direction") or "bidirectional"
    frecuencia = datos.get("sync_frequency") or "hourly"
    validar_parametros_de_sincronizacion(sentido, frecuencia)

    _seed_connectors(db)
    connector = (
        _conectores_visibles(db, org_id)
        .filter(IntegrationConnector.id == datos["connector_id"])
        .first()
    )
    if not connector:
        raise ErrorDeDominio(404, "Connector not found")

    return crear_instancia(
        db,
        connector=connector,
        organization_id=org_id,
        name=datos["name"],
        config=datos.get("config"),
        sync_direction=sentido,
        sync_frequency=frecuencia,
        user_id=getattr(user, "id", None),
    )


def list_marketplace_connectors(
    category: Optional[str],
    certified_only: bool,
    organization_id: Optional[str],
    db: Session,
) -> list:
    _seed_connectors(db)

    q = _conectores_visibles(db, organization_id)
    if category:
        q = q.filter(IntegrationConnector.category == category.lower())
    if certified_only:
        q = q.filter(IntegrationConnector.is_certified == True)  # noqa: E712
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
    validar_parametros_de_sincronizacion(sync_direction, sync_frequency)

    _seed_connectors(db)

    connector = (
        _conectores_visibles(db, organization_id)
        .filter(IntegrationConnector.slug == connector_slug)
        .first()
    )
    if not connector:
        raise ErrorDeDominio(404, f"Connector '{connector_slug}' not found in marketplace")
    if not organization_id:
        raise ErrorDeDominio(400, "User has no associated organization")

    instance = crear_instancia(
        db,
        connector=connector,
        organization_id=organization_id,
        name=name,
        config=config,
        sync_direction=sync_direction,
        sync_frequency=sync_frequency,
        user_id=user_id,
    )
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
    # Auditoria 2026-08: esto hacia UNA CONSULTA POR INSTANCIA para traer su
    # conector, mientras la puerta del Service Desk resolvia lo mismo con un
    # `JOIN`. Se usa el `JOIN`, que es la version buena de las dos.
    filas = _instancias_con_conector(db, organization_id)
    result = []
    for inst, conn in filas:
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
        raise ErrorDeDominio(404, "Integration instance not found")
    inst.is_enabled = False
    db.commit()
