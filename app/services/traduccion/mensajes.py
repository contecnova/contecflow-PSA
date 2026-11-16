"""Mensajes guardados en el idioma de quien mira (entrada).

Cada mensaje externo guarda su idioma (`language`, detectado al guardar o al
traducir). Cuando un operador lo abre, la interfaz pide aqui la version en SU
idioma (`traducir_mensajes`): se devuelve la ya guardada en
`message_translations` o se traduce, se guarda (auditable: proveedor, fecha,
origen) y se devuelve. Dos operadores con idiomas distintos tienen cada uno la
suya, y la segunda vez no se paga.

Tipos (`TIPOS`) y su acceso, con la misma regla que la pantalla que los muestra:

- `ticket_comment` y `ticket` (titulo y descripcion): el ticket con
  `get_scoped_ticket_or_404` (empresa y ambito del rol). Las notas internas se
  traducen tambien, solo entre operadores: jamas salen al cliente.
- `channel_message`: la conversacion de la empresa de quien mira.
- `chat_message`: el chat interno, con `assert_conversation_access`.

Canal de cada mensaje (`TRANSLATION_CHANNELS`): el origen del ticket
(`email`, `whatsapp`...) o `ticket`; el de la conversacion; `internal_chat`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.traduccion import MessageTranslation
from app.services.traduccion import ajustes
from app.services.traduccion.idiomas import IDIOMAS_DE_OPERADOR, normalizar
from app.services.traduccion.servicio import MISMO_IDIOMA, TRADUCIDO, traducir

#: Maximo de mensajes por peticion (una pantalla de ticket o de conversacion).
MAX_POR_PETICION = 200


@dataclass
class Mensaje:
    tipo: str
    id: str
    org_id: Optional[str]
    campos: dict            # campo -> texto
    idioma: Optional[str]   # idioma guardado del mensaje
    canal: str
    objeto: object          # la fila, para guardar el idioma detectado


def idioma_de_usuario(db: Session, usuario) -> str:
    """El idioma del operador: sus preferencias o el de la empresa."""
    from app.models.user import UserPreference
    pref = db.query(UserPreference.language).filter(UserPreference.user_id == usuario.id).scalar()
    return normalizar(pref) or ajustes.idioma_por_defecto(db, getattr(usuario, "organization_id", None)) \
        or IDIOMAS_DE_OPERADOR[0]


def canal_del_ticket(ticket) -> str:
    origen = (getattr(ticket, "source", None) or "").lower()
    return origen if origen in ajustes.CANALES else "ticket"


def _comentario(db: Session, usuario, id_: str) -> Mensaje:
    from app.models.service_desk import TicketComment
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    c = db.query(TicketComment).filter(TicketComment.id == id_).first()
    if c is None:
        raise ErrorDeDominio(404, "trad_mensaje_no_encontrado")
    t = get_scoped_ticket_or_404(db, usuario, c.ticket_id)
    return Mensaje("ticket_comment", c.id, t.organization_id, {"body": c.body}, c.language, canal_del_ticket(t), c)


def _ticket(db: Session, usuario, id_: str) -> Mensaje:
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    t = get_scoped_ticket_or_404(db, usuario, id_)
    return Mensaje("ticket", t.id, t.organization_id, {"title": t.title, "description": t.description},
                   t.language, canal_del_ticket(t), t)


def _mensaje_de_canal(db: Session, usuario, id_: str) -> Mensaje:
    from app.models.service_desk import ChannelConversation, ChannelMessage
    m = db.query(ChannelMessage).filter(ChannelMessage.id == id_,
                                        ChannelMessage.organization_id == usuario.organization_id).first()
    conv = db.get(ChannelConversation, m.conversation_id) if m is not None else None
    if m is None or conv is None or conv.organization_id != usuario.organization_id:
        raise ErrorDeDominio(404, "trad_mensaje_no_encontrado")
    canal = conv.channel if conv.channel in ajustes.CANALES else "livechat"
    return Mensaje("channel_message", m.id, conv.organization_id, {"body": m.body}, m.language, canal, m)


def _mensaje_de_chat(db: Session, usuario, id_: str) -> Mensaje:
    from app.services.collaboration.messages import _mensaje_accesible
    m = _mensaje_accesible(db, usuario, id_)
    return Mensaje("chat_message", m.id, m.organization_id, {"body": m.body or ""}, None, "internal_chat", m)


TIPOS: dict[str, Callable[[Session, object, str], Mensaje]] = {
    "ticket_comment": _comentario,
    "ticket": _ticket,
    "channel_message": _mensaje_de_canal,
    "chat_message": _mensaje_de_chat,
}


def cargar(db: Session, usuario, tipo: str, id_: str) -> Mensaje:
    cargador = TIPOS.get(tipo)
    if cargador is None:
        raise ErrorDeDominio(422, "trad_tipo_desconocido")
    m = cargador(db, usuario, id_)
    if m.org_id != usuario.organization_id and not getattr(usuario, "is_superadmin", False):
        raise ErrorDeDominio(404, "trad_mensaje_no_encontrado")
    return m


def guardadas(db: Session, org_id: Optional[str], tipo: str, ids: list[str], destino: str) -> dict:
    """{(id, campo): MessageTranslation} ya guardadas para ese destino."""
    if not ids:
        return {}
    filas = db.query(MessageTranslation).filter(
        MessageTranslation.organization_id == org_id, MessageTranslation.message_type == tipo,
        MessageTranslation.message_id.in_(ids), MessageTranslation.target_language == destino).all()
    return {(f.message_id, f.field): f for f in filas}


def guardar(db: Session, org_id: Optional[str], tipo: str, id_: str, campo: str, origen: Optional[str],
            destino: str, texto: str, origen_de: str, proveedor: Optional[str], user_id: Optional[str]) -> None:
    fila = db.query(MessageTranslation).filter(
        MessageTranslation.organization_id == org_id, MessageTranslation.message_type == tipo,
        MessageTranslation.message_id == id_, MessageTranslation.field == campo,
        MessageTranslation.target_language == destino).first()
    if fila is None:
        db.add(MessageTranslation(organization_id=org_id, message_type=tipo, message_id=id_, field=campo,
                                  source_language=origen, target_language=destino, text=texto, origin=origen_de,
                                  provider=proveedor, created_by_user_id=user_id))
    else:
        fila.source_language, fila.text, fila.origin, fila.provider = origen, texto, origen_de, proveedor
        fila.created_by_user_id = user_id


def _salida(m: Mensaje, campo: str, **kw) -> dict:
    return {"type": m.tipo, "id": m.id, "field": campo, "source_language": m.idioma, **kw}


def _de_plantilla(m: Mensaje, destino: str, salida: list) -> bool:
    """Un ticket que abrio el sistema, o un comentario que escribio el sistema
    (16-11-2026), se pinta en el idioma de quien mira con su plantilla
    (`textos_del_sistema`), sin proveedor. True si lo ha resuelto."""
    from app.services.traduccion import textos_del_sistema as tds
    codigo = getattr(m.objeto, "system_template", None) if m.tipo in ("ticket", "ticket_comment") else None
    if not codigo:
        return False
    if m.tipo == "ticket_comment":
        cuerpo = tds.renderizar_comentario(codigo, tds.params_de(m.objeto) or {}, destino)
        texto = None if cuerpo is None else (cuerpo,)
        campos = ("body",)
    else:
        texto = tds.renderizar(codigo, tds.params_de(m.objeto) or {}, destino)
        campos = ("title", "description")
    if texto is None:
        return False
    for campo, valor in zip(campos, texto):
        if normalizar(m.idioma) == destino:
            salida.append(_salida(m, campo, status=MISMO_IDIOMA, text=None, target_language=destino))
        else:
            salida.append(_salida(m, campo, status=TRADUCIDO, text=valor, target_language=destino, origin="system",
                                  provider=None))
    return True


def traducir_mensajes(db: Session, usuario, items: list[dict], destino: Optional[str] = None) -> dict:
    """Las versiones en el idioma de quien mira (o `destino`) de los mensajes pedidos."""
    if len(items) > MAX_POR_PETICION:
        raise ErrorDeDominio(422, "trad_demasiados_mensajes")
    destino_n = normalizar(destino) if destino else idioma_de_usuario(db, usuario)
    if not destino_n:
        raise ErrorDeDominio(422, "trad_idioma_no_soportado")
    vistos, mensajes = set(), []
    for it in items:
        clave = (it.get("type"), it.get("id"))
        if clave in vistos or not all(clave):
            continue
        vistos.add(clave)
        mensajes.append(cargar(db, usuario, clave[0], clave[1]))

    salida: list[dict] = []
    # Lo ya guardado, por tipo.
    previas: dict = {}
    for tipo in {m.tipo for m in mensajes}:
        previas.update({(tipo, *k): v for k, v in
                        guardadas(db, usuario.organization_id, tipo, [m.id for m in mensajes if m.tipo == tipo],
                                  destino_n).items()})

    # Agrupar por (empresa, canal) lo que falta: una llamada por grupo.
    pendientes: dict[tuple, list[tuple[Mensaje, str]]] = {}
    for m in mensajes:
        if _de_plantilla(m, destino_n, salida):
            continue
        for campo, texto in m.campos.items():
            previa = previas.get((m.tipo, m.id, campo))
            if previa is not None:
                salida.append(_salida(m, campo, status=TRADUCIDO, text=previa.text, target_language=destino_n,
                                      origin=previa.origin, provider=previa.provider,
                                      source_language=previa.source_language or m.idioma))
            elif not (texto or "").strip() or normalizar(m.idioma) == destino_n:
                salida.append(_salida(m, campo, status=MISMO_IDIOMA, text=None, target_language=destino_n))
            else:
                pendientes.setdefault((m.org_id, m.canal), []).append((m, campo))

    for (org_id, canal), lista in pendientes.items():
        resultados = traducir(db, org_id, [m.campos[c] for m, c in lista], destino_n, canal=canal,
                              origenes=[m.idioma for m, _ in lista], user_id=usuario.id)
        for (m, campo), r in zip(lista, resultados):
            if r.origen and not m.idioma and hasattr(m.objeto, "language"):
                m.objeto.language = r.origen
                m.idioma = r.origen
            if r.estado == TRADUCIDO:
                guardar(db, org_id, m.tipo, m.id, campo, r.origen, destino_n, r.texto, "auto", r.proveedor,
                        usuario.id)
            salida.append(_salida(m, campo, status=r.estado, text=r.texto if r.estado == TRADUCIDO else None,
                                  target_language=destino_n, origin="auto" if r.estado == TRADUCIDO else None,
                                  provider=r.proveedor, reason=r.motivo, source_language=r.origen or m.idioma))
    db.commit()
    return {"target_language": destino_n, "enabled": ajustes.habilitada(db, usuario.organization_id),
            "items": salida}


def texto_en(db: Session, org_id: Optional[str], tipo: str, objeto, campo: str, destino: Optional[str],
             canal: str, user_id: Optional[str] = None) -> str:
    """El campo de un mensaje en `destino`, para quien no pasa por la pantalla
    (avisos por correo a los agentes). La guardada, o se traduce y se guarda;
    si no se puede, el original. Sin comprobar acceso: quien llama ya sabe a
    quien se lo manda."""
    texto = getattr(objeto, campo, None) or ""
    destino_n = normalizar(destino)
    idioma = getattr(objeto, "language", None)
    if not destino_n or not texto.strip() or normalizar(idioma) == destino_n:
        return texto
    previa = guardadas(db, org_id, tipo, [objeto.id], destino_n).get((objeto.id, campo))
    if previa is not None:
        return previa.text
    r = traducir(db, org_id, [texto], destino_n, canal=canal, origenes=[idioma], user_id=user_id)[0]
    if r.origen and idioma is None and hasattr(objeto, "language"):
        objeto.language = r.origen
    if r.estado == TRADUCIDO:
        guardar(db, org_id, tipo, objeto.id, campo, r.origen, destino_n, r.texto, "auto", r.proveedor, user_id)
        return r.texto
    return texto
