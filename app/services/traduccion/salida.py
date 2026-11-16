"""Lo que el operador envia al cliente (salida).

1. **Idioma del cliente** (`idioma_del_cliente`), en este orden: el del
   contacto (usuario del portal), el del portal (el de la conversacion del
   chat, que envia el portal, o el idioma por defecto del portal de su
   empresa cliente) y el detectado en sus ultimos mensajes (o en el ticket).
2. **Vista previa** (`vista_previa`): el texto del operador en el idioma del
   cliente, para revisarlo y corregirlo antes de enviar.
3. **Envio** (`preparar` + `anotar_autor`): lo que se guarda como cuerpo del
   mensaje es lo que recibe el cliente, en su idioma; lo que escribio el
   operador queda en `message_translations` con `origin=author` (o `edited`
   si corrigio la vista previa), y la auditoria apunta idiomas y proveedor.
   Sin vista previa (Slack, API) se traduce solo si `TRANSLATION_OUTBOUND_AUTO`.
   Si no se puede traducir, sale el original (nunca a medias) y queda el motivo.
4. **Lo que ve el cliente** (`texto_para_cliente`): el cuerpo y, si la empresa
   lo quiere (`TRANSLATION_INCLUDE_ORIGINAL`), el original del operador debajo.

Las notas internas no pasan por aqui: jamas salen al cliente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.traduccion import MessageTranslation
from app.services.traduccion import ajustes
from app.services.traduccion import cache as _cache
from app.services.traduccion import glosario as _glosario
from app.services.traduccion.idiomas import detectar_si_seguro, normalizar
from app.services.traduccion.servicio import TRADUCIDO, traducir_uno

logger = logging.getLogger(__name__)

#: Separador entre la traduccion y el original cuando se envian los dos.
SEPARADOR_DEL_ORIGINAL = "\n\n----\n"


# ── Idioma del cliente ───────────────────────────────────────────────────────

def idioma_del_cliente(db: Session, *, ticket=None, conv=None) -> tuple[Optional[str], Optional[str]]:
    """`(idioma, de_donde)`; `de_donde` es `contact`, `portal` o `detected`. `(None, None)` si no se sabe."""
    from app.models.client_portal import ClientUser
    from app.models.clients import ClientPortalConfig

    cliente = None
    if conv is not None and conv.client_user_id:
        cliente = db.get(ClientUser, conv.client_user_id)
    if cliente is None and ticket is not None and ticket.requester_client_id:
        cliente = db.get(ClientUser, ticket.requester_client_id)
    if cliente is not None and normalizar(cliente.language):
        return normalizar(cliente.language), "contact"

    if conv is not None and normalizar(conv.language):
        return normalizar(conv.language), "portal"
    empresa_cliente = (getattr(ticket, "client_id", None) if ticket is not None else None) or \
        (cliente.client_org_id if cliente is not None else None)
    if empresa_cliente:
        cfg = db.query(ClientPortalConfig.default_language).filter(
            ClientPortalConfig.client_id == empresa_cliente).scalar()
        if normalizar(cfg):
            return normalizar(cfg), "portal"

    detectado = _ultimo_idioma_del_cliente(db, ticket=ticket, conv=conv)
    if detectado:
        return detectado, "detected"
    return None, None


def _ultimo_idioma_del_cliente(db: Session, *, ticket=None, conv=None) -> Optional[str]:
    from app.models.service_desk import ChannelMessage, TicketComment
    if conv is not None:
        fila = db.query(ChannelMessage.language).filter(
            ChannelMessage.conversation_id == conv.id, ChannelMessage.direction == "in",
            ChannelMessage.language.isnot(None)).order_by(ChannelMessage.created_at.desc()).first()
        if fila and normalizar(fila[0]):
            return normalizar(fila[0])
        if conv.ticket_id and ticket is None:
            from app.models.service_desk import Ticket
            ticket = db.get(Ticket, conv.ticket_id)
    if ticket is not None:
        fila = db.query(TicketComment.language).filter(
            TicketComment.ticket_id == ticket.id, TicketComment.is_public.is_(True),
            TicketComment.author_user_id.is_(None), TicketComment.language.isnot(None),
        ).order_by(TicketComment.created_at.desc()).first()
        if fila and normalizar(fila[0]):
            return normalizar(fila[0])
        return normalizar(ticket.language)
    return None


# ── Contexto (ticket o conversacion) con su acceso ───────────────────────────

@dataclass
class Contexto:
    tipo: str              # ticket | conversation
    ticket: object = None
    conv: object = None

    @property
    def org_id(self):
        return (self.ticket or self.conv).organization_id

    @property
    def canal(self) -> str:
        if self.conv is not None:
            return self.conv.channel if self.conv.channel in ajustes.CANALES else "livechat"
        origen = (getattr(self.ticket, "source", None) or "").lower()
        return origen if origen in ajustes.CANALES else "ticket"


def contexto(db: Session, usuario, tipo: str, id_: str) -> Contexto:
    if tipo == "ticket":
        from app.services.service_desk.scoping import get_scoped_ticket_or_404
        return Contexto("ticket", ticket=get_scoped_ticket_or_404(db, usuario, id_))
    if tipo == "conversation":
        from app.services.service_desk.conversaciones import _de_la_empresa
        return Contexto("conversation", conv=_de_la_empresa(db, id_, usuario.organization_id))
    raise ErrorDeDominio(422, "trad_tipo_desconocido")


# ── Vista previa ─────────────────────────────────────────────────────────────

def _idioma_del_texto(db: Session, org_id, texto: str, usuario) -> Optional[str]:
    from app.services.traduccion.mensajes import idioma_de_usuario
    return detectar_si_seguro(texto, ajustes.confianza_minima(db, org_id)) or (
        idioma_de_usuario(db, usuario) if usuario is not None else None)


def vista_previa(db: Session, usuario, tipo: str, id_: str, texto: str, destino: Optional[str] = None) -> dict:
    ctx = contexto(db, usuario, tipo, id_)
    if destino:
        idioma, de_donde = normalizar(destino), "manual"
        if not idioma:
            raise ErrorDeDominio(422, "trad_idioma_no_soportado")
    else:
        idioma, de_donde = idioma_del_cliente(db, ticket=ctx.ticket, conv=ctx.conv)
    base = {"target_language": idioma, "target_source": de_donde, "enabled": ajustes.habilitada_en(
        db, ctx.org_id, ctx.canal), "include_original": ajustes.incluir_original(db, ctx.org_id)}
    if not idioma:
        return {**base, "status": "unavailable", "reason": "unknown_client_language", "text": None,
                "source_language": None}
    origen = detectar_si_seguro(texto, ajustes.confianza_minima(db, ctx.org_id))
    r = traducir_uno(db, ctx.org_id, texto, idioma, canal=ctx.canal, origen=origen, user_id=usuario.id)
    db.commit()
    return {**base, "status": r.estado, "reason": r.motivo, "text": r.texto if r.estado == TRADUCIDO else None,
            "source_language": r.origen, "provider": r.proveedor}


# ── Envio ────────────────────────────────────────────────────────────────────

@dataclass
class Salida:
    cuerpo: str                       # lo que se guarda y recibe el cliente
    idioma: Optional[str]             # idioma de `cuerpo`
    original: Optional[str] = None    # lo que escribio el operador, si se tradujo
    idioma_original: Optional[str] = None
    origen: Optional[str] = None      # auto | edited
    proveedor: Optional[str] = None
    motivo: Optional[str] = None      # por que no se tradujo, si no se tradujo


def _era_la_vista_previa(db: Session, org_id, texto: str, origen, destino: str, traducido: str) -> bool:
    terminos = _glosario.relevantes(_glosario.activos(db, org_id), texto, destino)
    k = _cache.clave(texto, origen, destino, _glosario.huella(terminos))
    fila = _cache.buscar(db, org_id, [k]).get(k)
    return fila is not None and fila.translated_text == traducido


def preparar(db: Session, org_id, canal: str, texto: str, *, usuario=None, ticket=None, conv=None,
             texto_cliente: Optional[str] = None, idioma_cliente: Optional[str] = None) -> Salida:
    """Decide que se envia. No guarda nada del mensaje: quien llama lo crea con `cuerpo`/`idioma`."""
    origen = _idioma_del_texto(db, org_id, texto, usuario)
    if not ajustes.habilitada_en(db, org_id, canal):
        return Salida(texto, origen, motivo="disabled")
    if texto_cliente is not None and texto_cliente.strip():
        destino = normalizar(idioma_cliente)
        if not destino:
            raise ErrorDeDominio(422, "trad_idioma_no_soportado")
        if destino == origen or texto_cliente.strip() == texto.strip():
            return Salida(texto, origen)
        editada = not _era_la_vista_previa(db, org_id, texto, detectar_si_seguro(
            texto, ajustes.confianza_minima(db, org_id)), destino, texto_cliente)
        return Salida(texto_cliente.strip(), destino, texto, origen, "edited" if editada else "auto")
    if not ajustes.salida_automatica(db, org_id):
        return Salida(texto, origen, motivo="outbound_auto_off")
    destino, _ = idioma_del_cliente(db, ticket=ticket, conv=conv)
    if not destino:
        return Salida(texto, origen, motivo="unknown_client_language")
    if destino == origen:
        return Salida(texto, origen)
    r = traducir_uno(db, org_id, texto, destino, canal=canal, origen=detectar_si_seguro(
        texto, ajustes.confianza_minima(db, org_id)), user_id=getattr(usuario, "id", None))
    if r.estado != TRADUCIDO:
        if r.estado == "unavailable":
            logger.info("traduccion de salida no disponible (%s): se envia el original", r.motivo)
        return Salida(texto, r.origen or origen, motivo=r.motivo)
    return Salida(r.texto, destino, texto, r.origen or origen, "auto", r.proveedor)


def anotar_autor(db: Session, org_id, tipo: str, mensaje_id: str, salida: Salida, usuario=None,
                 recurso: Optional[str] = None) -> None:
    """Guarda lo que escribio el operador y lo audita. Nada si no se tradujo."""
    if salida.original is None:
        return
    from app.services.audit import audit_log
    from app.services.traduccion.mensajes import guardar
    idioma_autor = salida.idioma_original or "und"
    guardar(db, org_id, tipo, mensaje_id, "body", salida.idioma, idioma_autor, salida.original,
            "author", salida.proveedor, getattr(usuario, "id", None))
    audit_log(db, usuario, "TRANSLATE", recurso or tipo, mensaje_id, None, new_values={
        "direction": "outbound", "source_language": salida.idioma_original, "target_language": salida.idioma,
        "origin": salida.origen, "provider": salida.proveedor,
        "original_chars": len(salida.original), "sent_chars": len(salida.cuerpo)})


def publicar_texto_del_operador(db: Session, ticket, usuario, texto: str, crear):
    """Comentario publico automatico con un texto que escribio un operador (el
    de un paso de aprovisionamiento o de un playbook): sale en el idioma del
    cliente como una respuesta sin vista previa (`preparar`), y lo escrito
    queda en `message_translations`. `crear(cuerpo, idioma)` devuelve el
    `TicketComment`; se anade a la sesion y se devuelve (16-11-2026)."""
    from app.services.traduccion.mensajes import canal_del_ticket
    s = preparar(db, ticket.organization_id, canal_del_ticket(ticket), texto, usuario=usuario, ticket=ticket)
    comentario = crear(s.cuerpo, s.idioma)
    db.add(comentario)
    if s.original is not None:
        db.flush()
        anotar_autor(db, ticket.organization_id, "ticket_comment", comentario.id, s, usuario, "ticket_comment")
    return comentario


# ── Lo que ve el cliente ─────────────────────────────────────────────────────

def original_del_autor(db: Session, org_id, tipo: str, mensaje_id: str) -> Optional[str]:
    fila = db.query(MessageTranslation.text).filter(
        MessageTranslation.organization_id == org_id, MessageTranslation.message_type == tipo,
        MessageTranslation.message_id == mensaje_id, MessageTranslation.field == "body",
        MessageTranslation.origin == "author").first()
    return fila[0] if fila else None


def texto_para_cliente(db: Session, org_id, tipo: str, mensaje_id: str, cuerpo: str) -> str:
    if not cuerpo or not ajustes.incluir_original(db, org_id):
        return cuerpo
    original = original_del_autor(db, org_id, tipo, mensaje_id)
    return f"{cuerpo}{SEPARADOR_DEL_ORIGINAL}{original}" if original else cuerpo
