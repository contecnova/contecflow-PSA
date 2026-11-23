"""
integrations.py — Motor de integraciones nativas: Slack, Teams, Jira.

Funciones:
  - send_slack_message(webhook_url, text, blocks)
  - send_teams_message(webhook_url, title, text, color)
  - create_jira_issue(config, project_key, summary, description, issue_type)
  - transition_jira_issue(config, issue_key, transition_name)
  - notify_event(event_type, entity, db) → despacha a todas las integraciones activas
"""
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.config import settings
import json
import logging
import urllib.request

from app.core.outbound_url import abrir, validate_outbound_url
import urllib.parse
from typing import Optional
from app.core import timeutil
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger(__name__)
from app.models.cab import IntegrationConfig
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket, TicketType, TicketStatus, TicketPriority, SupportLevel
from app.models.task import Task
from app.models.task import TaskStatus, TaskPriority
from app.models.user import User
from sqlalchemy import func, cast, Integer


# ── Slack ──────────────────────────────────────────────────────────────────────

def send_slack_message(
    webhook_url: str,
    text: str,
    blocks: Optional[list] = None,
    username: str = NOMBRE_DEL_PRODUCTO,
    icon_emoji: str = ":triangular_ruler:",
) -> dict:
    """Envía un mensaje a Slack via Incoming Webhook (`entrega_saliente.enviar_a_webhook`)."""
    from app.services.entrega_saliente import enviar_a_webhook, mensaje_de_slack

    r = enviar_a_webhook(webhook_url, mensaje_de_slack(text, blocks, username=username, icon_emoji=icon_emoji))
    if r.ok:
        return {"ok": True, "response": r.texto}
    logger.warning("Fallo enviando mensaje a Slack: %s", r.error)
    return {"ok": False, "error": r.error}


def build_slack_blocks(title: str, fields: list, color: str = "#00d4ff", url: str = None) -> list:
    """Construye bloques de Slack con formato rico."""
    header_block = {
        "type": "header",
        "text": {"type": "plain_text", "text": title[:150], "emoji": True}
    }
    blocks = [header_block]
    if fields:
        blocks.append({
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": f"*{k}*\n{v}"} for k, v in fields[:10]]
        })
    if url:
        blocks.append({
            "type": "actions",
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": f"Ver en {NOMBRE_DEL_PRODUCTO}"},
                          "url": url, "style": "primary"}]
        })
    return blocks


# ── Microsoft Teams ────────────────────────────────────────────────────────────

def send_teams_message(
    webhook_url: str,
    title: str,
    text: str,
    color: str = "0078D7",
    facts: Optional[list] = None,
    url: Optional[str] = None,
) -> dict:
    """Envía un mensaje a Microsoft Teams via Incoming Webhook (`entrega_saliente`)."""
    from app.services.entrega_saliente import enviar_a_webhook, tarjeta_de_teams

    r = enviar_a_webhook(webhook_url, tarjeta_de_teams(title, text, url=url, hechos=facts, color=color))
    if r.ok:
        return {"ok": True, "response": r.texto}
    logger.warning("Fallo enviando mensaje a Microsoft Teams: %s", r.error)
    return {"ok": False, "error": r.error}


# ── Jira ───────────────────────────────────────────────────────────────────────

def _jira_request(config_dict: dict, method: str, path: str, body: Optional[dict] = None) -> dict:
    """Ejecuta una petición a la API REST de Jira por el cliente de `jira_service`.

    Auditoria 2026-11 (#34): tenia su propio cliente (urllib + Basic armado a
    mano) y devolvia hasta 300 caracteres del cuerpo de la respuesta remota.
    """
    import httpx
    from app.services import jira_service

    base_url   = config_dict.get("base_url", "").rstrip("/")
    email      = config_dict.get("email", "")
    api_token  = config_dict.get("api_token", "")

    if not base_url or not api_token:
        return {"ok": False, "error": "Jira no configurado (falta base_url o api_token)"}

    validate_outbound_url(base_url, field="URL de integración")
    cfg = {"jira_url": base_url, "jira_email": email, "jira_api_token": api_token}
    try:
        return {"ok": True, "data": jira_service.llamar_a_jira_crudo(cfg, method, f"/rest/api/3{path}", json=body)}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.warning("Fallo en petición Jira %s %s: %s", method, path, e)
        return {"ok": False, "error": "No se pudo conectar con Jira"}


def create_jira_issue(
    config_dict: dict,
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str = "Medium",
    labels: Optional[list] = None,
) -> dict:
    """Crea un issue en Jira y devuelve {ok, key, id, url}."""
    body = {
        "fields": {
            "project":   {"key": project_key},
            "summary":   summary[:255],
            "issuetype": {"name": issue_type},
            "priority":  {"name": priority},
            "description": {
                "type":    "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description[:2000]}]}]
            },
        }
    }
    if labels:
        body["fields"]["labels"] = labels

    result = _jira_request(config_dict, "POST", "/issue", body)
    if result["ok"]:
        data    = result["data"]
        base_url = config_dict.get("base_url", "").rstrip("/")
        return {"ok": True, "key": data.get("key"), "id": data.get("id"),
                "url": f"{base_url}/browse/{data.get('key')}"}
    return result


def _clave(issue_key: str) -> str:
    """M95: la clave va a la ruta: se escapa (antes `../` o `?` cambiaban la URL)."""
    from urllib.parse import quote
    return quote(str(issue_key or ""), safe="")


def get_jira_issue(config_dict: dict, issue_key: str) -> dict:
    """Obtiene un issue de Jira."""
    return _jira_request(config_dict, "GET", f"/issue/{_clave(issue_key)}")


def transition_jira_issue(config_dict: dict, issue_key: str, transition_name: str) -> dict:
    """Cambia el estado de un issue Jira buscando la transición por nombre."""
    # Obtener transiciones disponibles
    trans = _jira_request(config_dict, "GET", f"/issue/{_clave(issue_key)}/transitions")
    if not trans["ok"]: return trans

    transition_id = None
    for t in trans["data"].get("transitions", []):
        if t.get("name", "").lower() == transition_name.lower():
            transition_id = t["id"]
            break

    if not transition_id:
        available = [t["name"] for t in trans["data"].get("transitions", [])]
        return {"ok": False, "error": f"Transición '{transition_name}' no encontrada. Disponibles: {available}"}

    return _jira_request(config_dict, "POST", f"/issue/{_clave(issue_key)}/transitions",
                         {"transition": {"id": transition_id}})


def search_jira_issues(config_dict: dict, jql: str, max_results: int = 50) -> dict:
    """Busca issues en Jira via JQL.

    A56 (auditoría 22-11-2026): `POST /rest/api/3/search/jql` (la ruta `/search`
    está retirada en Jira Cloud); la respuesta trae `issues`, `nextPageToken` e
    `isLast`. Aquí una página de `max_results` (el buscador de la pantalla).
    """
    return _jira_request(config_dict, "POST", "/search/jql",
                         {"jql": jql, "maxResults": max_results,
                          "fields": ["summary", "status", "priority", "assignee", "labels"]})


def get_jira_projects(config_dict: dict) -> dict:
    """Lista proyectos disponibles en Jira."""
    return _jira_request(config_dict, "GET", "/project/search?maxResults=50")


# ── Dispatcher de eventos ──────────────────────────────────────────────────────

EVENT_TEMPLATES = {
    # event_type → (emoji, title_template, fields_fn)
    "ticket.created":       ("🎫", "Nuevo ticket: {title}", lambda e: [
        ("Proyecto", e.get("project_name", "—")),
        ("Prioridad", e.get("priority", "—")),
        ("Solicitante", e.get("requester", "—")),
    ]),
    "ticket.resolved":      ("✅", "Ticket resuelto: {title}", lambda e: [
        ("Tiempo de resolución", e.get("resolution_time", "—")),
        ("Agente", e.get("agent", "—")),
    ]),
    "project.status_changed": ("📋", "Proyecto: {title}", lambda e: [
        ("Estado anterior", e.get("old_status", "—")),
        ("Estado nuevo",    e.get("new_status", "—")),
        ("PM",              e.get("pm", "—")),
    ]),
    "milestone.approved":   ("◎",  "Milestone aprobado: {title}", lambda e: [
        ("Proyecto",  e.get("project_name", "—")),
        ("Importe",   e.get("billing_amount", "—")),
    ]),
    "invoice.generated":    ("🧾", "Factura generada: {title}", lambda e: [
        ("Cliente", e.get("client_name", "—")),
        ("Importe", e.get("total", "—")),
    ]),
    "risk.high":            ("⚠️",  "Riesgo alto detectado: {title}", lambda e: [
        ("Proyecto",  e.get("project_name", "—")),
        ("Impacto",   e.get("impact", "—")),
    ]),
    "task.overdue":         ("⏰", "Tarea vencida: {title}", lambda e: [
        ("Proyecto",  e.get("project_name", "—")),
        ("Asignado a", e.get("assignee", "—")),
        ("Vencía",    e.get("due_date", "—")),
    ]),
    "cr.approved":          ("🔄", "Change Request aprobado: {title}", lambda e: [
        ("Proyecto",  e.get("project_name", "—")),
        ("Aprobado por", e.get("approver", "—")),
    ]),
    # Revision 2026-11: la tarjeta de aprobacion existia solo en la vista previa
    # y nadie la enviaba.
    "approval.required":    ("🔔", "Aprobación pendiente: {title}", lambda e: [
        ("Tipo",      e.get("entity_type", "—")),
        ("Paso",      e.get("step", "—")),
        ("Solicitante", e.get("requester", "—")),
    ]),
}


#: A55: plantilla de los eventos sin una propia: título + resumen.
_PLANTILLA_GENERICA = ("🔔", "{title}", lambda e: [(k, e.get(k)) for k in ("summary", "resource")
                                                   if e.get(k)])


def notify_event(
    event_type: str,
    entity: dict,
    db,
    app_base_url: str = settings.FRONTEND_URL,
    *,
    organization_id: Optional[str] = None,
) -> list:
    """
    Despacha un evento a las integraciones activas de Slack/Teams DE LA
    ORGANIZACION que tienen el event_type suscrito.

    entity debe tener: title, id, y campos según el template.

    Auditoria 2026-11 (#29): la consulta no acotaba por organizacion y confiaba
    en el filtro de la sesion; desde un job o un superadmin (sesion sin filtro)
    el aviso de una aprobacion salia por el Slack/Teams de TODAS las
    organizaciones. `organization_id` (o la de la sesion) es obligatoria: sin
    ella no se envia nada.
    """
    org_id = organization_id or (getattr(db, "info", {}) or {}).get("organization_id")
    if not org_id:
        return []
    try:
        from app.models.cab import IntegrationConfig
    except ImportError:
        return []

    # A55 (auditoría 22-11-2026): un evento sin plantilla propia sale con la
    # genérica (antes se perdía: `policy.matched`, `alm.license_reclaim`).
    emoji, title_tpl, fields_fn = EVENT_TEMPLATES.get(event_type) or _PLANTILLA_GENERICA
    # M95: un campo que falta en `entity` ya no corta el envío con KeyError.
    from collections import defaultdict
    title  = f"{emoji} " + title_tpl.format_map(defaultdict(lambda: "—", {"event_type": event_type, **entity}))
    fields = fields_fn(entity)

    configs = db.query(IntegrationConfig).filter(
        IntegrationConfig.is_active == True,
        IntegrationConfig.organization_id == org_id,
        IntegrationConfig.integration_type.in_(["slack", "teams"]),
    ).all()

    results = []
    for cfg in configs:
        from app.core.secret_utils import decrypt_config_secrets
        # `webhook_url` se guarda cifrado: sin descifrar no llegaba ningun aviso.
        cfg_dict = decrypt_config_secrets(json.loads(cfg.config or "{}"))

        # Verificar que el evento está suscrito
        subscribed = cfg_dict.get("events", [])
        if subscribed and event_type not in subscribed:
            continue

        webhook_url = cfg_dict.get("webhook_url", "")
        if not webhook_url:
            continue

        entity_type_map = {
            "ticket":    "service-desk",
            "project":   "projects",
            "milestone": "milestone-billing",
            "invoice":   "invoices",
            "task":      "tasks",
            "risk":      "risks",
            "cr":        "changes",
            "approval":  "approvals",
        }
        entity_section = entity_type_map.get(event_type.split(".")[0], "dashboard")
        url = f"{app_base_url}/{entity_section}"

        if cfg.integration_type == "slack":
            blocks = build_slack_blocks(title, fields, url=url)
            result = send_slack_message(webhook_url, title, blocks=blocks)
        elif cfg.integration_type == "teams":
            color_map = {
                "ticket.created": "0078D7", "risk.high": "FF0000",
                "milestone.approved": "00E5A0", "invoice.generated": "7C3AED",
            }
            result = send_teams_message(
                webhook_url, title,
                entity.get("description", ""),
                color=color_map.get(event_type, "00D4FF"),
                facts=fields, url=url,
            )
        else:
            result = {"ok": False, "error": "Tipo no soportado"}

        results.append({"integration": cfg.name, "result": result})

    return results


# ── QuickBooks / Xero Integration ─────────────────────────────────────────────

def _xero_request(config_dict: dict, method: str, path: str, body=None) -> dict:
    """Ejecuta una petición a la API de Xero."""
    import urllib.request
    import urllib.parse
    import json as _json

    base_url    = settings.XERO_API_BASE
    access_token = config_dict.get("access_token", "")
    tenant_id    = config_dict.get("tenant_id", "")

    if not access_token:
        return {"ok": False, "error": "Falta access_token de Xero"}

    url  = f"{base_url}{path}"
    data = _json.dumps(body).encode() if body else None
    req  = urllib.request.Request(  # noqa: S310
        validate_outbound_url(url, field="URL de integración"), data=data, method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Xero-tenant-id": tenant_id,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )
    try:
        with abrir(req, timeout=outbound_http_timeout(default=15)) as resp:  # noqa: S310
            return {"ok": True, "data": _json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        # M16 (auditoría 22-11-2026): el access token de Xero caduca a los 30
        # minutos. Con 401 y `refresh_token`, se renueva (OAuth 2.0, grant
        # `refresh_token`, https://identity.xero.com/connect/token) y se repite
        # una vez. `config_dict` queda con los tokens nuevos: quien llama los guarda.
        if e.code == 401 and not config_dict.get("_reintentado") and _refrescar_token_xero(config_dict):
            return _xero_request({**config_dict, "_reintentado": True}, method, path, body) | {
                "tokens": {k: config_dict.get(k) for k in ("access_token", "refresh_token")}}
        logger.warning("Xero %s %s -> HTTP %s", method, path, e.code)
        return {"ok": False, "error": f"HTTP {e.code}"}   # sin el cuerpo remoto
    except Exception as e:
        logger.warning("Fallo en petición Xero %s %s: %s", method, path, e)
        return {"ok": False, "error": "No se pudo conectar con Xero"}


def _refrescar_token_xero(config_dict: dict) -> bool:
    """Renueva el access token de Xero con el refresh token (rotatorio: Xero
    devuelve también un refresh token nuevo). True si se renovó."""
    import base64
    import json as _json
    import urllib.parse
    import urllib.request
    rt, cid, sec = (config_dict.get("refresh_token"), config_dict.get("client_id"),
                    config_dict.get("client_secret"))
    if not (rt and cid and sec):
        return False
    url = settings.XERO_TOKEN_URL if getattr(settings, "XERO_TOKEN_URL", None) else "https://identity.xero.com/connect/token"
    req = urllib.request.Request(  # noqa: S310
        validate_outbound_url(url, field="URL de integración"), method="POST",
        data=urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": rt}).encode(),
        headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                 "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with abrir(req, timeout=outbound_http_timeout(default=15)) as resp:  # noqa: S310
            datos = _json.loads(resp.read())
    except Exception:
        logger.warning("Xero: no se pudo renovar el token", exc_info=True)
        return False
    if not datos.get("access_token"):
        return False
    config_dict["access_token"] = datos["access_token"]
    if datos.get("refresh_token"):
        config_dict["refresh_token"] = datos["refresh_token"]
    return True


def _qb_request(config_dict: dict, method: str, path: str, body=None) -> dict:
    """Ejecuta una petición a la API de QuickBooks Online."""
    import urllib.request
    import json as _json

    base_url     = f"{settings.QB_API_BASE}/{config_dict.get('realm_id','')}"
    access_token = config_dict.get("access_token", "")

    if not access_token:
        return {"ok": False, "error": "Falta access_token de QuickBooks"}

    sep  = "&" if "?" in path else "?"
    minor = config_dict.get("minor_version") or getattr(settings, "QB_MINOR_VERSION", 65)
    url  = f"{base_url}{path}{sep}minorversion={minor}"
    data = _json.dumps(body).encode() if body else None
    req  = urllib.request.Request(  # noqa: S310
        validate_outbound_url(url, field="URL de integración"), data=data, method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        },
    )
    try:
        with abrir(req, timeout=outbound_http_timeout(default=15)) as resp:  # noqa: S310
            return {"ok": True, "data": _json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        logger.warning("QuickBooks %s %s -> HTTP %s", method, path, e.code)
        return {"ok": False, "error": f"HTTP {e.code}"}   # M16: sin el cuerpo remoto
    except Exception as e:
        logger.warning("Fallo en petición QuickBooks %s %s: %s", method, path, e)
        return {"ok": False, "error": "No se pudo conectar con QuickBooks"}


def push_invoice_to_xero(config_dict: dict, invoice: dict) -> dict:
    """
    Empuja una factura de Contecflow a Xero.
    invoice: { number, client_name, client_email, issue_date, due_date,
               subtotal, tax_rate, total, lines: [{description, quantity, unit_price}] }
    """
    # M16 (auditoría 22-11-2026): importes a céntimos, moneda de la factura
    # (`CurrencyCode`, ISO 4217) y `TaxType` solo si la conexión lo configura
    # (sin él Xero aplica el impuesto por defecto de la cuenta; «OUTPUT» fijo no
    # vale para muchos países). Sin cliente no se inventa «Cliente».
    if not invoice.get("client_name"):
        return {"ok": False, "error": "La factura no tiene cliente"}
    tax_type = config_dict.get("tax_type")
    xero_invoice = {
        "Type":         "ACCREC",
        "Contact":      {"Name": invoice["client_name"]},
        "CurrencyCode": (invoice.get("currency") or "").upper() or None,
        "InvoiceNumber": invoice.get("number", ""),
        "Date":         invoice.get("issue_date", ""),
        "DueDate":      invoice.get("due_date", invoice.get("issue_date", "")),
        "Status":       "AUTHORISED",
        "LineAmountTypes": "Exclusive",
        "LineItems": [
            {
                "Description": l.get("description", "Servicio"),
                "Quantity":    l.get("quantity", 1),
                "UnitAmount":  round(float(l.get("unit_price", 0) or 0), 2),
                **({"TaxType": tax_type} if tax_type else {}),
            }
            for l in (invoice.get("lines") or [{"description": invoice.get("notes", "Servicios"), "quantity": 1, "unit_price": invoice.get("subtotal", 0)}])
        ],
    }
    xero_invoice = {k: v for k, v in xero_invoice.items() if v is not None}
    result = _xero_request(config_dict, "POST", "/Invoices", {"Invoices": [xero_invoice]})
    if result["ok"]:
        xero_id = result["data"].get("Invoices", [{}])[0].get("InvoiceID")
        return {"ok": True, "xero_invoice_id": xero_id}
    return result


def _cliente_de_quickbooks(config_dict: dict, nombre: Optional[str], correo: Optional[str] = None) -> dict:
    """{"ok", "id"}: el Customer de QuickBooks con ese DisplayName, creado si no existe.

    API de QuickBooks Online: `GET /query?query=select * from Customer where
    DisplayName = '…'` (comillas simples escapadas con barra) y `POST /customer`.
    """
    from urllib.parse import quote
    if not nombre:
        return {"ok": False, "error": "La factura no tiene cliente"}
    literal = str(nombre).replace("\\", "\\\\").replace("'", "\\'")
    r = _qb_request(config_dict, "GET", "/query?query=" + quote(f"select * from Customer where DisplayName = '{literal}'"))
    if not r["ok"]:
        return r
    encontrados = ((r["data"] or {}).get("QueryResponse") or {}).get("Customer") or []
    if encontrados:
        return {"ok": True, "id": encontrados[0].get("Id")}
    cuerpo = {"DisplayName": str(nombre)[:100]}
    if correo:
        cuerpo["PrimaryEmailAddr"] = {"Address": correo}
    r = _qb_request(config_dict, "POST", "/customer", cuerpo)
    if not r["ok"]:
        return r
    return {"ok": True, "id": ((r["data"] or {}).get("Customer") or {}).get("Id")}


def push_invoice_to_quickbooks(config_dict: dict, invoice: dict) -> dict:
    """
    Empuja una factura de Contecflow a QuickBooks Online.
    """

    # M16 (auditoría 22-11-2026): el cliente se busca por nombre (consulta de
    # la API de QuickBooks) y, si no existe, se crea; antes todas las facturas
    # iban al cliente «1». El artículo es el configurado (`default_item_id`):
    # sin él no se envía (antes «1», un artículo cualquiera).
    cliente = _cliente_de_quickbooks(config_dict, invoice.get("client_name"), invoice.get("client_email"))
    if not cliente.get("ok"):
        return cliente
    if not config_dict.get("default_item_id"):
        return {"ok": False, "error": "Falta default_item_id en la conexión de QuickBooks"}
    qb_invoice = {
        "CustomerRef":   {"value": cliente["id"]},
        **({"CurrencyRef": {"value": invoice["currency"].upper()}} if invoice.get("currency") else {}),
        "DocNumber":     invoice.get("number", ""),
        "TxnDate":       invoice.get("issue_date", ""),
        "DueDate":       invoice.get("due_date", invoice.get("issue_date", "")),
        "Line": [
            {
                "DetailType":         "SalesItemLineDetail",
                "Amount":             round(float(l.get("quantity", 1) or 0) * float(l.get("unit_price", 0) or 0), 2),
                "Description":        l.get("description", "Servicio"),
                "SalesItemLineDetail": {
                    "ItemRef":   {"value": config_dict["default_item_id"]},
                    "Qty":       l.get("quantity", 1),
                    "UnitPrice": l.get("unit_price", 0),
                },
            }
            for l in (invoice.get("lines") or [{"description": invoice.get("notes", "Servicios"), "quantity": 1, "unit_price": invoice.get("subtotal", 0)}])
        ],
    }
    result = _qb_request(config_dict, "POST", "/invoice", qb_invoice)
    if result["ok"]:
        qb_id = result["data"].get("Invoice", {}).get("Id")
        return {"ok": True, "qb_invoice_id": qb_id}
    return result


def pull_contacts_from_xero(config_dict: dict) -> dict:
    """Importa contactos/clientes desde Xero."""
    result = _xero_request(config_dict, "GET", "/Contacts?where=IsCustomer=true&order=Name")
    if not result["ok"]: return result
    contacts = result["data"].get("Contacts", [])
    return {
        "ok": True,
        "contacts": [
            {
                "xero_id":  c.get("ContactID"),
                "name":     c.get("Name", ""),
                "email":    c.get("EmailAddress", ""),
                "phone":    c.get("Phones", [{}])[0].get("PhoneNumber", "") if c.get("Phones") else "",
                "vat":      c.get("TaxNumber", ""),
            }
            for c in contacts
        ],
        "total": len(contacts),
    }


def test_xero_connection(config_dict: dict) -> dict:
    """Verifica la conexión con Xero."""
    result = _xero_request(config_dict, "GET", "/Organisation")
    if result["ok"]:
        org = result["data"].get("Organisations", [{}])[0]
        return {"ok": True, "organisation": org.get("Name"), "currency": org.get("BaseCurrency")}
    return result


def test_quickbooks_connection(config_dict: dict) -> dict:
    """Verifica la conexion con QuickBooks Online.

    Auditoria 2026-08. Esta funcion **no existia**, y su endpoint si:
    `POST /accounting/qb/test` la importaba sin `try`, asi que
    **«Verificar conexion con QuickBooks» ha devuelto siempre un 500**. Su
    gemela de Xero —`test_xero_connection`, veinte lineas mas abajo— si estaba,
    y el docstring del router anunciaba las dos.

    Escrita como espejo de la de Xero: una peticion de solo lectura al recurso
    de la propia empresa, que es la forma barata de comprobar que el token vale
    y a que cuenta apunta.

    `CompanyInfo` necesita el `realm_id` en la ruta ademas de en la URL base, y
    esa es la unica diferencia con la de Xero — de ahi que se lea de la
    configuracion en vez de fijarlo.
    """
    realm_id = config_dict.get("realm_id", "")
    if not realm_id:
        return {"ok": False, "error": "Falta realm_id de QuickBooks"}

    result = _qb_request(config_dict, "GET", f"/companyinfo/{realm_id}")
    if result["ok"]:
        info = (result["data"] or {}).get("CompanyInfo", {}) or {}
        return {
            "ok": True,
            "organisation": info.get("CompanyName"),
            "currency": info.get("Country"),
        }
    return result


def get_slack_webhook_url(db, org_id: str | None) -> str | None:
    """La URL del webhook de Slack de esa organizacion, o None si no la tiene.

    Auditoria 2026-08. Esto devolvia **siempre None**, y no por falta de
    configuracion: importaba `SlackConfig` de `app.models.slack`, modulo que NO
    EXISTE —la clase esta en `app.models.mfa`—, y el `except ImportError:
    return None` convertia el fallo en «no configurado». Con datos de Slack
    sembrados y validos, **las notificaciones no salian nunca**, y el docstring
    explicaba el silencio como una decision del usuario.

    Es la forma mas pura del patron de esta auditoria: un acceso tolerante que
    transforma un error en un resultado plausible. Se retira el `try`: si algun
    dia `SlackConfig` deja de estar donde esta, tiene que verse.
    """
    from app.models.mfa import SlackConfig
    # M95 (auditoría 22-11-2026): sin empresa no hay webhook (antes, el de
    # cualquier empresa: el aviso salía por el Slack de otra).
    if not org_id:
        return None
    cfg = db.query(SlackConfig).filter(SlackConfig.organization_id == org_id).first()
    return cfg.webhook_url if cfg and hasattr(cfg, "webhook_url") else None


# ── Hub service helpers (used by integrations_hub router) ─────────────────────

def get_active_integration(db, integration_id: str):
    """Return active IntegrationConfig by id, or None."""
    return db.query(IntegrationConfig).filter(
        IntegrationConfig.id == integration_id,
        IntegrationConfig.is_active == True,
    ).first()


def link_jira_to_task(db, task_id: str, jira_key: str) -> None:
    """Update task.jira_issue_key if the field exists, then commit."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if task and hasattr(task, "jira_issue_key"):
        task.jira_issue_key = jira_key
        db.commit()


def _uno_solo(candidatos):
    """El usuario si hay exactamente uno; si no, nadie.

    Auditoria 2026-11: se buscaba por coincidencia parcial («%ana%» casaba con
    juana@…) y se cogia el primero de CUALQUIER organizacion; el comando se
    ejecutaba en nombre de otra persona. Antes «no se quien eres» que a medias.
    """
    return candidatos[0] if len(candidatos) == 1 else None


class VinculoAmbiguo(Exception):
    """El workspace de Slack / tenant de Teams esta vinculado a varias organizaciones."""


def _organizacion_vinculada(db, clave: str, valor: Optional[str], canal: str) -> Optional[str]:
    """La organizacion que declara `clave = valor` (workspace de Slack o tenant de Teams).

    Auditoria 2026-11: el usuario del bot se buscaba por nombre en TODAS las
    organizaciones, y ese nombre lo elige quien escribe. Con el vinculo, solo
    se busca dentro de la organizacion duena del workspace/tenant. Sin vinculo
    se mantiene la busqueda global (decision: no cortar los bots ya en uso) y
    se avisa en el log para que se configure.

    Segunda auditoria 2026-11 (#8): vinculado a MAS de una organizacion ya no
    cae a la busqueda global — lanza `VinculoAmbiguo` y la peticion se rechaza.
    """
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import AppSetting

    if valor:
        with sin_filtro_de_tenant(db):
            orgs = {o for (o,) in db.query(AppSetting.organization_id).filter(
                AppSetting.key == clave, AppSetting.value == valor,
                AppSetting.organization_id.isnot(None)).all()}
        if len(orgs) == 1:
            return orgs.pop()
        if len(orgs) > 1:
            logger.error("%s: %s=%s esta vinculado a varias organizaciones; se rechaza", canal, clave, valor)
            raise VinculoAmbiguo(f"{clave}={valor}")
    logger.warning("%s: %s=%r sin organizacion vinculada; el usuario se busca en todas. "
                   "Configura %s en la organizacion.", canal, clave, valor, clave)
    return None


def organizacion_del_workspace_de_slack(db, team_id: Optional[str]) -> Optional[str]:
    """La organizacion vinculada al workspace (`SLACK_TEAM_ID`); lanza `VinculoAmbiguo`."""
    return _organizacion_vinculada(db, "SLACK_TEAM_ID", team_id, "Slack")


def secreto_de_firma_de_slack(db, org_id: Optional[str]) -> Optional[str]:
    """El signing secret con el que se verifica una peticion de Slack.

    Segunda auditoria 2026-11 (#8): el de la organizacion duena del workspace
    (credencial cifrada `slack.signing_secret` o ajuste `SLACK_SIGNING_SECRET`
    de esa organizacion) y, si no tiene, el global.
    """
    from app.core.config import settings as _settings
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion

    propio = secreto_propio_de_la_organizacion(
        db, "slack", "signing_secret", "SLACK_SIGNING_SECRET", org_id) if org_id else None
    return propio or _settings.SLACK_SIGNING_SECRET


def find_user_by_slack_name(db, user_name: str, team_id: Optional[str] = None):
    """Usuario de Slack: nombre de usuario o parte local del correo, exactos y sin ambiguedad."""
    nombre = (user_name or "").strip().lower()
    if not nombre:
        return None
    from sqlalchemy import func
    consulta = db.query(User).filter(
        User.is_active == True,  # noqa: E712
        (func.lower(User.username) == nombre) | (func.lower(User.email).like(f"{nombre}@%")),
    )
    try:
        org = _organizacion_vinculada(db, "SLACK_TEAM_ID", team_id, "Slack")
    except VinculoAmbiguo:
        return None
    if org:
        consulta = consulta.filter(User.organization_id == org)
    return _uno_solo(consulta.limit(2).all())


def find_user_by_teams_name(db, teams_name: str, tenant_id: Optional[str] = None):
    """Usuario de Teams: nombre completo exacto (sin mayusculas) y sin ambiguedad."""
    nombre = " ".join((teams_name or "").split()).lower()
    if not nombre:
        return None
    from sqlalchemy import func
    consulta = db.query(User).filter(
        User.is_active == True,  # noqa: E712
        func.lower(User.full_name) == nombre,
    )
    try:
        org = _organizacion_vinculada(db, "TEAMS_TENANT_ID", tenant_id, "Teams")
    except VinculoAmbiguo:
        return None
    if org:
        consulta = consulta.filter(User.organization_id == org)
    return _uno_solo(consulta.limit(2).all())


def slack_create_task_from_text(db, text: str, user) -> dict:
    """Parse text, create a Task in the db, and return a Slack response dict."""
    import re
    import uuid

    project_match = re.search(r'#(\S+)', text)
    title = re.sub(r'#\S+', '', text).strip() or "Tarea creada desde Slack"
    project_id = None
    proj = None
    if project_match:
        code = project_match.group(1).upper()
        proj = db.query(Project).filter(Project.code.ilike(code)).first()
        if proj:
            project_id = proj.id

    task = Task(
        id=str(uuid.uuid4()), title=title, status=TaskStatus.todo,
        priority=TaskPriority.medium, project_id=project_id,
        assignee_id=user.id if user else None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    location = f" en {proj.name}" if project_id and proj else ""
    return {
        "response_type": "in_channel",
        "text": f"✅ Tarea creada: *{task.title}* (`{task.code}`){location}",
    }


def slack_log_time_from_text(db, text: str, user) -> dict:
    """Parse text, create an Imputation in the db, and return a Slack response dict.

    Auditoría 22-11-2026 (A34): creaba `Imputation(...)` a mano, sin coste, sin
    tope, sin cierre de periodo ni pertenencia, con el primer número del texto
    (también el de `#PRJ-0001`) y el proyecto buscado en todas las empresas.
    Ahora el proyecto es obligatorio y de la empresa de la persona, las horas
    son el primer número FUERA del código, y el alta pasa por
    `imputation_service.crear_imputacion_validada` (las reglas del formulario).
    """
    import re
    from app.core.errores import ErrorDeDominio
    from app.services.imputation_service.alta import crear_imputacion_validada

    if not user:
        return {"response_type": "ephemeral", "text": f"❌ No encontré tu usuario en {NOMBRE_DEL_PRODUCTO}. Contacta con el admin."}

    project_match = re.search(r'#(\S+)', text)
    sin_codigo = re.sub(r'#\S+', '', text)
    hours_match = re.search(r'(\d+(?:[.,]\d+)?)', sin_codigo)
    if not hours_match or not project_match:
        return {"response_type": "ephemeral", "text": "❌ Indica las horas y el proyecto. Ejemplo: `/contecflow tiempo 2.5 #PRJ-0001 Revisión de diseño`"}

    hours = float(hours_match.group(1).replace(',', '.'))
    description = re.sub(r'\d+(?:[.,]\d+)?', '', sin_codigo, count=1).strip() or "Imputación desde Slack"
    q = db.query(Project).filter(Project.code == project_match.group(1).upper())
    if getattr(user, "organization_id", None):
        q = q.filter(Project.organization_id == user.organization_id)
    proj = q.first()
    if not proj:
        return {"response_type": "ephemeral", "text": f"❌ No encuentro el proyecto {project_match.group(1)}."}

    try:
        crear_imputacion_validada(user, db, project_id=proj.id, fecha=timeutil.today_for_user(user),
                                  horas=hours, description=description, is_billable=bool(proj.is_billable))
    except ErrorDeDominio as exc:
        db.rollback()
        return {"response_type": "ephemeral", "text": f"❌ {exc.detail}"}
    return {
        "response_type": "in_channel",
        "text": f"⏱ *{hours}h* registradas para {user.full_name} — {description}",
    }


def slack_get_status_by_code(db, code: str) -> dict:
    """Query task or project by code and return a Slack response dict."""

    task = db.query(Task).filter(Task.code.ilike(code.upper())).first()
    if task:
        return {
            "response_type": "ephemeral",
            "text": f"📋 *{task.code}* — {task.title}\nEstado: `{task.status}` · Prioridad: `{task.priority}`",
        }
    proj = db.query(Project).filter(Project.code.ilike(code.upper())).first()
    if proj:
        return {
            "response_type": "ephemeral",
            "text": (
                f"📁 *{proj.code}* — {proj.name}\n"
                f"Estado: `{proj.status}` · PM: {proj.project_manager.full_name if proj.project_manager else '—'}"
            ),
        }
    return {"response_type": "ephemeral", "text": f"❌ No encontré ningún elemento con código `{code}`"}


# ── Slack helpers ──────────────────────────────────────────────────────────────

def slack_help_response() -> dict:
    return {
        "response_type": "ephemeral",
        "text": (
            f"*Comandos disponibles de {NOMBRE_DEL_PRODUCTO}:*\n"
            "• `/contecflow tarea <título> [#PRJ-code]` — Crear tarea\n"
            "• `/contecflow tiempo <horas> [#PRJ-code] [descripción]` — Registrar tiempo\n"
            "• `/contecflow ticket <asunto>` — Crear ticket en Service Desk\n"
            "• `/contecflow ver <INC-0042>` — Ver un ticket con sus botones\n"
            "• `/contecflow comentar <INC-0042> <texto>` — Comentar un ticket\n"
            "• `/contecflow asignarme <INC-0042>` / `encurso <INC-0042>` — Tomarlo / ponerlo en curso\n"
            "• `/contecflow resolver <INC-0042> <resolución>` — Resolverlo\n"
            "• `/contecflow estado <code>` — Ver estado de tarea o proyecto (ej: TSK-0042)\n"
            "• `/contecflow ayuda` — Ver esta ayuda"
        ),
    }


def build_block_kit_message(event_type: str, payload: dict) -> dict:
    base_url = settings.FRONTEND_URL  # 19-11-2026: sin respaldo localhost:3000 (FRONTEND_URL se valida en producción)

    if event_type == "task_overdue":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Task Overdue"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Task:*\n{payload.get('task_title', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{payload.get('project_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Due Date:*\n{payload.get('due_date', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Assignee:*\n{payload.get('assignee', 'N/A')}"},
                ]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "View Task"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}",
                     "style": "primary"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Update Status"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}?action=update"},
                ]},
            ]
        }
    if event_type == "invoice_paid":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ Invoice Paid"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:*\n{payload.get('invoice_number', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Amount:*\n{payload.get('currency', settings.DEFAULT_CURRENCY)} {payload.get('amount', 0):,.2f}"},
                    {"type": "mrkdwn", "text": f"*Client:*\n{payload.get('client_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Paid At:*\n{payload.get('paid_at', 'N/A')}"},
                ]},
            ]
        }
    if event_type == "approval_required":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🔔 Approval Required"}},
                {"type": "section", "text": {
                    "type": "mrkdwn",
                    "text": f"*{payload.get('entity_type', 'Item').title()}* submitted by "
                            f"*{payload.get('submitter', 'Unknown')}* requires your approval.",
                }},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": " ✅ Approve"},
                     "style": "primary",
                     "url": f"{base_url}/approvals?request={payload.get('request_id', '')}"},
                    {"type": "button", "text": {"type": "plain_text", "text": " ❌ Reject"},
                     "style": "danger",
                     "url": f"{base_url}/approvals?request={payload.get('request_id', '')}"},
                ]},
            ]
        }

    return {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"*NexusPM Notification:* {payload.get('message', 'Event occurred')}"}}]}
