"""
integrations.py — Motor de integraciones nativas: Slack, Teams, Jira.

Funciones:
  - send_slack_message(webhook_url, text, blocks)
  - send_teams_message(webhook_url, title, text, color)
  - create_jira_issue(config, project_key, summary, description, issue_type)
  - update_jira_issue(config, issue_key, fields)
  - transition_jira_issue(config, issue_key, transition_name)
  - notify_event(event_type, entity, db) → despacha a todas las integraciones activas
"""
from app.core.config import settings
import json
import urllib.request
import urllib.parse
from typing import Optional


# ── Slack ──────────────────────────────────────────────────────────────────────

def send_slack_message(
    webhook_url: str,
    text: str,
    blocks: Optional[list] = None,
    username: str = "Clarive",
    icon_emoji: str = ":triangular_ruler:",
) -> dict:
    """Envía un mensaje a Slack via Incoming Webhook."""
    payload = {
        "username": username,
        "icon_emoji": icon_emoji,
        "text": text,
    }
    if blocks:
        payload["blocks"] = blocks

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
        return {"ok": True, "response": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
            "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Ver en Clarive"},
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
    """Envía un mensaje a Microsoft Teams via Incoming Webhook (Adaptive Card)."""
    payload = {
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": color.lstrip("#"),
        "summary":    title,
        "sections": [{
            "activityTitle":    f"**{title}**",
            "activitySubtitle": text,
            "facts":            [{"name": k, "value": str(v)} for k, v in (facts or [])],
            "markdown":         True,
        }],
    }
    if url:
        payload["potentialAction"] = [{
            "@type": "OpenUri",
            "name":  "Ver en Clarive",
            "targets": [{"os": "default", "uri": url}]
        }]

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
        return {"ok": True, "response": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Jira ───────────────────────────────────────────────────────────────────────

def _jira_request(config_dict: dict, method: str, path: str, body: Optional[dict] = None) -> dict:
    """Ejecuta una petición a la API REST de Jira."""
    base_url   = config_dict.get("base_url", "").rstrip("/")
    email      = config_dict.get("email", "")
    api_token  = config_dict.get("api_token", "")

    if not base_url or not api_token:
        return {"ok": False, "error": "Jira no configurado (falta base_url o api_token)"}

    import base64
    credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3{path}"

    data = json.dumps(body).encode("utf-8") if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "data": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()[:300]
        return {"ok": False, "error": f"HTTP {e.code}: {body_err}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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


def update_jira_issue(config_dict: dict, issue_key: str, fields: dict) -> dict:
    """Actualiza campos de un issue Jira."""
    return _jira_request(config_dict, "PUT", f"/issue/{issue_key}", {"fields": fields})


def get_jira_issue(config_dict: dict, issue_key: str) -> dict:
    """Obtiene un issue de Jira."""
    return _jira_request(config_dict, "GET", f"/issue/{issue_key}")


def transition_jira_issue(config_dict: dict, issue_key: str, transition_name: str) -> dict:
    """Cambia el estado de un issue Jira buscando la transición por nombre."""
    # Obtener transiciones disponibles
    trans = _jira_request(config_dict, "GET", f"/issue/{issue_key}/transitions")
    if not trans["ok"]: return trans

    transition_id = None
    for t in trans["data"].get("transitions", []):
        if t.get("name", "").lower() == transition_name.lower():
            transition_id = t["id"]
            break

    if not transition_id:
        available = [t["name"] for t in trans["data"].get("transitions", [])]
        return {"ok": False, "error": f"Transición '{transition_name}' no encontrada. Disponibles: {available}"}

    return _jira_request(config_dict, "POST", f"/issue/{issue_key}/transitions",
                         {"transition": {"id": transition_id}})


def search_jira_issues(config_dict: dict, jql: str, max_results: int = 50) -> dict:
    """Busca issues en Jira via JQL."""
    return _jira_request(config_dict, "POST", "/search",
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
}


def notify_event(
    event_type: str,
    entity: dict,
    db,
    app_base_url: str = settings.FRONTEND_URL,
) -> list:
    """
    Despacha un evento a todas las integraciones activas de Slack/Teams
    que tienen el event_type suscrito.

    entity debe tener: title, id, y campos según el template.
    """
    try:
        from app.models.cab import IntegrationConfig
    except ImportError:
        return []

    template = EVENT_TEMPLATES.get(event_type)
    if not template:
        return []

    emoji, title_tpl, fields_fn = template
    title  = f"{emoji} " + title_tpl.format(**entity)
    fields = fields_fn(entity)

    configs = db.query(IntegrationConfig).filter(
        IntegrationConfig.is_active == True,
        IntegrationConfig.integration_type.in_(["slack", "teams"]),
    ).all()

    results = []
    for cfg in configs:
        cfg_dict = json.loads(cfg.config or "{}")

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
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Xero-tenant-id": tenant_id,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "data": _json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:300]
        return {"ok": False, "error": f"HTTP {e.code}: {err}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _qb_request(config_dict: dict, method: str, path: str, body=None) -> dict:
    """Ejecuta una petición a la API de QuickBooks Online."""
    import urllib.request
    import json as _json

    base_url     = f"{settings.QB_API_BASE}/{config_dict.get('realm_id','')}"
    access_token = config_dict.get("access_token", "")

    if not access_token:
        return {"ok": False, "error": "Falta access_token de QuickBooks"}

    url  = f"{base_url}{path}?minorversion=65"
    data = _json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "data": _json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:300]
        return {"ok": False, "error": f"HTTP {e.code}: {err}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def push_invoice_to_xero(config_dict: dict, invoice: dict) -> dict:
    """
    Empuja una factura de Clarive a Xero.
    invoice: { number, client_name, client_email, issue_date, due_date,
               subtotal, tax_rate, total, lines: [{description, quantity, unit_price}] }
    """
    xero_invoice = {
        "Type":         "ACCREC",
        "Contact":      {"Name": invoice.get("client_name", "Cliente")},
        "InvoiceNumber": invoice.get("number", ""),
        "Date":         invoice.get("issue_date", ""),
        "DueDate":      invoice.get("due_date", invoice.get("issue_date", "")),
        "Status":       "AUTHORISED",
        "LineAmountTypes": "Exclusive",
        "LineItems": [
            {
                "Description": l.get("description", "Servicio"),
                "Quantity":    l.get("quantity", 1),
                "UnitAmount":  l.get("unit_price", 0),
                "TaxType":     "OUTPUT",
            }
            for l in (invoice.get("lines") or [{"description": invoice.get("notes", "Servicios"), "quantity": 1, "unit_price": invoice.get("subtotal", 0)}])
        ],
    }
    result = _xero_request(config_dict, "POST", "/Invoices", {"Invoices": [xero_invoice]})
    if result["ok"]:
        xero_id = result["data"].get("Invoices", [{}])[0].get("InvoiceID")
        return {"ok": True, "xero_invoice_id": xero_id}
    return result


def push_invoice_to_quickbooks(config_dict: dict, invoice: dict) -> dict:
    """
    Empuja una factura de Clarive a QuickBooks Online.
    """

    # Crear el Customer si no existe (simplificado — en producción buscar primero)
    qb_invoice = {
        "CustomerRef":   {"value": config_dict.get("default_customer_id", "1")},
        "DocNumber":     invoice.get("number", ""),
        "TxnDate":       invoice.get("issue_date", ""),
        "DueDate":       invoice.get("due_date", invoice.get("issue_date", "")),
        "Line": [
            {
                "DetailType":         "SalesItemLineDetail",
                "Amount":             l.get("quantity", 1) * l.get("unit_price", 0),
                "Description":        l.get("description", "Servicio"),
                "SalesItemLineDetail": {
                    "ItemRef":   {"value": config_dict.get("default_item_id", "1")},
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
    """Verifica la conexión con QuickBooks."""
    result = _qb_request(config_dict, "GET", "/companyinfo/" + config_dict.get("realm_id", ""))
    if result["ok"]:
        info = result["data"].get("CompanyInfo", {})
        return {"ok": True, "company": info.get("CompanyName"), "country": info.get("Country")}
    return result
