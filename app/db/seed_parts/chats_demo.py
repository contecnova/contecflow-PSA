"""Conversaciones de ejemplo de la demo en los cuatro chats (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §12 y README («Datos demo»). Siembra, para
la empresa demo (`contecflow-demo`), conversaciones realistas con mensajes en
los dos sentidos y fechas de los últimos días:

1. **Chat interno** (colaboración): un grupo del equipo con una imagen adjunta,
   reacciones, una cita y un mensaje editado con su versión anterior.
2. **Pestaña «Chat» del portal** (colaboración con clientes): un grupo con un
   usuario del portal, con imagen, reacciones del cliente y del equipo, una
   cita y una edición del cliente con su rastro.
3. **Conversación formal** (conversaciones gobernadas) «con supervisión»: su
   política exige aprobar los mensajes del cliente y hay uno pendiente de
   aprobación; además imagen, reacción, cita y edición.
4. **Chat en vivo de Soporte**: el cliente habla con el asistente, pide una
   persona (traspaso a agente), nace su ticket enlazado y el agente responde;
   con imagen, reacción, cita y edición.

Idempotente: cada conversación lleva una marca fija (título o `external_id`)
y, si ya existe, no se vuelve a crear. Usa los usuarios del portal de la
empresa; si no hay, crea dos con la contraseña demo de siempre
(`DEFAULT_USER_PASSWORD`, la que alinea `scripts/sincronizar_contrasenas_demo.py`).

La imagen es un PNG pequeño VÁLIDO generado aquí (sin ficheros binarios en el
repositorio), guardado en el almacén de objetos con una clave fija.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from datetime import datetime, timedelta, timezone

#: Usuarios del portal de la demo (si la empresa no tiene ninguno). Los alinea
#: `scripts/sincronizar_contrasenas_demo.py` con DEFAULT_USER_PASSWORD.
CLIENTES_DEMO = (
    ("marta.ruiz@cliente-demo.example.com", "Marta Ruiz", "Responsable de operaciones"),
    ("jorge.lima@cliente-demo.example.com", "Jorge Lima", "Compras"),
)

MARCA_INTERNO = "Demo · Equipo de entrega"
MARCA_PORTAL = "Demo · Seguimiento con el cliente"
MARCA_FORMAL = "Demo · Cambio de alcance (con supervisión)"
MARCA_EN_VIVO = "demo-livechat-1"
TEMA_SUPERVISADO = "governance"


def png_demo(ancho: int = 24, alto: int = 16) -> bytes:
    """Un PNG válido (franjas de color) sin dependencias: cabecera, IHDR, IDAT y IEND con CRC."""
    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)

    filas = b""
    for y in range(alto):
        color = (37, 99, 235) if y < alto // 2 else (16, 185, 129)
        filas += b"\x00" + bytes(color) * ancho
    ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", ihdr) + trozo(b"IDAT", zlib.compress(filas, 9)) + trozo(b"IEND", b"")


def _hace(dias: float, horas: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=dias, hours=horas)


def _guardar_imagen(clave: str):
    from app.services.collaboration._storage import storage
    return storage.save_bytes(clave, png_demo())


# ── Personas ─────────────────────────────────────────────────────────────────

def _equipo(db, org_id) -> dict:
    from app.models.user import User
    filas = {u.username: u for u in db.query(User).filter(User.organization_id == org_id).all()}
    admin = filas.get("admin") or next(iter(filas.values()), None)
    return {"admin": admin, "ana": filas.get("ana.torres") or admin, "luis": filas.get("luis.vega") or admin}


def clientes_del_portal(db, org_id) -> list:
    """Los usuarios del portal activos de la empresa; si no hay, los dos de la demo."""
    from app.core.config import settings
    from app.core.security import get_password_hash
    from app.models.client_portal import ClientUser
    from app.models.clients import Client
    from app.models.project import Project
    activos = db.query(ClientUser).filter(ClientUser.organization_id == org_id, ClientUser.is_active.is_(True),
                                          ClientUser.archived_at.is_(None)).order_by(ClientUser.created_at).all()
    if len(activos) >= 2:
        return activos[:2]
    cliente = db.query(Client).filter(Client.organization_id == org_id).order_by(Client.name).first()
    proyecto = None
    if cliente is not None:
        proyecto = db.query(Project).filter(Project.client_id == cliente.id).first()
    proyecto = proyecto or db.query(Project).filter(Project.organization_id == org_id).first()
    for email, nombre, cargo in CLIENTES_DEMO:
        if len(activos) >= 2:
            break
        cu = db.query(ClientUser).filter(ClientUser.organization_id == org_id, ClientUser.email == email).first()
        if cu is None:
            cu = ClientUser(organization_id=org_id, client_org_id=getattr(cliente, "id", None),
                            project_id=getattr(proyecto, "id", None), full_name=nombre, email=email,
                            job_title=cargo, company=getattr(cliente, "name", None) or "Cliente demo",
                            hashed_password=get_password_hash(settings.DEFAULT_USER_PASSWORD or ""),
                            is_active=True, language="es")
            db.add(cu)
            db.flush()
        if cu not in activos:
            activos.append(cu)
    return activos[:2]


# ── 1 y 2. Colaboración (chat interno y pestaña «Chat» del portal) ───────────

def _espacio(db, org_id):
    from app.models.collaboration import CollaborationWorkspace
    ws = db.query(CollaborationWorkspace).filter(CollaborationWorkspace.organization_id == org_id).first()
    if ws is None:
        ws = CollaborationWorkspace(organization_id=org_id, name="ContecFlow Demo")
        db.add(ws)
        db.flush()
    return ws


def _grupo_de_colaboracion(db, org_id, titulo: str, miembros: list, clientes: list, guion: list,
                           creado_por) -> bool:
    """Crea el grupo con su guion si no existe. `guion`: dicts con autor, texto, hace, y extras."""
    from app.models.collaboration import (
        CollaborationAttachment, CollaborationAttachmentVersion, CollaborationConversation,
        CollaborationConversationMember, CollaborationGroupConversation, CollaborationMessage,
        CollaborationMessageVersion, CollaborationReaction,
    )
    if db.query(CollaborationGroupConversation).filter(CollaborationGroupConversation.organization_id == org_id,
                                                       CollaborationGroupConversation.title == titulo).first():
        return False
    ws = _espacio(db, org_id)
    conv = CollaborationConversation(organization_id=org_id, kind="group", workspace_id=ws.id)
    db.add(conv)
    db.flush()
    grupo = CollaborationGroupConversation(organization_id=org_id, workspace_id=ws.id, conversation_id=conv.id,
                                           title=titulo, created_by=creado_por.id)
    db.add(grupo)
    db.flush()
    vistos = set()
    for u in miembros:
        if u is not None and u.id not in vistos:
            vistos.add(u.id)
            db.add(CollaborationConversationMember(organization_id=org_id, conversation_id=conv.id, group_id=grupo.id,
                                                   user_id=u.id, is_admin=(u.id == creado_por.id)))
    for c in clientes:
        db.add(CollaborationConversationMember(organization_id=org_id, conversation_id=conv.id, group_id=grupo.id,
                                               client_user_id=c.id))
    db.flush()
    creados = []
    for paso in guion:
        autor = paso["autor"]
        es_cliente = autor.__class__.__name__ == "ClientUser"
        cuando = _hace(*paso["hace"])
        msg = CollaborationMessage(
            organization_id=org_id, conversation_id=conv.id,
            user_id=None if es_cliente else autor.id, client_user_id=autor.id if es_cliente else None,
            type="file" if paso.get("imagen") else "text", status="visible", body=paso["texto"],
            metadata_json={}, sent_at=cuando,
            parent_message_id=creados[paso["cita"]].id if "cita" in paso else None,
        )
        db.add(msg)
        db.flush()
        if paso.get("imagen"):
            clave = f"{org_id}/{conv.id}/demo_{paso['imagen']}"
            g = _guardar_imagen(clave)
            att = CollaborationAttachment(
                organization_id=org_id, conversation_id=conv.id, message_id=msg.id,
                uploaded_by_user_id=None if es_cliente else autor.id,
                uploaded_by_client_id=autor.id if es_cliente else None, name=paso["imagen"], mime_type="image/png",
                size_bytes=g.size_bytes, storage_provider=g.storage_provider, storage_key=g.storage_key,
                sha256=g.sha256, av_status="clean", dlp_status="allowed", is_quarantined=False, created_at=cuando)
            db.add(att)
            db.flush()
            db.add(CollaborationAttachmentVersion(organization_id=org_id, attachment_id=att.id, version=1,
                                                  storage_key=g.storage_key, size_bytes=g.size_bytes, sha256=g.sha256,
                                                  uploaded_by_user_id=None if es_cliente else autor.id))
            msg.has_attachments = True
            msg.metadata_json = {"attachment_id": att.id, "quarantined": False}
        if paso.get("antes"):
            db.add(CollaborationMessageVersion(
                organization_id=org_id, message_id=msg.id, body=paso["antes"], metadata_json={},
                edited_by_user_id=None if es_cliente else autor.id, edited_by_client_id=autor.id if es_cliente else None,
                change_type="edit", edited_at=cuando + timedelta(minutes=3)))
            msg.status = "edited"
            msg.edited_at = cuando + timedelta(minutes=3)
        for quien, emoji in paso.get("reacciones", []):
            de_cliente = quien.__class__.__name__ == "ClientUser"
            db.add(CollaborationReaction(organization_id=org_id, message_id=msg.id, emoji=emoji,
                                         user_id=None if de_cliente else quien.id,
                                         client_user_id=quien.id if de_cliente else None))
        creados.append(msg)
    conv.last_activity_at = creados[-1].sent_at
    conv.last_message_id = creados[-1].id
    db.flush()
    return True


def _chat_interno(db, org_id, eq) -> bool:
    ana, luis, admin = eq["ana"], eq["luis"], eq["admin"]
    guion = [
        {"autor": ana, "hace": (3, 5), "texto": "Buenos días. ¿Cómo vamos con la entrega del sprint 14?"},
        {"autor": luis, "hace": (3, 4), "texto": "Bien: quedan dos historias en revisión y el informe de pruebas.",
         "reacciones": [(ana, "👍")]},
        {"autor": luis, "hace": (2, 6), "texto": "Os paso la captura del tablero de hoy.", "imagen": "tablero-sprint-14.png",
         "reacciones": [(admin, "🎉"), (ana, "👀")]},
        {"autor": ana, "hace": (2, 5), "cita": 2, "texto": "Perfecto. ¿El riesgo del proveedor sigue abierto?"},
        {"autor": admin, "hace": (1, 3), "texto": "Lo cerramos el jueves con el plan de contingencia aprobado.",
         "antes": "Lo cerramos el miércoles con el plan de contingencia.", "reacciones": [(luis, "✅")]},
        {"autor": ana, "hace": (0, 2), "texto": "Gracias. Preparo la demo para el cliente del viernes."},
    ]
    return _grupo_de_colaboracion(db, org_id, MARCA_INTERNO, [admin, ana, luis], [], guion, ana)


def _chat_del_portal(db, org_id, eq, clientes) -> bool:
    ana, luis = eq["ana"], eq["luis"]
    cli = clientes[0]
    guion = [
        {"autor": ana, "hace": (4, 3), "texto": f"Hola {cli.full_name.split()[0]}, os abrimos este chat para el seguimiento del despliegue."},
        {"autor": cli, "hace": (4, 2), "texto": "Genial, gracias. ¿Tenéis ya fecha para la ventana de mantenimiento?",
         "reacciones": [(ana, "👍")]},
        {"autor": ana, "hace": (3, 6), "cita": 1, "texto": "Sí: el sábado de 8:00 a 10:00. Os mandamos el aviso formal hoy."},
        {"autor": cli, "hace": (2, 4), "texto": "Os adjunto la captura del error que vemos en el informe mensual.",
         "imagen": "error-informe-mensual.png", "reacciones": [(luis, "👀")]},
        {"autor": luis, "hace": (2, 2), "texto": "Recibido. Es el filtro de fechas: lo corregimos en la versión de esta semana."},
        {"autor": cli, "hace": (1, 1), "texto": "Perfecto, lo validamos el lunes con el equipo de operaciones.",
         "antes": "Perfecto, lo validamos el lunes.", "reacciones": [(ana, "🙏")]},
    ]
    return _grupo_de_colaboracion(db, org_id, MARCA_PORTAL, [ana, luis], [cli], guion, ana)


# ── 3. Conversación formal con supervisión ───────────────────────────────────

def _conversacion_formal(db, org_id, eq, clientes) -> bool:
    from app.models.portal_conversations import (
        PortalConversation, PortalConversationAttachment, PortalConversationMessage,
        PortalConversationMessageVersion, PortalConversationParticipant, PortalConversationPolicy,
        PortalConversationReaction,
    )
    if db.query(PortalConversation).filter(PortalConversation.organization_id == org_id,
                                           PortalConversation.title == MARCA_FORMAL).first():
        return False
    ana, admin = eq["ana"], eq["admin"]
    cli = clientes[0]
    politica = db.query(PortalConversationPolicy).filter(PortalConversationPolicy.organization_id == org_id,
                                                         PortalConversationPolicy.topic_type == TEMA_SUPERVISADO).first()
    if politica is None:
        politica = PortalConversationPolicy(organization_id=org_id, topic_type=TEMA_SUPERVISADO, is_active=True,
                                            requires_client_message_approval=True, requires_team_message_approval=False,
                                            approval_user_id=admin.id)
        db.add(politica)
        db.flush()
    conv = PortalConversation(organization_id=org_id, client_org_id=cli.client_org_id, project_id=cli.project_id,
                              topic_type=TEMA_SUPERVISADO, title=MARCA_FORMAL, status="active", policy_id=politica.id,
                              created_by_user_id=ana.id, created_at=_hace(5), first_response_at=_hace(5, -1))
    db.add(conv)
    db.flush()
    db.add(PortalConversationParticipant(organization_id=org_id, conversation_id=conv.id,
                                         participant_type="internal_user", user_id=ana.id,
                                         role_in_conversation="owner", can_invite=True, can_close=True))
    db.add(PortalConversationParticipant(organization_id=org_id, conversation_id=conv.id,
                                         participant_type="internal_user", user_id=admin.id,
                                         role_in_conversation="approver"))
    db.add(PortalConversationParticipant(organization_id=org_id, conversation_id=conv.id,
                                         participant_type="client_user", client_user_id=cli.id,
                                         client_org_id=cli.client_org_id, role_in_conversation="requester"))
    db.flush()

    def _msg(texto, hace, *, de_cliente=False, tipo="text", padre=None, estado="allowed", notas=None):
        cuando = _hace(*hace)
        m = PortalConversationMessage(
            conversation_id=conv.id, organization_id=org_id, project_id=conv.project_id, parent_message_id=padre,
            sender_user_id=None if de_cliente else ana.id, sender_client_id=cli.id if de_cliente else None,
            message_type=tipo, body=texto, raw_body=texto, grc_status=estado, moderation_notes=notas,
            created_at=cuando, delivered_at=None if estado == "pending_review" else cuando)
        db.add(m)
        db.flush()
        return m

    m1 = _msg("Abrimos esta conversación para revisar el cambio de alcance del módulo de informes.", (5, 0))
    m2 = _msg("Gracias. Necesitamos añadir dos informes regulatorios trimestrales.", (4, 6), de_cliente=True)
    m3 = _msg("Os adjunto el borrador de la estimación (captura del plan).", (3, 5), tipo="attachment", padre=m2.id)
    g = _guardar_imagen(f"portal-chat/{org_id}/{conv.id}/demo_estimacion-cambio.png")
    db.add(PortalConversationAttachment(organization_id=org_id, conversation_id=conv.id, message_id=m3.id,
                                        uploaded_by_user_id=ana.id, name="estimacion-cambio.png", mime_type="image/png",
                                        size_bytes=g.size_bytes, storage_provider=g.storage_provider,
                                        storage_key=g.storage_key, sha256=g.sha256, av_status="clean",
                                        dlp_status="allowed", created_at=m3.created_at))
    db.add(PortalConversationReaction(organization_id=org_id, message_id=m3.id, client_user_id=cli.id, emoji="👍"))
    m4 = _msg("La estimación nos encaja; lo llevamos al comité del jueves.", (2, 3), de_cliente=True)
    db.add(PortalConversationMessageVersion(organization_id=org_id, message_id=m4.id,
                                            body="La estimación nos encaja.", raw_body="La estimación nos encaja.",
                                            change_type="edit", edited_by_client_id=cli.id,
                                            edited_at=m4.created_at + timedelta(minutes=4)))
    m4.edited_at = m4.created_at + timedelta(minutes=4)
    # Pendiente de aprobación: la política «governance» exige revisar lo que escribe el cliente.
    _msg("Aprobado por el comité. ¿Podéis enviarnos la adenda del contrato para firmarla?", (0, 3), de_cliente=True,
         estado="pending_review", notas="approval_required")
    conv.last_message_at = _hace(0, 3)
    db.flush()
    return True


# ── 4. Chat en vivo de Soporte con traspaso a agente y ticket ────────────────

def _chat_en_vivo(db, org_id, eq, clientes) -> bool:
    from app.models.service_desk import ChannelConversation, ChannelMessage
    from app.models.service_desk.mercado import ChannelAttachment, ChannelMessageVersion, ChannelReaction
    if db.query(ChannelConversation).filter(ChannelConversation.organization_id == org_id,
                                            ChannelConversation.external_id == MARCA_EN_VIVO).first():
        return False
    from app.services.service_desk.conversaciones import _asegurar_ticket
    luis = eq["luis"]
    cli = clientes[1] if len(clientes) > 1 else clientes[0]
    conv = ChannelConversation(organization_id=org_id, channel="livechat", external_id=MARCA_EN_VIVO,
                               client_user_id=cli.id, visitor_name=cli.full_name, language="es", status="bot",
                               created_at=_hace(1, 6))
    db.add(conv)
    db.flush()

    def _m(direccion, autor, texto, hace, *, usuario=None, cita=None):
        m = ChannelMessage(organization_id=org_id, conversation_id=conv.id, direction=direccion, author_type=autor,
                           author_user_id=getattr(usuario, "id", None), body=texto, created_at=_hace(*hace),
                           reply_to_message_id=cita)
        db.add(m)
        db.flush()
        return m

    p1 = _m("in", "customer", "Hola, no puedo descargar la factura de octubre desde el portal.", (1, 6))
    _m("out", "bot", "Prueba a recargar la página de Facturas. Si sigue fallando, puedo pasarte con una persona.", (1, 5.9))
    p2 = _m("in", "customer", "Sigue fallando. Te paso una captura del error.", (1, 5.5))
    g = _guardar_imagen(f"livechat/{org_id}/{conv.id}/demo_error-factura.png")
    db.add(ChannelAttachment(organization_id=org_id, conversation_id=conv.id, message_id=p2.id,
                             uploaded_by_client_id=cli.id, name="error-factura.png", mime_type="image/png",
                             size_bytes=g.size_bytes, storage_provider=g.storage_provider, storage_key=g.storage_key,
                             sha256=g.sha256, av_status="clean", dlp_status="allowed"))
    # Traspaso a agente: nace el ticket enlazado y la conversación espera a una persona.
    ticket = _asegurar_ticket(db, conv, f"{p1.body}\n{p2.body}", client_user=cli)
    _m("out", "system", "waiting_agent", (1, 5.4))
    conv.status = "agent"
    conv.assigned_user_id = luis.id
    if ticket is not None and not getattr(ticket, "assigned_to_user_id", None):
        ticket.assigned_to_user_id = luis.id
    _m("out", "system", "agent_joined", (1, 5.2), usuario=luis)
    r1 = _m("out", "agent", "Hola, soy Luis, de Soporte. Ya veo el error: es un permiso del documento. Lo corrijo ahora.",
            (1, 5), usuario=luis, cita=p2.id)
    db.add(ChannelReaction(organization_id=org_id, conversation_id=conv.id, message_id=r1.id, client_user_id=cli.id,
                           emoji="🙏"))
    r2 = _m("out", "agent", "Listo: ya puedes descargar la factura de octubre. Dejo el ticket abierto hasta que lo confirmes.",
            (1, 4.5), usuario=luis)
    db.add(ChannelMessageVersion(organization_id=org_id, conversation_id=conv.id, message_id=r2.id,
                                 body="Listo: ya puedes descargar la factura.", change_type="edit",
                                 edited_by_user_id=luis.id, edited_at=r2.created_at + timedelta(minutes=2)))
    r2.edited_at = r2.created_at + timedelta(minutes=2)
    _m("in", "customer", "Confirmado, ya la tengo. ¡Gracias!", (1, 4))
    conv.last_message_at = _hace(1, 4)
    conv.last_inbound_at = conv.last_message_at
    db.flush()
    return True


# ── Entrada ──────────────────────────────────────────────────────────────────

def sembrar_chats(db, org_id: str) -> dict:
    """Siembra los cuatro chats de ejemplo en la empresa. Idempotente. Confirma al final."""
    eq = _equipo(db, org_id)
    if eq["admin"] is None:
        return {"omitido": "sin usuarios en la empresa"}
    clientes = clientes_del_portal(db, org_id)
    hecho = {
        "chat_interno": _chat_interno(db, org_id, eq),
        "chat_del_portal": _chat_del_portal(db, org_id, eq, clientes) if clientes else False,
        "conversacion_formal": _conversacion_formal(db, org_id, eq, clientes) if clientes else False,
        "chat_en_vivo": _chat_en_vivo(db, org_id, eq, clientes) if clientes else False,
    }
    db.commit()
    return hecho


def seed_chats_demo() -> None:
    """`python -m app.db.seed` (modo demo de setup.bat/setup.sh): chats de ejemplo de la empresa demo."""
    from app.db.seed_parts._sesion import sesion_de_siembra
    from app.models.mfa import Organization
    from app.db.seed_parts._sesion import SLUG_DEMO
    db = sesion_de_siembra()
    try:
        org = db.query(Organization).filter(Organization.slug == SLUG_DEMO).first()
        if org is None:
            print("  Chats de ejemplo: sin empresa demo, nada que sembrar")
            return
        hecho = sembrar_chats(db, org.id)
        print(f"  Chats de ejemplo (interno, portal, formal con supervisión, chat en vivo): {hecho}")
    except Exception as exc:  # noqa: BLE001 - un chat de ejemplo no tumba la siembra
        db.rollback()
        print(f"  Chats de ejemplo: no se pudieron sembrar ({exc})")
    finally:
        db.close()


def huella_png() -> str:
    return hashlib.sha256(png_demo()).hexdigest()
