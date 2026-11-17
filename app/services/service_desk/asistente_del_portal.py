"""Asistente del portal de clientes que actua, con confirmacion
(service desk, mejoras de mercado 16-11-2026).

El chat de IA del portal respondia pero no hacia nada. Este asistente reconoce
tres peticiones y las resuelve con las herramientas del portal declaradas en la
politica comun de herramientas de IA
(`ai_chat/tool_execution/politica.py`, `POLITICAS_DEL_PORTAL`):

- **Estado de mis tickets** (`portal_ticket_status`, solo lectura): contesta
  al momento con el ticket citado (`INC-0042`) o los abiertos del cliente.
- **Pedir algo del catalogo** (`portal_catalog_request`): busca el servicio
  visible para clientes que mas se parece a lo pedido y PROPONE la peticion;
  solo se crea si el cliente la confirma.
- **Restablecer contraseña** (`portal_password_reset`): solo si la empresa ha
  integrado ese servicio (`SD_PASSWORD_RESET_SERVICE_ID`, un servicio del
  catalogo con su aprovisionamiento); propone la peticion y espera la
  confirmacion. Sin integracion lo dice y no inventa nada.

Lo que se propone queda en `sd_portal_assistant_actions` y caduca a los
`SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES`. El servidor devuelve codigos (intencion,
estado) y datos; los textos los pone el portal en su idioma.

17-11-2026: primero entiende la IA (`asistente_del_portal_ia`, con la busqueda
en la base de conocimiento y una respuesta redactada en el idioma del cliente);
este reconocimiento por palabras queda como respaldo cuando la IA no esta
disponible (`notice: ai_unavailable`) o la empresa la apaga
(`SD_PORTAL_ASSISTANT_AI`). Cada accion se audita (`PORTAL_ASSISTANT`) con su
motor (`engine`: `ai` | `rules`), tambien la confirmacion y el descarte.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error as error_con_codigo
from app.models.service_desk import PortalAssistantAction, ServiceCategory, ServiceItem, Ticket
from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS

#: Cuantos tickets abiertos se ensenan como mucho al preguntar por «mis tickets».
TOPE_DE_TICKETS = 5
_NUMERO = re.compile(r"\b([A-Z]{2,5}-\d{1,8})\b")

#: Palabras que delatan cada intencion, en los idiomas del portal (sin tildes).
_CLAVES = {
    "password_reset": ("contrasena", "password", "clave", "mot de passe", "passwort", "senha", "parola d", "haslo",
                       "密码", "reset", "restablecer", "olvide", "bloquead", "locked"),
    "ticket_status": ("estado", "status", "como va", "mis tickets", "my tickets", "mes tickets", "meine tickets",
                      "meus tickets", "i miei ticket", "moje zgloszenia", "进度", "状态", "statut", "stato"),
    "catalog_request": ("necesito", "quiero", "pedir", "solicitar", "need", "request", "order", "besoin",
                        "brauche", "preciso", "ho bisogno", "potrzebuje", "需要", "申请"),
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _ajuste(db: Session, clave: str, org_id, tipo: str = "str"):
    from app.services import settings_service as s
    return {"str": s.get_runtime_str, "int": s.get_runtime_int, "float": s.get_runtime_float,
            "bool": s.get_runtime_bool}[tipo](db, clave, org_id)


def _auditar(db: Session, cliente, accion: str, datos: dict) -> None:
    from app.services.audit import audit_log
    audit_log(db, None, "PORTAL_ASSISTANT", "portal_assistant", cliente.id, accion,
              metadata={"client_user_id": cliente.id, "organization_id": cliente.organization_id, **datos})


def _servicio_de_contrasenas(db: Session, org_id) -> Optional[ServiceItem]:
    servicio_id = _ajuste(db, "SD_PASSWORD_RESET_SERVICE_ID", org_id)
    if not servicio_id:
        return None
    return db.query(ServiceItem).filter(ServiceItem.id == servicio_id, ServiceItem.organization_id == org_id,
                                        ServiceItem.is_active.is_(True)).first()


def _exigir(db: Session, cliente, herramienta: str) -> None:
    from app.services.ai_chat.tool_execution.politica import codigo_de_denegacion_del_portal
    motivo = codigo_de_denegacion_del_portal(db, cliente, herramienta)
    if motivo:
        codigo, datos = motivo
        raise error_con_codigo(403, codigo, **datos)


def _servicios_visibles(db: Session, org_id) -> list[ServiceItem]:
    return (db.query(ServiceItem).join(ServiceCategory, ServiceCategory.id == ServiceItem.category_id)
            .filter(ServiceItem.organization_id == org_id, ServiceItem.is_active.is_(True),
                    ServiceItem.is_visible_to_clients.is_(True), ServiceCategory.is_active.is_(True)).all())


def _estado(db: Session, cliente, numero: Optional[str]) -> dict:
    _exigir(db, cliente, "portal_ticket_status")
    q = db.query(Ticket).filter(Ticket.requester_client_id == cliente.id)
    if numero:
        t = q.filter(Ticket.number == numero).first()
        tickets = [t] if t is not None else []
    else:
        tickets = (q.filter(Ticket.status.notin_(ESTADOS_DE_TICKET_CERRADOS))
                   .order_by(Ticket.created_at.desc()).limit(TOPE_DE_TICKETS).all())
    return {"tickets": [{"id": t.id, "number": t.number, "title": t.title,
                         "status": getattr(t.status, "value", t.status),
                         "updated_at": (t.updated_at or t.created_at).isoformat() if (t.updated_at or t.created_at) else None}
                        for t in tickets], "asked_number": numero}


def _proponer(db: Session, cliente, accion: str, params: dict, engine: str = "rules") -> dict:
    minutos = int(_ajuste(db, "SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES", cliente.organization_id, "int") or 0) or 15
    fila = PortalAssistantAction(organization_id=cliente.organization_id, client_user_id=cliente.id,
                                 action=accion, params_json=json.dumps(params), engine=engine)
    db.add(fila)
    db.commit()
    return {"id": fila.id, "action": accion, "params": params,
            "expires_at": (_creada(fila) + timedelta(minutes=minutos)).isoformat()}


def _creada(fila: PortalAssistantAction) -> datetime:
    c = fila.created_at or datetime.now(timezone.utc)
    return c if c.tzinfo else c.replace(tzinfo=timezone.utc)


def _en_idioma_de_la_empresa(db: Session, cliente, texto: str) -> Optional[str]:
    """Traduccion en tiempo real (16-11-2026): el mensaje del cliente en el idioma
    de la empresa, para reconocer la peticion y buscar en el catalogo (que esta
    escrito en ese idioma). None si no hace falta o no se puede."""
    from app.services.traduccion.ajustes import idioma_por_defecto
    from app.services.traduccion.servicio import TRADUCIDO, traducir_uno
    r = traducir_uno(db, cliente.organization_id, texto, idioma_por_defecto(db, cliente.organization_id),
                     canal="portal_assistant")
    return r.texto if r.estado == TRADUCIDO else None


def _al_idioma_del_cliente(db: Session, cliente, textos: list[str], idioma: Optional[str] = None) -> list[str]:
    """Titulos de tickets y nombres de servicios en el idioma del cliente (o tal cual)."""
    from app.services.traduccion.idiomas import normalizar
    from app.services.traduccion.servicio import TRADUCIDO, traducir
    destino = normalizar(idioma) or normalizar(getattr(cliente, "language", None))
    if not destino or not textos:
        return textos
    resultados = traducir(db, cliente.organization_id, textos, destino, canal="portal_assistant")
    return [r.texto if r.estado == TRADUCIDO else t for t, r in zip(textos, resultados)]


def idioma_de_la_respuesta(cliente, pedido: Optional[str]) -> str:
    """El idioma del portal en que se contesta: el que pide el portal, el del
    contacto o el primero del portal."""
    from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL, normalizar
    for candidato in (pedido, getattr(cliente, "language", None)):
        codigo = normalizar(candidato)
        if codigo in IDIOMAS_DEL_PORTAL:
            return codigo
    return IDIOMAS_DEL_PORTAL[0]


def interpretar(db: Session, cliente, mensaje: str, idioma: Optional[str] = None,
                historial: Optional[list] = None) -> dict:
    """Que quiere el cliente: contesta (lectura) o propone (escritura).

    Primero la IA (`asistente_del_portal_ia.entender`); sin ella, el
    reconocimiento por palabras con el aviso `ai_unavailable`. Con la
    traduccion activa, el mensaje se entiende tambien en el idioma de la
    empresa y los titulos y servicios que se devuelven van en el del cliente.
    """
    if not (mensaje or "").strip():
        raise error_con_codigo(422, "mensaje_vacio")
    idioma = idioma_de_la_respuesta(cliente, idioma)
    respuesta, aviso = None, None
    if _ajuste(db, "SD_PORTAL_ASSISTANT_AI", cliente.organization_id, "bool"):
        from app.services.service_desk import asistente_del_portal_ia
        respuesta = asistente_del_portal_ia.entender(db, cliente, mensaje, idioma, historial)
        if respuesta is None:
            aviso = "ai_unavailable"
    if respuesta is None:
        respuesta = _interpretar(db, cliente, mensaje)
        respuesta["engine"] = "rules"
        _auditar(db, cliente, respuesta["intent"], {"engine": "rules", "proposed_action": (
            respuesta.get("action") or {}).get("id")})
        if aviso:
            respuesta["notice"] = aviso
    respuesta["language"] = idioma
    tickets = (respuesta.get("result") or {}).get("tickets") or []
    if tickets:
        for t, titulo in zip(tickets, _al_idioma_del_cliente(db, cliente, [t["title"] for t in tickets], idioma)):
            t["title"] = titulo
    params = (respuesta.get("action") or {}).get("params") or {}
    if params.get("service_name"):
        respuesta["action"]["params"] = {**params, "service_name": _al_idioma_del_cliente(
            db, cliente, [params["service_name"]], idioma)[0]}
    db.commit()
    return respuesta


def _interpretar(db: Session, cliente, mensaje: str) -> dict:
    from app.services.service_desk.duplicados import similitud_de_texto
    texto = (mensaje or "").strip()
    if not texto:
        raise error_con_codigo(422, "mensaje_vacio")
    original = texto
    traducido = _en_idioma_de_la_empresa(db, cliente, texto)
    if traducido:
        texto = f"{texto}\n{traducido}"
    n = _norm(texto)
    hallado = _NUMERO.search(texto.upper())
    numero = hallado.group(1) if hallado else None
    org = cliente.organization_id

    if any(k in n for k in _CLAVES["password_reset"]):
        item = _servicio_de_contrasenas(db, org)
        if item is None:
            return {"intent": "password_reset_unavailable"}
        _exigir(db, cliente, "portal_password_reset")
        return {"intent": "password_reset",
                "action": _proponer(db, cliente, "password_reset", {"service_item_id": item.id, "service_name": item.name})}

    if numero or any(k in n for k in _CLAVES["ticket_status"]):
        return {"intent": "ticket_status", "result": _estado(db, cliente, numero)}

    minimo = float(_ajuste(db, "SD_PORTAL_ASSISTANT_MIN_MATCH", org, "float") or 0)
    candidatos = sorted(((similitud_de_texto(texto, f"{s.name} {s.description or ''}"), s)
                         for s in _servicios_visibles(db, org)), key=lambda x: x[0], reverse=True)
    if candidatos and candidatos[0][0] >= minimo and candidatos[0][0] > 0:
        s = candidatos[0][1]
        _exigir(db, cliente, "portal_catalog_request")
        return {"intent": "catalog_request",
                "action": _proponer(db, cliente, "catalog_request",
                                    {"service_item_id": s.id, "service_name": s.name, "description": original[:2000]})}
    if any(k in n for k in _CLAVES["catalog_request"]):
        return {"intent": "catalog_no_match"}
    return {"intent": "none"}


def _accion_del_cliente(db: Session, cliente, accion_id: str) -> PortalAssistantAction:
    fila = db.query(PortalAssistantAction).filter(PortalAssistantAction.id == accion_id,
                                                  PortalAssistantAction.client_user_id == cliente.id).first()
    if fila is None:
        raise error_con_codigo(404, "accion_no_encontrada")
    if fila.status != "proposed":
        raise error_con_codigo(409, "accion_ya_decidida")
    minutos = int(_ajuste(db, "SD_PORTAL_ASSISTANT_ACTION_TTL_MINUTES", cliente.organization_id, "int") or 0) or 15
    if datetime.now(timezone.utc) > _creada(fila) + timedelta(minutes=minutos):
        fila.status = "expired"
        db.commit()
        raise error_con_codigo(410, "propuesta_caducada")
    return fila


def confirmar(db: Session, cliente, accion_id: str) -> dict:
    """El cliente confirma: se crea su peticion del catalogo, como desde el portal."""
    from app.schemas.service_desk import TicketCreateIn
    from app.services.service_desk.ticket_creation_service import build_client_portal_ticket

    fila = _accion_del_cliente(db, cliente, accion_id)
    herramienta = {"catalog_request": "portal_catalog_request", "password_reset": "portal_password_reset"}.get(fila.action)
    if herramienta is None:
        raise error_con_codigo(422, "accion_desconocida")
    _exigir(db, cliente, herramienta)
    params = json.loads(fila.params_json or "{}")
    item = db.query(ServiceItem).filter(ServiceItem.id == params.get("service_item_id"),
                                        ServiceItem.organization_id == cliente.organization_id,
                                        ServiceItem.is_active.is_(True)).first()
    if item is None:
        fila.status = "failed"
        db.commit()
        raise error_con_codigo(409, "servicio_no_disponible")
    ticket = build_client_portal_ticket(db, TicketCreateIn(
        title=item.name[:255], description=params.get("description") or item.name,
        ticket_type=getattr(item.ticket_type, "value", item.ticket_type) or "service_request",
        service_item_id=item.id, source="portal"), cliente)
    fila.status = "executed"
    fila.decided_at = datetime.now(timezone.utc)
    fila.result_json = json.dumps({"ticket_id": ticket.id, "ticket_number": ticket.number})
    _auditar(db, cliente, "confirm", {"action_id": fila.id, "action": fila.action, "engine": fila.engine,
                                      "ticket_id": ticket.id, "ticket_number": ticket.number})
    db.commit()
    return {"id": fila.id, "status": fila.status, "ticket_id": ticket.id, "ticket_number": ticket.number,
            "approval_status": ticket.approval_status}


def cancelar(db: Session, cliente, accion_id: str) -> dict:
    fila = _accion_del_cliente(db, cliente, accion_id)
    fila.status = "cancelled"
    fila.decided_at = datetime.now(timezone.utc)
    _auditar(db, cliente, "cancel", {"action_id": fila.id, "action": fila.action, "engine": fila.engine})
    db.commit()
    return {"id": fila.id, "status": fila.status}
