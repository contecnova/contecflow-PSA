"""Conectores ETL de BI: extraer de un sistema externo y dejarlo para BI.

Cada conector declara sus ``campos`` (lo que hay que darle y cuáles son
secretos) y sus ``entidades``; con eso la pantalla pinta el formulario sin
saber nada de cada proveedor. ``fuente_rest`` es el genérico: cualquier API
JSON se conecta con una URL, una cabecera de autenticación y la ruta a la
lista dentro de la respuesta, sin escribir código.

Revisión 2026-11. Medido antes: los extractores añadidos después capturaban
cualquier error y devolvían ``[]``, así que una credencial mala quedaba como
«sincronizado, 0 registros»; y la entidad por defecto era ``"default"``, que
HubSpot, Stripe y Xero no reconocían. Ahora el error sube y queda en el
registro, y la entidad es la que se configura o la primera que el conector
declara. Toda petición pasa por ``assert_safe_outbound_url``.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
import httpx as _httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.network import assert_safe_outbound_url
from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, "BaseConnector"] = {}

_SYNC_DATA_KEY_TPL = "bi.etl.sync_data.{connector}.{org}"
_SYNC_LOG_KEY_TPL = "bi.etl.sync_log.{connector}.{org}"


#: Ajustes de la organización que sincroniza. Los fija el servicio (que tiene
#: la sesión y lee los valores de Admin) con ``ajustes(...)``; aquí sólo se
#: leen. Sin fijar, valen los de ``Settings``.
_AJUSTES: ContextVar[Dict[str, Any]] = ContextVar("bi_etl_ajustes", default={})


@contextmanager
def ajustes(**valores: Any):
    marca = _AJUSTES.set(valores)
    try:
        yield
    finally:
        _AJUSTES.reset(marca)


def _ajuste(clave: str) -> Any:
    return _AJUSTES.get().get(clave, getattr(settings, clave))


def _tam() -> int:
    """Registros por petición (``BI_ETL_PAGE_SIZE``)."""
    return int(_ajuste("BI_ETL_PAGE_SIZE"))


def _plazo(timeout: Optional[float]) -> float:
    return float(timeout or _ajuste("BI_ETL_HTTP_TIMEOUT_S"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_key(connector: str, organization_id: Optional[str]) -> str:
    return _SYNC_DATA_KEY_TPL.format(connector=connector, org=organization_id or "global")


def _set_json(
    db: Session,
    key: str,
    organization_id: Optional[str],
    value: Any,
    description: str,
) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=organization_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


# ── HTTP helpers (replaces urllib.request across all connectors) ───────────────

def _http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Any:
    """GET con httpx, tras comprobar que la URL no apunta a la red interna."""
    assert_safe_outbound_url(url)
    with _httpx.Client(timeout=_plazo(timeout)) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


def _http_post(
    url: str,
    payload: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    raw_body: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Any:
    """Synchronous HTTP POST using httpx.

    Pass *raw_body* (str) to send a pre-serialised string body instead of *payload* (dict).
    """
    assert_safe_outbound_url(url)
    with _httpx.Client(timeout=_plazo(timeout)) as client:
        if raw_body is not None:
            resp = client.post(url, content=raw_body.encode(), headers=headers or {})
        elif payload is not None:
            resp = client.post(url, json=payload, headers=headers or {})
        else:
            resp = client.post(url, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


def _log_sync(
    db: Session,
    connector: str,
    organization_id: Optional[str],
    result: Dict[str, Any],
) -> None:
    """Append a sync event to the connector's rolling log stored as AppSetting JSON."""
    key = _SYNC_LOG_KEY_TPL.format(connector=connector, org=organization_id or "global")
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    logs: list = []
    if row and row.value:
        try:
            logs = json.loads(row.value)
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            logs = []
    entry = {
        "connector": connector,
        "ok": result.get("ok", False),
        "records_ingested": result.get("records_ingested", 0),
        "error": result.get("error"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
    }
    logs.append(entry)
    tope = int(_ajuste("BI_ETL_LOG_MAX_ENTRIES"))
    if len(logs) > tope:
        logs = logs[-tope:]
    serialized = json.dumps(logs, ensure_ascii=False, separators=(",", ":"))
    if not row:
        row = AppSetting(
            key=key,
            organization_id=organization_id,
            description=f"BI ETL sync log: {connector}",
            value=serialized,
        )
        db.add(row)
    else:
        row.value = serialized
    db.commit()


# ── Base connector ─────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """Abstract base for all BI ETL connectors."""

    name: str = "base"
    #: Lo que hay que darle: ``(clave, secreto)``. La pantalla pinta un campo
    #: por cada uno y los secretos no se devuelven nunca.
    campos: tuple = ()
    entidades: tuple = ("default",)
    #: Paquete opcional que necesita: ``(módulo, nombre para pip)``. Los que
    #: hablan HTTP directo no necesitan ninguno.
    requiere: Optional[tuple] = None

    def falta(self) -> Optional[str]:
        """El ``pip install`` que falta, o ``None`` si se puede usar."""
        if not self.requiere:
            return None
        import importlib.util
        try:
            encontrado = importlib.util.find_spec(self.requiere[0]) is not None
        except (ImportError, ValueError):
            encontrado = False
        return None if encontrado else f"pip install {self.requiere[1]}"

    def entidad(self, config: Dict[str, Any]) -> str:
        """La configurada o la primera que declara; una desconocida es un error."""
        e = (config.get("entity") or "").strip() or self.entidades[0]
        if e not in self.entidades:
            raise ValueError(f"Entidad «{e}» no soportada por {self.name}: {', '.join(self.entidades)}")
        return e

    def probar(self, config: Dict[str, Any]) -> int:
        """Conecta y extrae sin guardar nada: cuántos registros traería."""
        return len(self.extract(self.connect(config), entity=self.entidad(config), filters=config.get("filters") or {}))

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> Any:
        """Initialise and return a client session using the provided config."""

    @abstractmethod
    def extract(self, client: Any, entity: str = "default", filters: Optional[Dict] = None) -> List[Dict]:
        """Pull raw records from the source."""

    def transform(self, raw_records: List[Dict], mapping: Optional[Dict] = None) -> List[Dict]:
        """Normalise raw records to internal schema. Override for custom transforms."""
        if not mapping:
            return raw_records
        out = []
        for rec in raw_records:
            transformed = {}
            for src_field, dst_field in mapping.items():
                transformed[dst_field] = rec.get(src_field)
            out.append(transformed)
        return out

    def load(
        self,
        db: Session,
        records: List[Dict],
        organization_id: Optional[str],
    ) -> int:
        """Persist transformed records as AppSetting JSON blob."""
        key = _store_key(self.name, organization_id)
        payload = {
            "connector": self.name,
            "records": records,
            "count": len(records),
            "loaded_at": _iso_now(),
        }
        _set_json(db, key, organization_id, payload, f"BI ETL sync data: {self.name}")
        return len(records)

    def run_sync(
        self,
        config: Dict[str, Any],
        organization_id: Optional[str],
        db: Session,
        filters: Optional[Dict] = None,
        field_mapping: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Full ETL pipeline: connect → extract → transform → load → log."""
        started_at = _iso_now()
        try:
            entity = self.entidad(config)
            client = self.connect(config)
            raw = self.extract(client, entity=entity, filters=filters or config.get("filters") or {})
            records = self.transform(raw, mapping=field_mapping)
            count = self.load(db, records, organization_id)
            result = {
                "ok": True,
                "connector": self.name,
                "records_ingested": count,
                "entity": entity,
                "started_at": started_at,
                "finished_at": _iso_now(),
            }
        except Exception as exc:
            logger.warning("BI ETL sync error [%s]: %s", self.name, exc)
            result = {
                "ok": False,
                "connector": self.name,
                "records_ingested": 0,
                "error": str(exc)[:500],
                "started_at": started_at,
                "finished_at": _iso_now(),
            }
        _log_sync(db, self.name, organization_id, result)
        return result


# ── Salesforce connector ───────────────────────────────────────────────────────

class SalesforceConnector(BaseConnector):
    """Pulls Opportunity + Account data from Salesforce using simple-salesforce."""

    name = "salesforce"
    requiere = ('simple_salesforce', 'simple-salesforce')
    campos = (('instance_url', False), ('access_token', True), ('username', False), ('password', True), ('security_token', True), ('domain', False))

    def connect(self, config: Dict[str, Any]) -> Any:
        try:
            from simple_salesforce import Salesforce  # type: ignore
        except ImportError:
            raise ImportError("pip install simple-salesforce")

        instance_url = config.get("instance_url", "")
        # Accept session_id/access_token (OAuth) or username+password+security_token
        if config.get("access_token"):
            return Salesforce(instance_url=instance_url, session_id=config["access_token"])
        return Salesforce(
            username=config.get("username", ""),
            password=config.get("password", ""),
            security_token=config.get("security_token", ""),
            domain=config.get("domain", "login"),
        )

    def extract(self, client: Any, entity: str = "Opportunity", filters: Optional[Dict] = None) -> List[Dict]:
        soql = f"SELECT Id, Name, Amount, CloseDate, StageName, AccountId FROM {entity} LIMIT {_tam()}"  # noqa: S608
        result = client.query_all(soql)
        records = result.get("records", [])
        return [{k: v for k, v in r.items() if k != "attributes"} for r in records]


# ── HubSpot connector ──────────────────────────────────────────────────────────

class HubSpotConnector(BaseConnector):
    """Pulls Deals + Contacts from HubSpot v3 API."""

    name = "hubspot"
    requiere = ('hubspot', 'hubspot-api-client')
    campos = (('access_token', True),)

    def connect(self, config: Dict[str, Any]) -> Any:
        try:
            import hubspot  # type: ignore  # noqa: F401  (optional-dependency availability probe)
            from hubspot import HubSpot  # type: ignore
        except ImportError:
            raise ImportError("pip install hubspot-api-client")
        return HubSpot(access_token=config.get("access_token", ""))

    def extract(self, client: Any, entity: str = "deals", filters: Optional[Dict] = None) -> List[Dict]:
        if entity == "deals":
            resp = client.crm.deals.basic_api.get_page(limit=_tam(), properties=["dealname", "amount", "closedate", "dealstage"])
            return [r.to_dict() for r in (resp.results or [])]
        if entity == "contacts":
            resp = client.crm.contacts.basic_api.get_page(limit=_tam(), properties=["firstname", "lastname", "email", "company"])
            return [r.to_dict() for r in (resp.results or [])]
        raise ValueError(f"Entidad no soportada: {entity}")


# ── Jira connector ─────────────────────────────────────────────────────────────

class JiraConnector(BaseConnector):
    """Pulls Issues from Jira Cloud using jira-python."""

    name = "jira"
    requiere = ('jira', 'jira')
    campos = (('server_url', False), ('email', False), ('api_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        try:
            from jira import JIRA  # type: ignore
        except ImportError:
            raise ImportError("pip install jira")
        return JIRA(
            server=config.get("server_url", ""),
            basic_auth=(config.get("email", ""), config.get("api_token", "")),
        )

    def extract(self, client: Any, entity: str = "issues", filters: Optional[Dict] = None) -> List[Dict]:
        jql = (filters or {}).get("jql", "project IS NOT EMPTY ORDER BY updated DESC")
        issues = client.search_issues(jql, maxResults=_tam())
        return [
            {
                "id": str(i.id),
                "key": i.key,
                "summary": i.fields.summary,
                "status": i.fields.status.name if i.fields.status else None,
                "priority": i.fields.priority.name if hasattr(i.fields, "priority") and i.fields.priority else None,
                "assignee": i.fields.assignee.displayName if hasattr(i.fields, "assignee") and i.fields.assignee else None,
                "created": str(i.fields.created),
                "updated": str(i.fields.updated),
            }
            for i in issues
        ]


# ── Stripe connector ───────────────────────────────────────────────────────────

class StripeConnector(BaseConnector):
    """Pulls Charges + Invoices from Stripe."""

    name = "stripe"
    requiere = ('stripe', 'stripe')
    campos = (('api_key', True),)

    def connect(self, config: Dict[str, Any]) -> Any:
        try:
            import stripe as _stripe  # type: ignore
        except ImportError:
            raise ImportError("pip install stripe")
        _stripe.api_key = config.get("api_key", "")
        return _stripe

    def extract(self, client: Any, entity: str = "invoices", filters: Optional[Dict] = None) -> List[Dict]:
        limit = int((filters or {}).get("limit", _tam()))
        if entity == "invoices":
            resp = client.Invoice.list(limit=limit)
            return [
                {
                    "id": inv.id,
                    "customer": inv.customer,
                    "amount_paid": inv.amount_paid,
                    "currency": inv.currency,
                    "status": inv.status,
                    "created": inv.created,
                    "period_start": inv.period_start,
                    "period_end": inv.period_end,
                }
                for inv in (resp.data or [])
            ]
        if entity == "charges":
            resp = client.Charge.list(limit=limit)
            return [
                {
                    "id": ch.id,
                    "amount": ch.amount,
                    "currency": ch.currency,
                    "status": ch.status,
                    "customer": ch.customer,
                    "created": ch.created,
                }
                for ch in (resp.data or [])
            ]
        raise ValueError(f"Entidad no soportada: {entity}")


# ── Xero connector ─────────────────────────────────────────────────────────────

class XeroConnector(BaseConnector):
    """Pulls Invoices + Contacts from Xero using xero-python."""

    name = "xero"
    requiere = ('xero_python', 'xero-python')
    campos = (('tenant_id', False), ('client_id', False), ('client_secret', True), ('access_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        try:
            from xero_python.api_client import ApiClient  # type: ignore
            from xero_python.api_client.configuration import Configuration  # type: ignore  # noqa: F401
            from xero_python.api_client.oauth2 import OAuth2Token  # type: ignore
            from xero_python.accounting import AccountingApi  # type: ignore  # noqa: F401
        except ImportError:
            raise ImportError("pip install xero-python")

        api_client = ApiClient(
            oauth2_token=OAuth2Token(
                client_id=config.get("client_id", ""),
                client_secret=config.get("client_secret", ""),
            )
        )
        api_client.set_oauth2_token(config.get("access_token", ""))
        return {"client": api_client, "tenant_id": config.get("tenant_id", "")}

    def extract(self, client: Any, entity: str = "invoices", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            from xero_python.accounting import AccountingApi  # type: ignore
        except ImportError:
            raise ImportError("pip install xero-python")

        api = AccountingApi(client["client"])
        tenant_id = client["tenant_id"]

        if entity == "invoices":
            resp = api.get_invoices(tenant_id)
            return [
                {
                    "invoice_id": str(inv.invoice_id),
                    "type": inv.type,
                    "status": inv.status,
                    "total": float(inv.total or 0),
                    "amount_due": float(inv.amount_due or 0),
                    "date": str(inv.date) if inv.date else None,
                    "due_date": str(inv.due_date) if inv.due_date else None,
                }
                for inv in (resp.invoices or [])
            ]
        if entity == "contacts":
            resp = api.get_contacts(tenant_id)
            return [
                {
                    "contact_id": str(c.contact_id),
                    "name": c.name,
                    "email_address": c.email_address,
                    "is_customer": c.is_customer,
                }
                for c in (resp.contacts or [])
            ]
        raise ValueError(f"Entidad no soportada: {entity}")


# ══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL CONNECTORS — Plugin framework 20+ (v23.10.44)
# ══════════════════════════════════════════════════════════════════════════════

# ── Zendesk ───────────────────────────────────────────────────────────────────

class ZendeskConnector(BaseConnector):
    """Pulls Tickets from Zendesk Support."""

    name = "zendesk"
    campos = (('subdomain', False), ('email', False), ('api_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "subdomain": config.get("subdomain", ""),
            "email": config.get("email", ""),
            "token": config.get("api_token", ""),
        }

    def extract(self, client: Any, entity: str = "tickets", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            import base64

            creds = base64.b64encode(f"{client['email']}/token:{client['token']}".encode()).decode()
            url = f"https://{client['subdomain']}.zendesk.com/api/v2/{entity}.json?per_page={_tam()}"
            data = _http_get(url, headers={"Authorization": f"Basic {creds}"})
            return data.get(entity, [])
        except Exception as exc:
            logger.warning("ZendeskConnector.extract error: %s", exc)
            raise


# ── Freshdesk ─────────────────────────────────────────────────────────────────

class FreshdeskConnector(BaseConnector):
    """Pulls Tickets from Freshdesk."""

    name = "freshdesk"
    campos = (('domain', False), ('api_key', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "domain": config.get("domain", ""),
            "api_key": config.get("api_key", ""),
        }

    def extract(self, client: Any, entity: str = "tickets", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            import base64

            creds = base64.b64encode(f"{client['api_key']}:X".encode()).decode()
            url = f"https://{client['domain']}.freshdesk.com/api/v2/{entity}?per_page={_tam()}"
            return _http_get(url, headers={"Authorization": f"Basic {creds}"})
        except Exception as exc:
            logger.warning("FreshdeskConnector.extract error: %s", exc)
            raise


# ── ServiceNow ────────────────────────────────────────────────────────────────

class ServiceNowConnector(BaseConnector):
    """Pulls Incidents / Problems from ServiceNow Table API."""

    name = "servicenow"
    campos = (('instance', False), ('username', False), ('password', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "instance": config.get("instance", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
        }

    def extract(self, client: Any, entity: str = "incident", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            import base64

            creds = base64.b64encode(f"{client['username']}:{client['password']}".encode()).decode()
            url = (
                f"https://{client['instance']}.service-now.com/api/now/table/{entity}"
                f"?sysparm_limit={_tam()}&sysparm_fields=sys_id,number,short_description,state,priority,category"
            )
            data = _http_get(url, headers={"Authorization": f"Basic {creds}", "Accept": "application/json"})
            return data.get("result", [])
        except Exception as exc:
            logger.warning("ServiceNowConnector.extract error: %s", exc)
            raise


# ── Pipedrive ─────────────────────────────────────────────────────────────────

class PipedriveConnector(BaseConnector):
    """Pulls Deals from Pipedrive CRM."""

    name = "pipedrive"
    campos = (('api_token', True),)

    def connect(self, config: Dict[str, Any]) -> Any:
        return {"api_token": config.get("api_token", "")}

    def extract(self, client: Any, entity: str = "deals", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://api.pipedrive.com/v1/{entity}?api_token={client['api_token']}&limit={_tam()}"
            data = _http_get(url)
            return data.get("data") or []
        except Exception as exc:
            logger.warning("PipedriveConnector.extract error: %s", exc)
            raise


# ── Zoho CRM ──────────────────────────────────────────────────────────────────

class ZohoCRMConnector(BaseConnector):
    """Pulls Leads/Deals from Zoho CRM v3 API."""

    name = "zoho_crm"
    campos = (('domain', False), ('access_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "access_token": config.get("access_token", ""),
            "domain": config.get("domain", "com"),
        }

    def extract(self, client: Any, entity: str = "Deals", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://www.zohoapis.{client['domain']}/crm/v3/{entity}?fields=id,Deal_Name,Amount,Stage,Closing_Date&per_page={_tam()}"
            data = _http_get(url, headers={"Authorization": f"Zoho-oauthtoken {client['access_token']}"})
            return data.get("data") or []
        except Exception as exc:
            logger.warning("ZohoCRMConnector.extract error: %s", exc)
            raise


# ── QuickBooks ────────────────────────────────────────────────────────────────

class QuickBooksConnector(BaseConnector):
    """Pulls Invoices from QuickBooks Online REST API."""

    name = "quickbooks"
    campos = (('realm_id', False), ('sandbox', False), ('access_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "access_token": config.get("access_token", ""),
            "realm_id": config.get("realm_id", ""),
            "sandbox": config.get("sandbox", False),
        }

    def extract(self, client: Any, entity: str = "Invoice", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            base = "sandbox-quickbooks.api.intuit.com" if client["sandbox"] else "quickbooks.api.intuit.com"
            url = f"https://{base}/v3/company/{client['realm_id']}/query?query=select * from {entity} MAXRESULTS {_tam()}"  # noqa: S608
            data = _http_get(
                url,
                headers={"Authorization": f"Bearer {client['access_token']}", "Accept": "application/json"},
            )
            return (data.get("QueryResponse") or {}).get(entity, [])
        except Exception as exc:
            logger.warning("QuickBooksConnector.extract error: %s", exc)
            raise


# ── GitHub ────────────────────────────────────────────────────────────────────

class GitHubConnector(BaseConnector):
    """Pulls Issues/PRs from a GitHub repository."""

    name = "github"
    campos = (('repo', False), ('token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "token": config.get("token", ""),
            "repo": config.get("repo", ""),  # owner/repo
        }

    def extract(self, client: Any, entity: str = "issues", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://api.github.com/repos/{client['repo']}/{entity}?per_page={_tam()}&state=all"
            return _http_get(
                url,
                headers={"Authorization": f"token {client['token']}", "Accept": "application/vnd.github.v3+json"},
            )
        except Exception as exc:
            logger.warning("GitHubConnector.extract error: %s", exc)
            raise


# ── GitLab ────────────────────────────────────────────────────────────────────

class GitLabConnector(BaseConnector):
    """Pulls Issues from a GitLab project."""

    name = "gitlab"
    campos = (('host', False), ('project_id', False), ('token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "token": config.get("token", ""),
            "project_id": config.get("project_id", ""),
            "host": config.get("host", "gitlab.com"),
        }

    def extract(self, client: Any, entity: str = "issues", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://{client['host']}/api/v4/projects/{client['project_id']}/{entity}?per_page={_tam()}"
            return _http_get(url, headers={"PRIVATE-TOKEN": client["token"]})
        except Exception as exc:
            logger.warning("GitLabConnector.extract error: %s", exc)
            raise


# ── Datadog ───────────────────────────────────────────────────────────────────

class DatadogConnector(BaseConnector):
    """Pulls Monitors/Events from Datadog API."""

    name = "datadog"
    campos = (('site', False), ('api_key', True), ('app_key', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "api_key": config.get("api_key", ""),
            "app_key": config.get("app_key", ""),
            "site": config.get("site", "datadoghq.com"),
        }

    def extract(self, client: Any, entity: str = "monitors", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://api.{client['site']}/api/v1/{entity}?count={_tam()}"
            return _http_get(
                url,
                headers={"DD-API-KEY": client["api_key"], "DD-APPLICATION-KEY": client["app_key"]},
            )
        except Exception as exc:
            logger.warning("DatadogConnector.extract error: %s", exc)
            raise


# ── Monday.com ────────────────────────────────────────────────────────────────

class MondayConnector(BaseConnector):
    """Pulls Boards/Items from Monday.com GraphQL API."""

    name = "monday"
    campos = (('token', True),)

    def connect(self, config: Dict[str, Any]) -> Any:
        return {"token": config.get("token", "")}

    def extract(self, client: Any, entity: str = "items", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            data = _http_post(
                "https://api.monday.com/v2",
                raw_body='{"query": "{ boards { id name items_count } }"}',
                headers={"Authorization": client["token"], "Content-Type": "application/json"},
            )
            return (data.get("data") or {}).get("boards", [])
        except Exception as exc:
            logger.warning("MondayConnector.extract error: %s", exc)
            raise


# ── Asana ─────────────────────────────────────────────────────────────────────

class AsanaConnector(BaseConnector):
    """Pulls Tasks from Asana API."""

    name = "asana"
    campos = (('project_gid', False), ('token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "token": config.get("token", ""),
            "project_gid": config.get("project_gid", ""),
        }

    def extract(self, client: Any, entity: str = "tasks", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://app.asana.com/api/1.0/projects/{client['project_gid']}/tasks?opt_fields=gid,name,completed,due_on,assignee"
            data = _http_get(url, headers={"Authorization": f"Bearer {client['token']}"})
            return data.get("data", [])
        except Exception as exc:
            logger.warning("AsanaConnector.extract error: %s", exc)
            raise


# ── Trello ────────────────────────────────────────────────────────────────────

class TrelloConnector(BaseConnector):
    """Pulls Cards from a Trello board."""

    name = "trello"
    campos = (('board_id', False), ('api_key', True), ('token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "api_key": config.get("api_key", ""),
            "token": config.get("token", ""),
            "board_id": config.get("board_id", ""),
        }

    def extract(self, client: Any, entity: str = "cards", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = (
                f"https://api.trello.com/1/boards/{client['board_id']}/cards"
                f"?key={client['api_key']}&token={client['token']}&fields=id,name,due,idList,desc"
            )
            return _http_get(url)
        except Exception as exc:
            logger.warning("TrelloConnector.extract error: %s", exc)
            raise


# ── Shopify ───────────────────────────────────────────────────────────────────

class ShopifyConnector(BaseConnector):
    """Pulls Orders from Shopify Admin API."""

    name = "shopify"
    campos = (('shop', False), ('access_token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "shop": config.get("shop", ""),
            "access_token": config.get("access_token", ""),
        }

    def extract(self, client: Any, entity: str = "orders", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://{client['shop']}/admin/api/2024-01/{entity}.json?limit={_tam()}&status=any"
            data = _http_get(url, headers={"X-Shopify-Access-Token": client["access_token"]})
            return data.get(entity, [])
        except Exception as exc:
            logger.warning("ShopifyConnector.extract error: %s", exc)
            raise


# ── Intercom ──────────────────────────────────────────────────────────────────

class IntercomConnector(BaseConnector):
    """Pulls Conversations from Intercom."""

    name = "intercom"
    campos = (('token', True),)

    def connect(self, config: Dict[str, Any]) -> Any:
        return {"token": config.get("token", "")}

    def extract(self, client: Any, entity: str = "conversations", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://api.intercom.io/{entity}?per_page={_tam()}&display_as=plaintext"
            data = _http_get(
                url,
                headers={
                    "Authorization": f"Bearer {client['token']}",
                    "Accept": "application/json",
                    "Intercom-Version": "2.10",
                },
            )
            return data.get("conversations", [])
        except Exception as exc:
            logger.warning("IntercomConnector.extract error: %s", exc)
            raise


# ── ClickUp ───────────────────────────────────────────────────────────────────

class ClickUpConnector(BaseConnector):
    """Pulls Tasks from ClickUp API v2."""

    name = "clickup"
    campos = (('list_id', False), ('token', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "token": config.get("token", ""),
            "list_id": config.get("list_id", ""),
        }

    def extract(self, client: Any, entity: str = "tasks", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            url = f"https://api.clickup.com/api/v2/list/{client['list_id']}/task?include_closed=true&subtasks=true"
            data = _http_get(url, headers={"Authorization": client["token"]})
            return data.get("tasks", [])
        except Exception as exc:
            logger.warning("ClickUpConnector.extract error: %s", exc)
            raise


# ── Google Analytics 4 ────────────────────────────────────────────────────────

class GoogleAnalyticsConnector(BaseConnector):
    """Pulls session/pageview data from Google Analytics Data API (GA4)."""

    name = "google_analytics"
    requiere = ('google.analytics.data_v1beta', 'google-analytics-data')
    campos = (('property_id', False), ('credentials_json', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return {
            "property_id": config.get("property_id", ""),
            "credentials_json": config.get("credentials_json", ""),
        }

    def extract(self, client: Any, entity: str = "sessions", filters: Optional[Dict] = None) -> List[Dict]:
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest  # type: ignore
            # Antes: `os.environ.setdefault(...)`, global al proceso — la primera
            # organización que sincronizaba fijaba las credenciales de todas.
            ga_client = BetaAnalyticsDataClient.from_service_account_info(json.loads(client["credentials_json"]))
            request = RunReportRequest(
                property=f"properties/{client['property_id']}",
                dimensions=[Dimension(name="date"), Dimension(name="country")],
                metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
                date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
            )
            resp = ga_client.run_report(request)
            return [
                {
                    "date": row.dimension_values[0].value,
                    "country": row.dimension_values[1].value,
                    "sessions": row.metric_values[0].value,
                    "active_users": row.metric_values[1].value,
                }
                for row in resp.rows
            ]
        except Exception as exc:
            logger.warning("GoogleAnalyticsConnector.extract error: %s", exc)
            raise


# ── Webhook / Plugin connector ────────────────────────────────────────────────

class WebhookPluginConnector(BaseConnector):
    """Generic webhook-based connector for custom data sources.

    Configuration:
        endpoint_url: URL to POST/GET for data extraction
        method: "GET" | "POST" (default "GET")
        headers: dict of custom HTTP headers
        payload: JSON body for POST requests
        data_path: dot-separated path to array in response, e.g. "data.items"
    """

    name = "fuente_rest"
    campos = (('endpoint_url', False), ('method', False), ('data_path', False), ('header_name', False), ('header_value', True))

    def connect(self, config: Dict[str, Any]) -> Any:
        return config

    def extract(self, client: Any, entity: str = "default", filters: Optional[Dict] = None) -> List[Dict]:
        url = client.get("endpoint_url", "")
        if not url:
            raise ValueError("Falta endpoint_url")
        method = (client.get("method") or "GET").upper()
        headers = dict(client.get("headers") or {})
        if client.get("header_name") and client.get("header_value"):
            headers[client["header_name"]] = client["header_value"]
        payload_data = client.get("payload")
        data_path = client.get("data_path", "")

        try:
            if method == "POST":
                raw = _http_post(url, payload=payload_data, headers=headers)
            else:
                raw = _http_get(url, headers=headers)

            # Navigate to data_path
            result = raw
            if data_path:
                for segment in data_path.split("."):
                    if not isinstance(result, dict) or segment not in result:
                        raise ValueError(f"data_path «{data_path}»: no hay «{segment}» en la respuesta")
                    result = result[segment]

            return result if isinstance(result, list) else [result]
        except Exception as exc:
            logger.warning("WebhookPluginConnector.extract error: %s", exc)
            raise


# ── Registro ──────────────────────────────────────────────────────────────────
#
# Una sola lista. Antes había tres que no coincidían: el panel enseñaba 20, el
# estado admitía 5 y el registro tenía 22. Las entidades son las que el
# extractor implementa de verdad (medido: Asana, Trello, Intercom, Monday y GA
# ignoraban la entidad y devolvían siempre lo mismo; HubSpot no tenía
# «companies» y Datadog «events» exige un intervalo que no se le pasa).

_ENTIDADES: Dict[str, tuple] = {
    "salesforce": ("Opportunity", "Account", "Contact", "Lead"),
    "hubspot": ("deals", "contacts"),
    "jira": ("issues",),
    "stripe": ("invoices", "charges"),
    "xero": ("invoices", "contacts"),
    "zendesk": ("tickets", "users", "organizations"),
    "freshdesk": ("tickets", "contacts", "companies"),
    "servicenow": ("incident", "problem", "change_request", "cmdb_ci"),
    "pipedrive": ("deals", "persons", "organizations", "activities"),
    "zoho_crm": ("Deals", "Leads", "Contacts", "Accounts"),
    "quickbooks": ("Invoice", "Bill", "Customer", "Vendor"),
    "github": ("issues", "pulls"),
    "gitlab": ("issues", "merge_requests", "pipelines"),
    "datadog": ("monitors",),
    "monday": ("boards",),
    "asana": ("tasks",),
    "trello": ("cards",),
    "shopify": ("orders", "products", "customers"),
    "intercom": ("conversations",),
    "clickup": ("tasks",),
    "google_analytics": ("sessions",),
}

_REGISTRY: Dict[str, BaseConnector] = {
    c.name: c
    for c in (
        SalesforceConnector(), HubSpotConnector(), JiraConnector(), StripeConnector(), XeroConnector(),
        ZendeskConnector(), FreshdeskConnector(), ServiceNowConnector(), PipedriveConnector(),
        ZohoCRMConnector(), QuickBooksConnector(), GitHubConnector(), GitLabConnector(),
        DatadogConnector(), MondayConnector(), AsanaConnector(), TrelloConnector(),
        ShopifyConnector(), IntercomConnector(), ClickUpConnector(), GoogleAnalyticsConnector(),
    )
}
for _n, _c in _REGISTRY.items():
    _c.entidades = _ENTIDADES[_n]

#: Nombre comercial de cada proveedor, para la pantalla.
_ETIQUETAS: Dict[str, str] = {
    "salesforce": "Salesforce", "hubspot": "HubSpot", "jira": "Jira", "stripe": "Stripe", "xero": "Xero",
    "zendesk": "Zendesk", "freshdesk": "Freshdesk", "servicenow": "ServiceNow", "pipedrive": "Pipedrive",
    "zoho_crm": "Zoho CRM", "quickbooks": "QuickBooks", "github": "GitHub", "gitlab": "GitLab",
    "datadog": "Datadog", "monday": "monday.com", "asana": "Asana", "trello": "Trello", "shopify": "Shopify",
    "intercom": "Intercom", "clickup": "ClickUp", "google_analytics": "Google Analytics",
}

#: El tipo genérico: no es una entrada del registro sino la plantilla de cada
#: fuente REST que da de alta el usuario.
TIPO_GENERICO = WebhookPluginConnector.name
SUPPORTED_CONNECTORS = list(_REGISTRY)


def get_connector(name: str) -> BaseConnector:
    """Return connector instance by name; raises ValueError if unsupported."""
    if name not in _REGISTRY:
        raise ValueError(f"Unsupported connector: {name!r}")
    return _REGISTRY[name]


def instancia(tipo: str, nombre: str) -> BaseConnector:
    """El conector de un tipo con el nombre de la fuente (para el genérico, uno por fuente)."""
    if tipo == TIPO_GENERICO:
        c = WebhookPluginConnector()
        c.name = nombre
        return c
    return get_connector(tipo)


def ficha(tipo: str) -> Dict[str, Any]:
    """Lo que la pantalla necesita para pintar el formulario de un tipo."""
    c = WebhookPluginConnector if tipo == TIPO_GENERICO else get_connector(tipo)
    return {
        "etiqueta": _ETIQUETAS.get(tipo, ""),
        "falta": c().falta() if isinstance(c, type) else c.falta(),
        "campos": [{"clave": k, "secreto": sec} for k, sec in c.campos],
        "entidades": list(c.entidades),
    }
